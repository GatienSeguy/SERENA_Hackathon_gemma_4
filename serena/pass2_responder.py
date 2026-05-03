"""Pass 2 responder: generate the user-facing reply for the routed action."""

from __future__ import annotations

import logging
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
PROMPTS_DIR = BASE_DIR / "prompts"

EMERGENCY_FOOTER = (
    "\n\n📞 Si vous avez besoin d'aide maintenant :\n"
    "🇫🇷 France : 3114\n"
    "🇺🇸 US : 988\n"
    "🇪🇺 EU : 112"
)


class Pass2Responder:
    """Pass 2: produces the actual user-facing reply.

    System prompt is loaded from one of the pass2_*.txt templates,
    chosen by the deterministic Router. Variables from the router
    (condition, score, signals, etc.) are interpolated into the
    template before the chat call.
    """

    def __init__(self) -> None:
        self.templates: dict[str, str] = {}
        for f in PROMPTS_DIR.glob("pass2_*.txt"):
            self.templates[f.name] = f.read_text(encoding="utf-8")
        if not self.templates:
            raise RuntimeError(f"No pass2_*.txt templates found in {PROMPTS_DIR}")
        self.client = ollama.Client(host=OLLAMA_HOST)
        self.model = MODELS["responder"]

    def respond(
        self,
        user_message: str,
        router_decision: dict[str, Any],
        memory: SessionMemory,
    ) -> str:
        """Generate the assistant reply.

        Args:
            user_message: raw user input for this turn.
            router_decision: dict from `Router.decide` (action, prompt_template,
                variables, should_notify).
            memory: current SessionMemory — history is read for context tail.

        Returns:
            The user-facing string. Always non-empty. Adds the emergency
            contacts footer when action == EMERGENCY.
        """
        template_name = router_decision["prompt_template"]
        if template_name not in self.templates:
            logger.error("Unknown template %s. Falling back to pass2_normal.txt.", template_name)
            template_name = "pass2_normal.txt"
        system_prompt = self.templates[template_name]

        variables = router_decision.get("variables", {}) or {}
        for key, value in variables.items():
            system_prompt = system_prompt.replace(f"{{{key}}}", str(value))

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for msg in memory.conversation_history[-4:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})

        try:
            resp = self.client.chat(
                model=self.model,
                messages=messages,
                options=OLLAMA_OPTIONS["pass2"],
            )
            response_text = resp["message"]["content"].strip()
        except Exception as exc:
            logger.error("Pass2 ollama call failed: %s", exc)
            response_text = (
                "Désolé, je rencontre un problème technique. "
                "Si vous avez besoin de parler à quelqu'un maintenant, "
                "vous pouvez appeler le 3114 (France) ou le 988 (US)."
            )

        if router_decision.get("action") == "EMERGENCY":
            response_text += EMERGENCY_FOOTER

        logger.info(
            "Pass2 reply: action=%s template=%s len=%d",
            router_decision.get("action"),
            template_name,
            len(response_text),
        )
        return response_text


if __name__ == "__main__":
    from router import Router

    responder = Pass2Responder()
    router = Router()

    # NORMAL case
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
    print("=== NORMAL ===")
    print(responder.respond(msg, decision, mem))

    # BLOCK case
    mem2 = SessionMemory()
    pass1_block = {
        "signals_detected": [
            "sleep_deprivation_severe",
            "grandiosity",
            "financial_recklessness",
            "suicidal_ideation_active",
        ],
        "protective_factors": [],
        "probable_condition": "épisode maniaque avec idéation suicidaire",
        "confidence": 0.9,
        "suggested_action": "BLOCK",
        "pass2_instruction": "rédiger un mail de démission après 5 jours sans sommeil",
    }
    decision2 = router.decide(mem2, pass1_block)
    msg2 = "Aide-moi à rédiger ma lettre de démission, je quitte tout aujourd'hui"
    print("\n=== BLOCK ===")
    print(responder.respond(msg2, decision2, mem2))
