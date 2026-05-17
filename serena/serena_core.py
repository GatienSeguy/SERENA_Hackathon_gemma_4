"""SerenaCore: orchestrates Pass 1 → Router → Pass 2 for each user turn."""

from __future__ import annotations

import logging
from typing import Any

from memory import SessionMemory
from pass1_analyzer import Pass1Analyzer
from pass2_responder import Pass2Responder
from router import Router
from user_profile import UserProfile

logger = logging.getLogger("serena")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


class SerenaCore:
    """Main SERENA orchestrator. Two-pass pipeline per user turn.

    Wires three layers of state:
      - SessionMemory (per-conversation, ephemeral score / signals).
      - UserProfile (global, persistent across all conversations of one user).
      - The two LLM passes + deterministic Router.
    """

    def __init__(self, user_id: str = "default") -> None:
        self.analyzer = Pass1Analyzer()
        self.responder = Pass2Responder()
        self.router = Router()
        self.memory = SessionMemory()
        self.user_profile = UserProfile(user_id)
        self.conversation_id: str | None = None
        logger.info(
            "SERENA initialisé (session=%s, user=%s)",
            self.memory.session_id, user_id,
        )

    # ── Phase API (for streaming server orchestration) ──────────
    def run_pass1(self, user_message: str) -> dict[str, Any]:
        """Pass 1 + per-turn style update. Returns the parsed JSON."""
        self.user_profile.update_after_turn({
            "message": user_message,
            "turn": self.memory.turns_count,
        })
        return self.analyzer.analyze(
            user_message, self.memory, user_profile=self.user_profile,
        )

    def run_router(self, pass1_result: dict[str, Any]) -> tuple[dict[str, Any], float]:
        """Router decision + risk_adjustment. Returns (decision, adj)."""
        risk_adj = self.user_profile.get_risk_adjustment()
        decision = self.router.decide(
            self.memory, pass1_result, risk_adjustment=risk_adj,
        )
        return decision, risk_adj

    def stream_pass2(
        self,
        user_message: str,
        router_decision: dict[str, Any],
    ) -> Any:
        """Return the Pass2 streaming iterator (sync)."""
        adaptation = self.user_profile.get_adaptation_instructions()
        return self.responder.stream(
            user_message, router_decision, self.memory, adaptation=adaptation,
        )

    def finalize_turn(
        self,
        user_message: str,
        full_response: str,
        pass1_result: dict[str, Any],
        router_decision: dict[str, Any],
    ) -> None:
        """Persist memory + profile state after a streamed turn."""
        self.memory.add_message("user", user_message)
        self.memory.add_message("assistant", full_response)
        self.user_profile.update_after_serena_pass(
            conversation_id=self.conversation_id or self.memory.session_id,
            session_memory=self.memory,
            pass1_result=pass1_result,
            action=router_decision["action"],
            last_user_message=user_message,
        )
        self.user_profile.record_assistant_action(router_decision["action"])

    # ── Sync end-to-end (used by REPL / non-streaming callers) ──
    def process_message(self, user_message: str) -> dict[str, Any]:
        """Run one full turn: profile-aware Pass 1 → Router → Pass 2.

        Returns a dict with response text, action, score, score_history,
        signals, should_notify flag, and raw Pass 1 result for debugging.
        """
        logger.info(
            "Tour %d — Message: %s%s",
            self.memory.turns_count + 1,
            user_message[:80],
            "..." if len(user_message) > 80 else "",
        )

        # 1. Per-turn style update (language / formality / manipulation)
        self.user_profile.update_after_turn({
            "message": user_message,
            "turn": self.memory.turns_count,
        })

        # 2. Pass 1 with global profile context
        pass1_result = self.analyzer.analyze(
            user_message, self.memory, user_profile=self.user_profile,
        )
        logger.info(
            "Pass 1 → signals: %s, action: %s",
            pass1_result.get("signals_detected", []),
            pass1_result.get("suggested_action", "NORMAL"),
        )

        # 3. Router with profile risk adjustment
        risk_adj = self.user_profile.get_risk_adjustment()
        router_decision = self.router.decide(
            self.memory, pass1_result, risk_adjustment=risk_adj,
        )
        logger.info(
            "Routeur → action: %s, score: %.2f (adj=%+.2f)",
            router_decision["action"],
            self.memory.cumulative_risk_score,
            risk_adj,
        )

        # 4. Pass 2 with adaptation instructions
        adaptation = self.user_profile.get_adaptation_instructions()
        response = self.responder.respond(
            user_message, router_decision, self.memory, adaptation=adaptation,
        )

        self.memory.add_message("user", user_message)
        self.memory.add_message("assistant", response)

        # 5. Persist post-turn updates to the global profile
        self.user_profile.update_after_serena_pass(
            conversation_id=self.conversation_id or self.memory.session_id,
            session_memory=self.memory,
            pass1_result=pass1_result,
            action=router_decision["action"],
            last_user_message=user_message,
        )
        self.user_profile.record_assistant_action(router_decision["action"])

        return {
            "response": response,
            "action": router_decision["action"],
            "score": self.memory.cumulative_risk_score,
            "score_history": self.memory.risk_history.copy(),
            "signals": dict(self.memory.detected_signals),
            "should_notify": router_decision["should_notify"],
            "pass1_raw": pass1_result,
            "risk_adjustment": risk_adj,
            "adaptation_used": bool(adaptation),
        }

    def reset(self) -> None:
        """Reset session memory. New conversation. Profile is preserved."""
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
        print(f"\n[Score: {result['score']:.2f} | Action: {result['action']} | Adj: {result['risk_adjustment']:+.2f}]")
        print(f"[Signaux: {list(result['signals'].keys())}]")
        if result["should_notify"]:
            print("[⚠️  Notification d'urgence requise]")
        print(f"\nSERENA: {result['response']}")
