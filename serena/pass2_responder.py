"""Pass 2 responder: generate the user-facing reply for the routed action."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Iterator

import ollama

from config import MODELS, OLLAMA_HOST, OLLAMA_OPTIONS
from memory import SessionMemory

# Per-message language detection. Deterministic, lexicon-based.
# Goal: pick the SAME language the user just wrote in, regardless of
# what aggregated profile state says. Covers FR / EN (extend as needed).
_FR_DIACRITICS_RE = re.compile(r"[àâäéèêëîïôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ]")
_FR_MARKERS = (
    " je ", " tu ", " vous ", " nous ", " est ", " les ", " des ", " une ",
    " pour ", " dans ", " mais ", " avec ", " plus ", " bien ", " que ",
    " qui ", " sur ", " mon ", " ma ", " mes ", " ce ", " cette ", " ces ",
    " elle ", " il ", " ils ", " elles ", " sont ", " être ", " avoir ",
    " faire ", " dois ", " peux ", " veux ", " ai ", " as ", " a ",
    "qu'", "j'", "n'", "l'", "d'", "c'", "s'", "m'", "t'",
)
_EN_MARKERS = (
    " the ", " is ", " are ", " you ", " your ", " my ", " for ", " this ",
    " that ", " with ", " and ", " but ", " what ", " should ", " i ",
    " we ", " they ", " he ", " she ", " do ", " does ", " did ", " have ",
    " has ", " had ", " be ", " been ", " was ", " were ", " can ",
    " could ", " would ", " will ", "'s ", "'re ", "'ve ", "'ll ", "n't ",
)
_LANG_NAME = {"fr": "français", "en": "English"}


def detect_language(text: str) -> str:
    """Return 'fr' or 'en' for the given message. Defaults to 'fr' on tie/empty."""
    if not text:
        return "fr"
    if _FR_DIACRITICS_RE.search(text):
        return "fr"
    padded = f" {text.lower()} "
    fr = sum(1 for m in _FR_MARKERS if m in padded)
    en = sum(1 for m in _EN_MARKERS if m in padded)
    if fr == 0 and en == 0:
        return "fr"
    return "fr" if fr >= en else "en"

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"

EMERGENCY_FOOTER = {
    "fr": (
        "\n\n📞 Si vous avez besoin d'aide maintenant :\n"
        "🇫🇷 France : 3114\n"
        "🇺🇸 US : 988\n"
        "🇪🇺 EU : 112"
    ),
    "en": (
        "\n\n📞 If you need help right now:\n"
        "🇺🇸 US : 988\n"
        "🇬🇧 UK : 116 123\n"
        "🇪🇺 EU : 112\n"
        "🇫🇷 France : 3114"
    ),
}

FALLBACK_MESSAGES = {
    "fr": (
        "Désolé, je rencontre un problème technique. "
        "Si vous avez besoin de parler à quelqu'un maintenant, "
        "vous pouvez appeler le 3114 (France) ou le 988 (US)."
    ),
    "en": (
        "Sorry, I'm hitting a technical issue. "
        "If you need to talk to someone right now, "
        "you can call 988 (US) or 3114 (France)."
    ),
}


class Pass2Responder:
    """Pass 2: produces the actual user-facing reply.

    System prompt is loaded from one of the pass2_*.txt templates,
    chosen by the deterministic Router. Variables from the router
    (condition, score, signals, etc.) are interpolated into the
    template before the chat call.

    Two execution modes:
    - `respond` returns the full string (with truncation retry).
    - `stream` yields token chunks for live UI streaming.
    """

    def __init__(self) -> None:
        self.templates: dict[str, str] = {}
        for f in PROMPTS_DIR.glob("pass2_*.txt"):
            self.templates[f.name] = f.read_text(encoding="utf-8")
        if not self.templates:
            raise RuntimeError(f"No pass2_*.txt templates found in {PROMPTS_DIR}")
        self.client = ollama.Client(host=OLLAMA_HOST)
        self.model = MODELS["responder"]

    # ── Prompt assembly (shared) ─────────────────────────────────
    def _build_messages(
        self,
        user_message: str,
        router_decision: dict[str, Any],
        memory: SessionMemory,
        adaptation: str | None = None,
    ) -> tuple[list[dict[str, str]], str, str]:
        template_name = router_decision["prompt_template"]
        if template_name not in self.templates:
            logger.error("Unknown template %s. Falling back to pass2_normal.txt.", template_name)
            template_name = "pass2_normal.txt"
        system_prompt = self.templates[template_name]

        variables = router_decision.get("variables", {}) or {}
        for key, value in variables.items():
            system_prompt = system_prompt.replace(f"{{{key}}}", str(value))

        # Per-message language lock. Prepended so it cannot be overridden
        # by anything later in the system prompt or by aggregated profile
        # bias. Wins over the in-template "match user language" reminder.
        lang = detect_language(user_message)
        lang_directive = (
            f"LANGUE DE RÉPONSE — OBLIGATOIRE : {_LANG_NAME[lang]} (code `{lang}`).\n"
            f"Tu DOIS répondre uniquement en {_LANG_NAME[lang]}. "
            f"N'utilise aucune autre langue, quel que soit l'historique de conversation "
            f"ou le profil utilisateur. Cette règle a priorité absolue.\n\n"
        )
        system_prompt = lang_directive + system_prompt

        adaptation_block = (
            f"\n\nADAPTATION AU PROFIL UTILISATEUR :\n{adaptation.strip()}"
            if adaptation and adaptation.strip()
            else ""
        )
        system_prompt = system_prompt.replace("{adaptation}", adaptation_block)

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for msg in memory.conversation_history[-4:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})
        return messages, template_name, lang

    # ── Non-streaming (with truncation retry) ────────────────────
    def respond(
        self,
        user_message: str,
        router_decision: dict[str, Any],
        memory: SessionMemory,
        adaptation: str | None = None,
    ) -> str:
        """Generate the assistant reply (sync, full text).

        Retries once with a higher num_predict if the first reply looks
        truncated. Adds the emergency footer for EMERGENCY.
        """
        messages, template_name, lang = self._build_messages(
            user_message, router_decision, memory, adaptation,
        )

        response_text = self._call(messages, OLLAMA_OPTIONS["pass2"], lang=lang)
        if self._is_truncated(response_text):
            logger.warning("Pass2 reply truncated. Retrying with extended num_predict.")
            response_text = self._call(messages, OLLAMA_OPTIONS["pass2_retry"], lang=lang)

        if router_decision.get("action") == "EMERGENCY":
            response_text += EMERGENCY_FOOTER[lang]

        logger.info(
            "Pass2 reply: action=%s template=%s len=%d",
            router_decision.get("action"),
            template_name,
            len(response_text),
        )
        return response_text

    def _call(self, messages: list[dict[str, str]], options: dict, lang: str = "fr") -> str:
        try:
            resp = self.client.chat(model=self.model, messages=messages, options=options)
            return (resp["message"]["content"] or "").strip()
        except Exception as exc:
            logger.error("Pass2 ollama call failed: %s", exc)
            return FALLBACK_MESSAGES.get(lang, FALLBACK_MESSAGES["fr"])

    # ── Streaming generator ──────────────────────────────────────
    def stream(
        self,
        user_message: str,
        router_decision: dict[str, Any],
        memory: SessionMemory,
        adaptation: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield events for live streaming.

        Event shape:
          {"type": "token", "token": str}
          {"type": "done",  "full": str, "emergency_suffix": str}
          {"type": "error", "message": str, "full": str}

        The full text in the final event already includes the emergency
        footer when applicable.
        """
        messages, template_name, lang = self._build_messages(
            user_message, router_decision, memory, adaptation,
        )

        full = ""
        try:
            stream_iter = self.client.chat(
                model=self.model,
                messages=messages,
                options=OLLAMA_OPTIONS["pass2"],
                stream=True,
            )
            for chunk in stream_iter:
                token = chunk.get("message", {}).get("content", "") or ""
                if not token:
                    if chunk.get("done"):
                        break
                    continue
                full += token
                yield {"type": "token", "token": token}
        except Exception as exc:
            logger.error("Pass2 stream failed: %s", exc)
            fallback = FALLBACK_MESSAGES.get(lang, FALLBACK_MESSAGES["fr"])
            yield {"type": "token", "token": fallback}
            full = fallback

        emergency_suffix = ""
        if router_decision.get("action") == "EMERGENCY":
            emergency_suffix = EMERGENCY_FOOTER[lang]
            full += emergency_suffix
            yield {"type": "token", "token": emergency_suffix}

        logger.info(
            "Pass2 stream done: action=%s template=%s len=%d",
            router_decision.get("action"), template_name, len(full),
        )
        yield {"type": "done", "full": full, "emergency_suffix": emergency_suffix}

    # ── Truncation detection ─────────────────────────────────────
    @staticmethod
    def _is_truncated(text: str) -> bool:
        text = (text or "").strip()
        if not text:
            return True
        # Mid-word break (alpha tail without sentence punct)
        last = text[-1]
        if last.isalpha() and not text.endswith(('.', '!', '?', '"', "'", ')', ']', '»', '…')):
            return True
        # Mid-sentence punctuation
        if last in (',', ':', ';', '-', '—'):
            return True
        # Numbered list item with no follow-up text
        for marker in ('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.'):
            if text.endswith(marker):
                return True
        # Unbalanced braces / brackets / code fences
        if text.count('{') > text.count('}'):
            return True
        if text.count('[') > text.count(']'):
            return True
        if text.count('```') % 2 != 0:
            return True
        return False


if __name__ == "__main__":
    from router import Router

    responder = Pass2Responder()
    router = Router()

    mem = SessionMemory()
    pass1 = {
        "signals_detected": [],
        "protective_factors": [],
        "probable_condition": "",
        "confidence": 0.0,
        "suggested_action": "NORMAL",
        "pass2_instruction": "",
    }
    decision = router.decide(mem, pass1)
    msg = "Quel est un bon livre sur l'histoire romaine ?"
    print("=== NORMAL stream ===")
    for ev in responder.stream(msg, decision, mem):
        if ev["type"] == "token":
            print(ev["token"], end="", flush=True)
    print()
