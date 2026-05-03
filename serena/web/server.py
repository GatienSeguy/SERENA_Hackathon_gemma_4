"""FastAPI + WebSocket server for SERENA web UI."""

from __future__ import annotations

import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
SERENA_ROOT = HERE.parent
sys.path.insert(0, str(SERENA_ROOT))

from serena_core import SerenaCore  # noqa: E402
from memory import SessionMemory  # noqa: E402

logger = logging.getLogger("serena.web")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

CONV_DIR = HERE / "conversations"
CONV_DIR.mkdir(exist_ok=True)
STATIC_DIR = HERE / "static"


# ──────────────────────────────────────────────────────────────────
# Storage
# ──────────────────────────────────────────────────────────────────
class ConversationStore:
    """JSON-on-disk persistence + in-memory SerenaCore cache."""

    def __init__(self) -> None:
        self._cores: dict[str, SerenaCore] = {}

    def _path(self, cid: str) -> Path:
        return CONV_DIR / f"{cid}.json"

    def list_meta(self) -> list[dict]:
        items = []
        for p in CONV_DIR.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                items.append({
                    "id": data["id"],
                    "title": data.get("title", "Nouvelle conversation"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "final_score": data.get("final_score", 0.0),
                    "final_action": data.get("final_action", "NORMAL"),
                })
            except Exception as exc:
                logger.warning("Skipping bad file %s: %s", p, exc)
        items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return items

    def load(self, cid: str) -> dict:
        p = self._path(cid)
        if not p.exists():
            raise HTTPException(404, f"Conversation {cid} not found")
        return json.loads(p.read_text(encoding="utf-8"))

    def save(self, data: dict) -> None:
        p = self._path(data["id"])
        data["updated_at"] = datetime.utcnow().isoformat()
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def delete(self, cid: str) -> None:
        p = self._path(cid)
        if p.exists():
            p.unlink()
        self._cores.pop(cid, None)

    def rename(self, cid: str, new_title: str) -> dict:
        data = self.load(cid)
        data["title"] = new_title.strip() or "Sans titre"
        self.save(data)
        return data

    def create(self) -> dict:
        cid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        data = {
            "id": cid,
            "title": "Nouvelle conversation",
            "created_at": now,
            "updated_at": now,
            "messages": [],
            "memory_state": SerenaCore().memory.to_json(),
            "final_score": 0.0,
            "final_action": "NORMAL",
        }
        self.save(data)
        return data

    def get_core(self, cid: str) -> SerenaCore:
        """Get-or-rehydrate SerenaCore for a conversation."""
        if cid in self._cores:
            return self._cores[cid]
        data = self.load(cid)
        core = SerenaCore()
        memory_state = data.get("memory_state")
        if memory_state:
            try:
                core.memory = SessionMemory.from_json(memory_state)
            except Exception as exc:
                logger.warning("Could not rehydrate memory for %s: %s", cid, exc)
        self._cores[cid] = core
        return core

    def persist_core(self, cid: str) -> None:
        if cid not in self._cores:
            return
        data = self.load(cid)
        core = self._cores[cid]
        data["memory_state"] = core.memory.to_json()
        data["final_score"] = core.memory.cumulative_risk_score
        data["final_action"] = core.memory.current_action
        self.save(data)


store = ConversationStore()

# ──────────────────────────────────────────────────────────────────
# FastAPI
# ──────────────────────────────────────────────────────────────────
app = FastAPI(title="SERENA Web")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(STATIC_DIR / "assets" / "serena-logo.svg")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/api/conversations")
def list_conversations():
    return store.list_meta()


@app.get("/api/conversations/{cid}")
def get_conversation(cid: str):
    return store.load(cid)


@app.delete("/api/conversations/{cid}")
def delete_conversation(cid: str):
    store.delete(cid)
    return {"ok": True}


class RenameBody(BaseModel):
    title: str


@app.post("/api/conversations/{cid}/rename")
def rename_conversation(cid: str, body: RenameBody):
    return store.rename(cid, body.title)


@app.post("/api/conversations/new")
def create_conversation():
    return store.create()


# ──────────────────────────────────────────────────────────────────
# WebSocket
# ──────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    logger.info("WS client connected")
    try:
        while True:
            raw = await ws.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = payload.get("type")
            if msg_type != "message":
                await ws.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})
                continue

            content = (payload.get("content") or "").strip()
            cid = payload.get("conversation_id")
            if not content:
                continue
            if not cid:
                cid = store.create()["id"]
                await ws.send_json({"type": "conversation_created", "conversation_id": cid})

            # auto-title on first user message
            data = store.load(cid)
            is_first = len(data.get("messages", [])) == 0

            await ws.send_json({"type": "thinking", "conversation_id": cid})

            try:
                core = store.get_core(cid)
                result = core.process_message(content)
            except Exception as exc:
                logger.exception("process_message failed")
                await ws.send_json({"type": "error", "message": str(exc)})
                continue

            now = datetime.utcnow().isoformat()
            data = store.load(cid)
            data["messages"].append({
                "role": "user",
                "content": content,
                "timestamp": now,
            })
            data["messages"].append({
                "role": "assistant",
                "content": result["response"],
                "timestamp": now,
                "score": result["score"],
                "action": result["action"],
                "signals": result["signals"],
                "should_notify": result["should_notify"],
                "pass1_raw": result["pass1_raw"],
            })
            if is_first:
                title = content.strip().replace("\n", " ")
                data["title"] = (title[:60] + "…") if len(title) > 60 else title
            data["final_score"] = result["score"]
            data["final_action"] = result["action"]
            data["memory_state"] = core.memory.to_json()
            store.save(data)

            await ws.send_json({
                "type": "response",
                "conversation_id": cid,
                "title": data["title"],
                "content": result["response"],
                "score": result["score"],
                "action": result["action"],
                "signals": result["signals"],
                "score_history": result["score_history"],
                "should_notify": result["should_notify"],
                "probable_condition": core.memory.probable_condition,
                "confidence": core.memory.confidence,
                "pass1_raw": result["pass1_raw"],
            })

    except WebSocketDisconnect:
        logger.info("WS client disconnected")
    except Exception as exc:
        logger.exception("WS error: %s", exc)
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
