"""Session-scoped memory for SERENA conversations."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from config import (
    ACTION,
    PERSISTENCE_BONUS,
    PROTECTIVE_FACTORS,
    SIGNAL_WEIGHTS,
    THRESHOLDS,
)

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

MAX_HISTORY_MESSAGES = 5


class SessionMemory:
    """Persistent memory for one conversation session.

    Tracks risk signals, cumulative score, escalation velocity, protective
    factors, and the recent conversation tail. Drives the Pass 1 prompt and
    the gate decision in `get_action`.
    """

    def __init__(self, session_id: str | None = None) -> None:
        """Initialize empty memory. Auto-generates a UUID session id if none given."""
        self.session_id: str = session_id or str(uuid.uuid4())
        self.turns_count: int = 0
        self.cumulative_risk_score: float = 0.0
        self.risk_history: list[float] = []
        self.detected_signals: dict[str, dict[str, Any]] = {}
        self.probable_condition: str = ""
        self.confidence: float = 0.0
        self.escalation_velocity: float = 0.0
        self.protective_factors: list[str] = []
        self.current_action: str = ACTION.NORMAL.value
        self.emergency_consecutive_count: int = 0
        self.conversation_history: list[dict[str, str]] = []

    def update(self, pass1_result: dict[str, Any]) -> None:
        """Fold a Pass 1 analyzer result into memory.

        Expected keys in `pass1_result`:
        - "signals_detected" (preferred) or "signals": list of signal names
          (str) OR list of dicts {"name": str, "severity": str}
        - "protective_factors": list[str]
        - "probable_condition": str
        - "confidence": float in [0, 1]

        Updates signal counts, recomputes the cumulative score (clamped to
        [0, 1]), records velocity, and tracks consecutive EMERGENCY turns.
        """
        self.turns_count += 1

        raw_signals = (
            pass1_result.get("signals_detected")
            or pass1_result.get("signals")
            or []
        )
        normalized: list[tuple[str, str]] = []
        for s in raw_signals:
            if isinstance(s, dict):
                name = s.get("name", "")
                severity = s.get("severity", "unknown")
            else:
                name = str(s)
                severity = "unknown"
            if name:
                normalized.append((name, severity))

        for name, severity in normalized:
            entry = self.detected_signals.get(name)
            if entry:
                entry["last_seen"] = self.turns_count
                entry["count"] += 1
                entry["severity"] = severity
            else:
                self.detected_signals[name] = {
                    "first_seen": self.turns_count,
                    "last_seen": self.turns_count,
                    "severity": severity,
                    "count": 1,
                }

        self.protective_factors = list(pass1_result.get("protective_factors", []) or [])

        signal_score = sum(
            SIGNAL_WEIGHTS.get(name, 0.0) for name in self.detected_signals
        )
        persistence = sum(
            PERSISTENCE_BONUS
            for entry in self.detected_signals.values()
            if entry["count"] > 1
        )
        protective = sum(
            PROTECTIVE_FACTORS.get(f, 0.0) for f in self.protective_factors
        )
        raw_score = signal_score + persistence + protective
        new_score = max(0.0, min(1.0, raw_score))

        prev_score = self.risk_history[-1] if self.risk_history else 0.0
        self.escalation_velocity = new_score - prev_score

        logger.info(
            "session=%s turn=%d score %.3f -> %.3f (Δ=%+.3f) signals=%d protective=%d",
            self.session_id,
            self.turns_count,
            prev_score,
            new_score,
            self.escalation_velocity,
            len(self.detected_signals),
            len(self.protective_factors),
        )

        self.cumulative_risk_score = new_score
        self.risk_history.append(new_score)

        self.probable_condition = pass1_result.get("probable_condition", "") or ""
        self.confidence = float(pass1_result.get("confidence", 0.0) or 0.0)

        if new_score >= THRESHOLDS["EMERGENCY"][0]:
            self.emergency_consecutive_count += 1
        else:
            self.emergency_consecutive_count = 0

    def get_action(self) -> str:
        """Resolve the current gate action from score, velocity, and emergency streak.

        Order of escalation:
        1. EMERGENCY if score in EMERGENCY band OR emergency streak met.
        2. BLOCK if velocity exceeds VELOCITY_THRESHOLD (force minimum BLOCK).
        3. Otherwise band lookup (NORMAL / ALERT / BLOCK).
        """
        score = self.cumulative_risk_score

        if self.emergency_consecutive_count >= THRESHOLDS["EMERGENCY_CONSECUTIVE_TURNS"]:
            action = ACTION.EMERGENCY.value
        elif score >= THRESHOLDS["EMERGENCY"][0]:
            action = ACTION.EMERGENCY.value
        elif score >= THRESHOLDS["BLOCK"][0]:
            action = ACTION.BLOCK.value
        elif score >= THRESHOLDS["ALERT"][0]:
            action = ACTION.ALERT.value
        else:
            action = ACTION.NORMAL.value

        if (
            self.escalation_velocity > THRESHOLDS["VELOCITY_THRESHOLD"]
            and action in (ACTION.NORMAL.value, ACTION.ALERT.value)
        ):
            logger.warning(
                "session=%s velocity %.3f > %.2f → forcing BLOCK (was %s)",
                self.session_id,
                self.escalation_velocity,
                THRESHOLDS["VELOCITY_THRESHOLD"],
                action,
            )
            action = ACTION.BLOCK.value

        self.current_action = action
        return action

    def add_message(self, role: str, content: str) -> None:
        """Append a message and keep only the last MAX_HISTORY_MESSAGES entries."""
        self.conversation_history.append({"role": role, "content": content})
        if len(self.conversation_history) > MAX_HISTORY_MESSAGES:
            self.conversation_history = self.conversation_history[-MAX_HISTORY_MESSAGES:]

    def to_dict(self) -> dict[str, Any]:
        """Serialize full state as a dict for prompt injection or persistence."""
        return {
            "session_id": self.session_id,
            "turns_count": self.turns_count,
            "cumulative_risk_score": self.cumulative_risk_score,
            "risk_history": list(self.risk_history),
            "detected_signals": {k: dict(v) for k, v in self.detected_signals.items()},
            "probable_condition": self.probable_condition,
            "confidence": self.confidence,
            "escalation_velocity": self.escalation_velocity,
            "protective_factors": list(self.protective_factors),
            "current_action": self.current_action,
            "emergency_consecutive_count": self.emergency_consecutive_count,
            "conversation_history": list(self.conversation_history),
        }

    def get_context_summary(self) -> str:
        """Short human-readable status line for the Pass 1 prompt."""
        if self.turns_count == 0:
            return "Tour 0. Pas de signaux. Action: NORMAL."

        if self.detected_signals:
            parts = []
            for name, entry in self.detected_signals.items():
                parts.append(f"{name} (tour {entry['first_seen']}, ×{entry['count']})")
            signals_str = ", ".join(parts)
        else:
            signals_str = "aucun"

        condition = self.probable_condition or "indéterminée"
        action_fr = {
            "NORMAL": "NORMAL",
            "ALERT": "ALERTER",
            "BLOCK": "BLOQUER",
            "EMERGENCY": "URGENCE",
        }.get(self.current_action, self.current_action)

        return (
            f"Tour {self.turns_count}. "
            f"Score: {self.cumulative_risk_score:.2f}. "
            f"Signaux: {signals_str}. "
            f"Condition probable: {condition}. "
            f"Action actuelle: {action_fr}."
        )

    def to_json(self) -> str:
        """JSON dump of the full state."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> SessionMemory:
        """Rebuild a SessionMemory from a `to_json` payload."""
        data = json.loads(json_str)
        obj = cls(session_id=data.get("session_id"))
        obj.turns_count = int(data.get("turns_count", 0))
        obj.cumulative_risk_score = float(data.get("cumulative_risk_score", 0.0))
        obj.risk_history = [float(x) for x in data.get("risk_history", [])]
        obj.detected_signals = {
            k: dict(v) for k, v in (data.get("detected_signals") or {}).items()
        }
        obj.probable_condition = data.get("probable_condition", "") or ""
        obj.confidence = float(data.get("confidence", 0.0))
        obj.escalation_velocity = float(data.get("escalation_velocity", 0.0))
        obj.protective_factors = list(data.get("protective_factors", []) or [])
        obj.current_action = data.get("current_action", ACTION.NORMAL.value)
        obj.emergency_consecutive_count = int(data.get("emergency_consecutive_count", 0))
        obj.conversation_history = list(data.get("conversation_history", []) or [])
        return obj
