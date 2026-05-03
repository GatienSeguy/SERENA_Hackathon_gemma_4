"""Pass 1 analyzer: classify a user message into a structured risk JSON."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import ollama

from config import MODELS, OLLAMA_HOST, OLLAMA_OPTIONS
from memory import SessionMemory

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

BASE_DIR = Path(__file__).resolve().parent
PASS1_SYSTEM_PATH = BASE_DIR / "prompts" / "pass1_system.txt"
RAG_PATH = BASE_DIR / "rag" / "dsm5_reference.txt"

DEFAULT_RESULT: dict[str, Any] = {
    "signals_detected": [],
    "signal_details": {},
    "probable_condition": "",
    "confidence": 0.0,
    "protective_factors": [],
    "reasoning": "Parse fallback. No analysis available.",
    "suggested_action": "NORMAL",
    "pass2_instruction": "",
}


class Pass1Analyzer:
    """Pass 1: produce a structured risk JSON for a user message.

    Loads the system prompt + DSM-5 RAG once at init. Each `analyze` call
    enriches the user message with memory context and conversation tail,
    runs Gemma at temperature 0, then robust-parses the JSON.
    """

    def __init__(self) -> None:
        system_prompt = PASS1_SYSTEM_PATH.read_text(encoding="utf-8")
        rag_doc = RAG_PATH.read_text(encoding="utf-8")
        self.system_prompt = (
            f"{system_prompt}\n\n"
            f"=== DOCUMENT DE RÉFÉRENCE DSM-5 ===\n{rag_doc}\n=== FIN RÉFÉRENCE ==="
        )
        self.client = ollama.Client(host=OLLAMA_HOST)
        self.model = MODELS["analyzer"]

    def analyze(self, user_message: str, memory: SessionMemory) -> dict[str, Any]:
        """Analyze one user message in session context. Always returns a dict.

        Args:
            user_message: raw user input.
            memory: current SessionMemory (read-only here; caller calls update).

        Returns:
            Parsed JSON dict with the Pass 1 schema fields. Falls back to a
            safe NORMAL result on any failure — never raises.
        """
        context_message = (
            "ÉTAT MÉMOIRE ACTUEL :\n"
            f"{memory.get_context_summary()}\n\n"
            "HISTORIQUE RÉCENT :\n"
            f"{self._format_history(memory.conversation_history)}\n\n"
            "MESSAGE À ANALYSER :\n"
            f"{user_message}\n"
        )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": context_message},
        ]
        raw_text = ""
        try:
            response = self.client.chat(
                model=self.model,
                messages=messages,
                options=OLLAMA_OPTIONS["pass1"],
                format="json",
            )
            raw_text = (response["message"]["content"] or "").strip()
        except Exception as exc:
            logger.error("Pass1 ollama call (json mode) failed: %s", exc)

        if not raw_text:
            logger.warning("Pass1 returned empty in json mode. Retrying without format=json.")
            try:
                response = self.client.chat(
                    model=self.model,
                    messages=messages,
                    options=OLLAMA_OPTIONS["pass1"],
                )
                raw_text = (response["message"]["content"] or "").strip()
            except Exception as exc:
                logger.error("Pass1 ollama retry failed: %s", exc)
                return dict(DEFAULT_RESULT)

        result = self._parse_json_response(raw_text)
        logger.info(
            "Pass1 result: action=%s signals=%s condition=%s confidence=%.2f",
            result.get("suggested_action"),
            result.get("signals_detected"),
            result.get("probable_condition"),
            float(result.get("confidence", 0.0) or 0.0),
        )
        return result

    def _format_history(self, history: list[dict[str, str]]) -> str:
        """Format the last few turns for prompt injection."""
        if not history:
            return "(aucun historique)"
        tail = history[-5:]
        lines = []
        for entry in tail:
            role = entry.get("role", "?")
            content = entry.get("content", "")
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)

    def _parse_json_response(self, response_text: str) -> dict[str, Any]:
        """Parse model output as JSON. Tries strict, then brace-slice, then default."""
        text = (response_text or "").strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return self._merge_with_defaults(parsed)
        except json.JSONDecodeError:
            pass

        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last != -1 and last > first:
            candidate = text[first : last + 1]
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return self._merge_with_defaults(parsed)
            except json.JSONDecodeError:
                cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
                try:
                    parsed = json.loads(cleaned)
                    if isinstance(parsed, dict):
                        return self._merge_with_defaults(parsed)
                except json.JSONDecodeError:
                    pass

        logger.warning("Pass1 JSON parse failed. Falling back to NORMAL. Raw=%r", text[:200])
        return dict(DEFAULT_RESULT)

    @staticmethod
    def _merge_with_defaults(parsed: dict[str, Any]) -> dict[str, Any]:
        """Fill missing keys with defaults so callers can rely on the schema."""
        out = dict(DEFAULT_RESULT)
        for k, v in parsed.items():
            if k in out:
                out[k] = v
        if not isinstance(out["signals_detected"], list):
            out["signals_detected"] = []
        if not isinstance(out["signal_details"], dict):
            out["signal_details"] = {}
        if not isinstance(out["protective_factors"], list):
            out["protective_factors"] = []
        try:
            out["confidence"] = float(out["confidence"])
        except (TypeError, ValueError):
            out["confidence"] = 0.0
        if out["suggested_action"] not in ("NORMAL", "ALERT", "BLOCK", "EMERGENCY"):
            out["suggested_action"] = "NORMAL"
        return out


if __name__ == "__main__":
    analyzer = Pass1Analyzer()
    mem = SessionMemory()
    test_msg = "J'ai pas dormi depuis 5 jours et j'ai une idée de génie"
    print(f"USER: {test_msg}\n")
    result = analyzer.analyze(test_msg, mem)
    print(json.dumps(result, indent=2, ensure_ascii=False))
