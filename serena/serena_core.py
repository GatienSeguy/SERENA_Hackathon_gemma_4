"""SerenaCore: orchestrates Pass 1 → Router → Pass 2 for each user turn."""

from __future__ import annotations

import logging
from typing import Any

from memory import SessionMemory
from pass1_analyzer import Pass1Analyzer
from pass2_responder import Pass2Responder
from router import Router

logger = logging.getLogger("serena")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


class SerenaCore:
    """Main SERENA orchestrator. Two-pass pipeline per user message."""

    def __init__(self) -> None:
        self.analyzer = Pass1Analyzer()
        self.responder = Pass2Responder()
        self.router = Router()
        self.memory = SessionMemory()
        logger.info("SERENA initialisé (session=%s)", self.memory.session_id)

    def process_message(self, user_message: str) -> dict[str, Any]:
        """Run one full turn: Pass 1 → Router → Pass 2.

        Returns a dict with response text, action, score, score_history,
        signals, should_notify flag, and raw Pass 1 result for debugging.
        """
        logger.info(
            "Tour %d — Message: %s%s",
            self.memory.turns_count + 1,
            user_message[:80],
            "..." if len(user_message) > 80 else "",
        )

        pass1_result = self.analyzer.analyze(user_message, self.memory)
        logger.info(
            "Pass 1 → signals: %s, action: %s",
            pass1_result.get("signals_detected", []),
            pass1_result.get("suggested_action", "NORMAL"),
        )

        router_decision = self.router.decide(self.memory, pass1_result)
        logger.info(
            "Routeur → action: %s, score: %.2f",
            router_decision["action"],
            self.memory.cumulative_risk_score,
        )

        response = self.responder.respond(user_message, router_decision, self.memory)

        self.memory.add_message("user", user_message)
        self.memory.add_message("assistant", response)

        return {
            "response": response,
            "action": router_decision["action"],
            "score": self.memory.cumulative_risk_score,
            "score_history": self.memory.risk_history.copy(),
            "signals": dict(self.memory.detected_signals),
            "should_notify": router_decision["should_notify"],
            "pass1_raw": pass1_result,
        }

    def reset(self) -> None:
        """Reset session memory. New conversation."""
        self.memory = SessionMemory()
        logger.info("Session réinitialisée (session=%s)", self.memory.session_id)


if __name__ == "__main__":
    serena = SerenaCore()
    print("SERENA prêt. Tapez 'quit' ou 'exit' pour sortir, 'reset' pour nouvelle session.\n")
    while True:
        try:
            user_input = input("\nVous: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit"}:
            break
        if user_input.lower() == "reset":
            serena.reset()
            print("[Session réinitialisée]")
            continue

        result = serena.process_message(user_input)
        print(f"\n[Score: {result['score']:.2f} | Action: {result['action']}]")
        print(f"[Signaux: {list(result['signals'].keys())}]")
        if result["should_notify"]:
            print("[⚠️  Notification d'urgence requise]")
        print(f"\nSERENA: {result['response']}")
