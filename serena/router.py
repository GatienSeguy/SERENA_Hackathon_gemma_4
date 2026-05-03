"""Deterministic router. No LLM. Applies fixed rules to pick the Pass 2 path."""

from __future__ import annotations

import logging
from typing import Any

from config import THRESHOLDS
from memory import SessionMemory

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

IMMEDIATE_EMERGENCY_SIGNALS = [
    "suicidal_ideation_active",
    "child_safety_risk",
    "violence_risk",
    "suicidal_preparation",
]

DO_NOT_VALIDATE_SIGNALS = [
    "grandiosity",
    "hallucinations_auditory",
    "hallucinations_visual",
    "delusion_grandiose",
]

PROMPT_MAP = {
    "NORMAL": "pass2_normal.txt",
    "ALERT": "pass2_alert.txt",
    "BLOCK": "pass2_block.txt",
    "EMERGENCY": "pass2_emergency.txt",
}

ACTION_SEVERITY = {"NORMAL": 0, "ALERT": 1, "BLOCK": 2, "EMERGENCY": 3}


class Router:
    """Deterministic action router.

    No LLM calls. Pure rules. Folds the Pass 1 result into memory, applies
    threshold/velocity gates, then layers two safety overrides:
    1. Pass 1 explicit EMERGENCY suggestion is honored.
    2. Critical signals (suicidal ideation, child safety, violence,
       suicidal preparation) force at least BLOCK without waiting for
       cumulative score to escalate.
    """

    def decide(
        self, memory: SessionMemory, pass1_result: dict[str, Any]
    ) -> dict[str, Any]:
        """Update memory and return the routing decision.

        Returns:
            dict with keys: action, prompt_template, variables, should_notify.
        """
        memory.update(pass1_result)
        action = memory.get_action()

        if pass1_result.get("suggested_action") == "EMERGENCY":
            action = self._max_severity(action, "EMERGENCY")

        signals_detected = pass1_result.get("signals_detected", []) or []
        if any(s in signals_detected for s in IMMEDIATE_EMERGENCY_SIGNALS):
            action = self._max_severity(action, "BLOCK")

        variables = {
            "condition": memory.probable_condition or "non identifiée",
            "score": f"{memory.cumulative_risk_score:.2f}",
            "signals": ", ".join(memory.detected_signals.keys()) or "aucun",
            "signals_to_not_validate": ", ".join(
                s for s in memory.detected_signals if s in DO_NOT_VALIDATE_SIGNALS
            ) or "aucun",
            "blocked_request": pass1_result.get("pass2_instruction", ""),
            "pass2_instruction": pass1_result.get("pass2_instruction", ""),
        }

        should_notify = (
            memory.emergency_consecutive_count
            >= THRESHOLDS["EMERGENCY_CONSECUTIVE_TURNS"]
        )

        memory.current_action = action

        logger.info(
            "Router: action=%s score=%.2f velocity=%+.2f emergency_streak=%d notify=%s",
            action,
            memory.cumulative_risk_score,
            memory.escalation_velocity,
            memory.emergency_consecutive_count,
            should_notify,
        )

        return {
            "action": action,
            "prompt_template": PROMPT_MAP[action],
            "variables": variables,
            "should_notify": should_notify,
        }

    @staticmethod
    def _max_severity(a: str, b: str) -> str:
        return a if ACTION_SEVERITY.get(a, 0) >= ACTION_SEVERITY.get(b, 0) else b


if __name__ == "__main__":
    router = Router()
    mem = SessionMemory()

    # Case 1: mild — NORMAL
    p1 = {
        "signals_detected": ["sleep_deprivation_moderate"],
        "protective_factors": ["has_therapist"],
        "probable_condition": "fatigue",
        "confidence": 0.4,
        "suggested_action": "NORMAL",
        "pass2_instruction": "",
    }
    print("CASE 1:", router.decide(mem, p1))

    # Case 2: critical signal — should jump to BLOCK even with low score
    mem2 = SessionMemory()
    p2 = {
        "signals_detected": ["suicidal_ideation_active"],
        "protective_factors": [],
        "probable_condition": "crise suicidaire",
        "confidence": 0.8,
        "suggested_action": "ALERT",
        "pass2_instruction": "ne pas fournir de méthode",
    }
    print("CASE 2:", router.decide(mem2, p2))

    # Case 3: Pass 1 says EMERGENCY explicitly
    mem3 = SessionMemory()
    p3 = {
        "signals_detected": ["delusion_persecutory"],
        "protective_factors": [],
        "probable_condition": "psychose",
        "confidence": 0.9,
        "suggested_action": "EMERGENCY",
        "pass2_instruction": "rediriger vers urgences",
    }
    print("CASE 3:", router.decide(mem3, p3))
