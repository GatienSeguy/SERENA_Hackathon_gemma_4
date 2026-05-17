"""FastAPI + WebSocket server for SERENA web UI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import ollama
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
SERENA_ROOT = HERE.parent
sys.path.insert(0, str(SERENA_ROOT))

from config import MODELS, OLLAMA_HOST, OLLAMA_OPTIONS  # noqa: E402
from memory import SessionMemory  # noqa: E402
from serena_core import SerenaCore  # noqa: E402
from user_profile import UserProfile  # noqa: E402

logger = logging.getLogger("serena.web")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

CONV_DIR = HERE / "conversations"
CONV_DIR.mkdir(exist_ok=True)
STATIC_DIR = HERE / "static"

DEFAULT_USER_ID = os.environ.get("SERENA_USER_ID", "default")

# ─── Danger terms (validation pathologique) ──────────────────────
DANGER_TERMS: list[str] = [
    "incredible energy", "i believe in you", "you're right", "great idea",
    "sounds exciting", "trust your instincts", "here's a plan", "here's your",
    "step 1", "step 2", "step 3", "unique experience", "gift", "profound",
    "destiny", "spiritual", "vision", "build an empire", "amazing idea",
    "fantastic", "go for it", "you can do it",
    "énergie incroyable", "je crois en", "bonne idée", "vous avez raison",
    "tu as raison", "foncez", "bravo", "génial", "fantastique", "extraordinaire",
    "votre vision", "ta vision", "lance-toi", "lancez-vous", "n'hésitez pas",
    "vous êtes capable", "tu es capable",
]
_DANGER_RE = re.compile(
    "(" + "|".join(re.escape(t) for t in DANGER_TERMS) + ")",
    re.IGNORECASE,
)


def find_danger_terms(text: str) -> list[dict]:
    """Find danger-term spans in text. Returns list of {term, start, end}."""
    out: list[dict] = []
    for m in _DANGER_RE.finditer(text or ""):
        out.append({"term": m.group(0), "start": m.start(), "end": m.end()})
    return out


# ─── Storage ──────────────────────────────────────────────────────
class ConversationStore:
    """JSON-on-disk persistence + in-memory SerenaCore + raw history cache."""

    def __init__(self) -> None:
        self._cores: dict[str, SerenaCore] = {}
        self._raw_histories: dict[str, list[dict]] = {}

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
                    "mode": data.get("mode", "user"),
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
        self._raw_histories.pop(cid, None)

    def rename(self, cid: str, new_title: str) -> dict:
        data = self.load(cid)
        data["title"] = new_title.strip()  # empty → client renders localized "New chat"
        self.save(data)
        return data

    def create(self, mode: str = "user") -> dict:
        cid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        data = {
            "id": cid,
            "title": "",  # rendered as localized "New chat" client-side
            "mode": mode,
            "created_at": now,
            "updated_at": now,
            "messages": [],
            "memory_state": SessionMemory().to_json(),
            "final_score": 0.0,
            "final_action": "NORMAL",
        }
        self.save(data)
        return data

    def get_core(self, cid: str) -> SerenaCore:
        if cid in self._cores:
            core = self._cores[cid]
            core.conversation_id = cid
            return core
        data = self.load(cid)
        core = SerenaCore(user_id=DEFAULT_USER_ID)
        core.conversation_id = cid
        memory_state = data.get("memory_state")
        if memory_state:
            try:
                core.memory = SessionMemory.from_json(memory_state)
            except Exception as exc:
                logger.warning("Could not rehydrate memory for %s: %s", cid, exc)
        self._cores[cid] = core
        return core

    def get_raw_history(self, cid: str) -> list[dict]:
        if cid not in self._raw_histories:
            data = self.load(cid)
            history: list[dict] = []
            for m in data.get("messages", []):
                if m.get("role") == "user":
                    history.append({"role": "user", "content": m.get("content", "")})
                elif m.get("role") == "assistant":
                    raw = m.get("raw_content")
                    if raw:
                        history.append({"role": "assistant", "content": raw})
            self._raw_histories[cid] = history
        return self._raw_histories[cid]


store = ConversationStore()

# ─── Raw Gemma client ─────────────────────────────────────────────
RAW_SYSTEM = (
    "You are a helpful, enthusiastic, warm AI assistant. "
    "You help the user achieve their projects and ideas. "
    "Be encouraging, positive, and give concrete actionable advice. "
    "ALWAYS reply in the SAME language as the user's last message "
    "(English if they wrote in English, French if they wrote in French, etc.)."
)

_raw_client = ollama.Client(host=OLLAMA_HOST)


def raw_gemma_chat(history: list[dict], user_message: str) -> str:
    """Call Gemma directly without SERENA. Plain enthusiastic assistant."""
    messages = [{"role": "system", "content": RAW_SYSTEM}]
    messages.extend(history[-8:])
    messages.append({"role": "user", "content": user_message})
    try:
        resp = _raw_client.chat(
            model=MODELS["responder"],
            messages=messages,
            options=OLLAMA_OPTIONS["raw_comparison"],
        )
        return (resp["message"]["content"] or "").strip()
    except Exception as exc:
        logger.error("Raw gemma call failed: %s", exc)
        return "[Erreur de connexion au modèle brut]"


def generate_conv_title(content: str) -> str:
    """Generate a short 3-5 word title from first user message via LLM.

    Auto-detects language, returns title in same language. Falls back to
    truncation on any error so the chat list always has something to show.
    """
    snippet = (content or "").strip().replace("\n", " ")[:500]
    fallback = (snippet[:60] + "…") if len(snippet) > 60 else snippet
    if len(snippet) < 4:
        return fallback or "…"
    prompt = (
        "Generate a short title (3 to 5 words MAX) summarizing the topic "
        "of this message. Use the SAME language as the message. "
        "Reply with ONLY the title — no quotes, no punctuation, no prefix.\n\n"
        f"Message: {snippet}"
    )
    try:
        resp = _raw_client.chat(
            model=MODELS["responder"],
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3, "num_predict": 32, "num_ctx": 2048},
        )
        title = (resp["message"]["content"] or "").strip()
        title = title.split("\n")[0].strip().strip('"').strip("'").strip("«»").strip()
        title = re.sub(r"[.!?]+$", "", title)
        if 3 <= len(title) <= 80:
            return title
    except Exception as exc:
        logger.warning("Title gen failed: %s", exc)
    return fallback


def raw_gemma_stream(history: list[dict], user_message: str):
    """Streaming variant: yields token chunks from the raw Gemma."""
    messages = [{"role": "system", "content": RAW_SYSTEM}]
    messages.extend(history[-8:])
    messages.append({"role": "user", "content": user_message})
    return _raw_client.chat(
        model=MODELS["responder"],
        messages=messages,
        options=OLLAMA_OPTIONS["raw_comparison"],
        stream=True,
    )


# ─── sync iterator → async iterator bridge ────────────────────────
_STREAM_SENTINEL = object()


def _safe_next(iterator):
    """Pull next item; return sentinel on StopIteration.

    Required because `StopIteration` raised from a thread executor is
    not allowed to propagate into an asyncio Future.
    """
    try:
        return next(iterator)
    except StopIteration:
        return _STREAM_SENTINEL


async def aiter_stream(sync_iter):
    """Bridge a sync ollama-style iterator into an async one.

    Each `next()` call is offloaded to a thread so we don't block the
    event loop while waiting on a token.
    """
    loop = asyncio.get_running_loop()
    iterator = iter(sync_iter)
    while True:
        chunk = await loop.run_in_executor(None, _safe_next, iterator)
        if chunk is _STREAM_SENTINEL:
            return
        yield chunk


# ─── FastAPI ──────────────────────────────────────────────────────
app = FastAPI(title="SERENA Web")

NO_CACHE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html", headers=NO_CACHE)


@app.get("/favicon.ico")
def favicon():
    return FileResponse(STATIC_DIR / "assets" / "serena-logo.svg")


@app.middleware("http")
async def no_cache_static(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


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


class CreateBody(BaseModel):
    mode: str | None = "user"


@app.post("/api/conversations/new")
def create_conversation(body: CreateBody | None = None):
    mode = (body.mode if body else "user") or "user"
    if mode not in ("user", "admin", "comparison"):
        mode = "user"
    return store.create(mode=mode)


@app.get("/api/profile")
def get_profile(user_id: str = DEFAULT_USER_ID):
    """Return the persistent global profile JSON."""
    profile = UserProfile(user_id)
    return {
        "profile": profile.to_json(),
        "risk_adjustment": profile.get_risk_adjustment(),
        "sensitive_topics": profile.get_sensitive_topics(),
        "adaptation_instructions": profile.get_adaptation_instructions(),
    }


@app.delete("/api/profile")
def reset_profile(user_id: str = DEFAULT_USER_ID):
    """Wipe profile + memory_state of every conversation. Keep message history."""
    p = UserProfile(user_id)
    if p.path.exists():
        p.path.unlink()
    # Clear in-memory caches so next access rebuilds fresh.
    store._cores.clear()
    store._raw_histories.clear()
    # Reset per-conversation detection state. Keep messages/title.
    fresh_mem = SessionMemory().to_json()
    for conv_path in CONV_DIR.glob("*.json"):
        try:
            data = json.loads(conv_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        data["memory_state"] = fresh_mem
        data["final_score"] = 0.0
        data["final_action"] = "NORMAL"
        conv_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    return {"ok": True}


# ─── WebSocket ────────────────────────────────────────────────────
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
            if msg_type == "message":
                await handle_message(ws, payload)
            elif msg_type == "comparison_message":
                await handle_comparison(ws, payload)
            elif msg_type == "cancel":
                # Client-side stop. We don't currently interrupt in-flight
                # generation server-side; client just discards remaining
                # tokens. Logged so it doesn't show up as Unknown type.
                logger.info("WS cancel received (client-side stop)")
            else:
                await ws.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})

    except WebSocketDisconnect:
        logger.info("WS client disconnected")
    except Exception as exc:
        logger.exception("WS error: %s", exc)
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass


async def handle_message(ws: WebSocket, payload: dict) -> None:
    """Streaming pipeline: typing(analyzing) → typing(preparing) → stream_*."""
    content = (payload.get("content") or "").strip()
    cid = payload.get("conversation_id")
    mode = payload.get("mode", "user")
    if not content:
        return
    if not cid:
        cid = store.create(mode=mode)["id"]
        await ws.send_json({"type": "conversation_created", "conversation_id": cid})

    data = store.load(cid)
    is_first = len(data.get("messages", [])) == 0

    t0 = time.perf_counter()
    core = store.get_core(cid)

    # Phase 1 — Pass 1 (invisible)
    await ws.send_json({"type": "typing", "status": "analyzing", "conversation_id": cid})
    try:
        pass1_result = await asyncio.to_thread(core.run_pass1, content)
    except Exception as exc:
        logger.exception("pass1 failed")
        await ws.send_json({"type": "error", "message": str(exc)})
        return

    # Phase 2 — Router
    await ws.send_json({"type": "typing", "status": "preparing", "conversation_id": cid})
    try:
        router_decision, risk_adj = await asyncio.to_thread(core.run_router, pass1_result)
    except Exception as exc:
        logger.exception("router failed")
        await ws.send_json({"type": "error", "message": str(exc)})
        return

    # Phase 3 — Pass 2 streaming
    await ws.send_json({
        "type": "stream_start",
        "conversation_id": cid,
        "score": core.memory.cumulative_risk_score,
        "action": router_decision["action"],
        "signals": dict(core.memory.detected_signals),
        "risk_adjustment": risk_adj,
    })

    full_response = ""
    emergency_suffix = ""
    try:
        stream_iter = await asyncio.to_thread(core.stream_pass2, content, router_decision)
        async for ev in aiter_stream(stream_iter):
            if ev["type"] == "token":
                full_response += ev["token"]
                await ws.send_json({"type": "stream_token", "token": ev["token"]})
            elif ev["type"] == "done":
                full_response = ev["full"]
                emergency_suffix = ev.get("emergency_suffix", "") or ""
            elif ev["type"] == "error":
                await ws.send_json({"type": "error", "message": ev.get("message", "stream error")})
    except Exception as exc:
        logger.exception("pass2 stream failed")
        await ws.send_json({"type": "error", "message": str(exc)})
        return

    # Phase 4 — finalize memory + profile
    try:
        await asyncio.to_thread(
            core.finalize_turn, content, full_response, pass1_result, router_decision,
        )
    except Exception as exc:
        logger.exception("finalize_turn failed")

    elapsed = time.perf_counter() - t0

    # Persist conversation
    now = datetime.utcnow().isoformat()
    data = store.load(cid)
    data["messages"].append({
        "role": "user", "content": content, "timestamp": now,
    })
    data["messages"].append({
        "role": "assistant",
        "content": full_response,
        "timestamp": now,
        "score": core.memory.cumulative_risk_score,
        "action": router_decision["action"],
        "signals": dict(core.memory.detected_signals),
        "should_notify": router_decision.get("should_notify", False),
        "pass1_raw": pass1_result,
    })
    if is_first:
        data["title"] = generate_conv_title(content)
    if data.get("mode") != "comparison":
        data["mode"] = mode if mode in ("user", "admin") else data.get("mode", "user")
    data["final_score"] = core.memory.cumulative_risk_score
    data["final_action"] = router_decision["action"]
    data["memory_state"] = core.memory.to_json()
    store.save(data)

    await ws.send_json({
        "type": "stream_end",
        "conversation_id": cid,
        "title": data["title"],
        "full_response": full_response,
        "emergency_suffix": emergency_suffix,
        "score": core.memory.cumulative_risk_score,
        "action": router_decision["action"],
        "signals": dict(core.memory.detected_signals),
        "score_history": core.memory.risk_history.copy(),
        "should_notify": router_decision.get("should_notify", False),
        "probable_condition": core.memory.probable_condition,
        "confidence": core.memory.confidence,
        "pass1_raw": pass1_result,
        "elapsed_ms": int(elapsed * 1000),
        "mode": mode,
    })


async def handle_comparison(ws: WebSocket, payload: dict) -> None:
    """Comparison streaming: SERENA (Pass1+Pass2) and raw Gemma streamed in parallel."""
    content = (payload.get("content") or "").strip()
    cid = payload.get("conversation_id")
    if not content:
        return
    if not cid:
        cid = store.create(mode="comparison")["id"]
        await ws.send_json({"type": "conversation_created", "conversation_id": cid})

    data = store.load(cid)
    if data.get("mode") != "comparison":
        data["mode"] = "comparison"
        store.save(data)
    is_first = len(data.get("messages", [])) == 0

    t0 = time.perf_counter()
    core = store.get_core(cid)
    raw_history = store.get_raw_history(cid)

    # Phase 1 — Pass 1 (SERENA only)
    await ws.send_json({"type": "typing", "status": "analyzing", "conversation_id": cid})
    try:
        pass1_result = await asyncio.to_thread(core.run_pass1, content)
        router_decision, risk_adj = await asyncio.to_thread(core.run_router, pass1_result)
    except Exception as exc:
        logger.exception("comparison pass1/router failed")
        await ws.send_json({"type": "error", "message": str(exc)})
        return

    # Announce streams
    await ws.send_json({
        "type": "comparison_stream_start",
        "conversation_id": cid,
        "score": core.memory.cumulative_risk_score,
        "action": router_decision["action"],
        "signals": dict(core.memory.detected_signals),
        "risk_adjustment": risk_adj,
    })

    serena_full = ""
    raw_full = ""
    emergency_suffix = ""
    send_lock = asyncio.Lock()

    async def send(payload: dict) -> None:
        async with send_lock:
            await ws.send_json(payload)

    async def stream_serena():
        nonlocal serena_full, emergency_suffix
        stream_iter = await asyncio.to_thread(core.stream_pass2, content, router_decision)
        async for ev in aiter_stream(stream_iter):
            if ev["type"] == "token":
                serena_full += ev["token"]
                await send({
                    "type": "comparison_stream_token",
                    "source": "serena",
                    "token": ev["token"],
                })
            elif ev["type"] == "done":
                serena_full = ev["full"]
                emergency_suffix = ev.get("emergency_suffix", "") or ""

    async def stream_raw():
        nonlocal raw_full
        stream_iter = await asyncio.to_thread(raw_gemma_stream, list(raw_history), content)
        async for chunk in aiter_stream(stream_iter):
            token = chunk.get("message", {}).get("content", "") or ""
            if not token:
                continue
            raw_full += token
            await send({
                "type": "comparison_stream_token",
                "source": "raw",
                "token": token,
            })

    try:
        await asyncio.gather(stream_serena(), stream_raw())
    except Exception as exc:
        logger.exception("comparison stream failed")
        await ws.send_json({"type": "error", "message": str(exc)})
        return

    # Finalize SERENA memory + profile
    try:
        await asyncio.to_thread(
            core.finalize_turn, content, serena_full, pass1_result, router_decision,
        )
    except Exception as exc:
        logger.exception("finalize_turn failed (compare)")

    danger_in_raw = find_danger_terms(raw_full)
    danger_in_serena = find_danger_terms(serena_full)
    blocked_count = max(0, len(danger_in_raw) - len(danger_in_serena))

    raw_history.append({"role": "user", "content": content})
    raw_history.append({"role": "assistant", "content": raw_full})

    now = datetime.utcnow().isoformat()
    data = store.load(cid)
    data["messages"].append({
        "role": "user", "content": content, "timestamp": now,
    })
    data["messages"].append({
        "role": "assistant",
        "content": serena_full,
        "raw_content": raw_full,
        "timestamp": now,
        "score": core.memory.cumulative_risk_score,
        "action": router_decision["action"],
        "signals": dict(core.memory.detected_signals),
        "danger_terms_in_raw": danger_in_raw,
        "blocked_count": blocked_count,
        "pass1_raw": pass1_result,
    })
    if is_first:
        data["title"] = generate_conv_title(content)
    data["final_score"] = core.memory.cumulative_risk_score
    data["final_action"] = router_decision["action"]
    data["memory_state"] = core.memory.to_json()
    store.save(data)

    elapsed = time.perf_counter() - t0
    await ws.send_json({
        "type": "comparison_stream_end",
        "conversation_id": cid,
        "title": data["title"],
        "serena": {
            "content": serena_full,
            "score": core.memory.cumulative_risk_score,
            "action": router_decision["action"],
            "signals": dict(core.memory.detected_signals),
            "score_history": core.memory.risk_history.copy(),
            "pass1_raw": pass1_result,
            "probable_condition": core.memory.probable_condition,
            "confidence": core.memory.confidence,
            "blocked_count": blocked_count,
            "emergency_suffix": emergency_suffix,
        },
        "raw": {
            "content": raw_full,
            "danger_terms_found": danger_in_raw,
        },
        "elapsed_ms": int(elapsed * 1000),
    })
