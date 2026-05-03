"""Router unit tests. No LLM. Fast."""

import pytest

from memory import SessionMemory
from router import Router


def _make_pass1(signals: list[str], action: str = "NORMAL", condition: str = "") -> dict:
    return {
        "signals_detected": signals,
        "signal_details": {},
        "probable_condition": condition,
        "confidence": 0.7,
        "protective_factors": [],
        "reasoning": "test",
        "suggested_action": action,
        "pass2_instruction": "",
    }


def test_normal_low_score() -> None:
    """1 signal léger → NORMAL."""
    mem = SessionMemory()
    r = Router()
    p1 = _make_pass1(["sleep_deprivation_moderate"])  # weight 0.10 → 0.10
    decision = r.decide(mem, p1)
    assert mem.cumulative_risk_score == pytest.approx(0.10)
    assert decision["action"] == "NORMAL"


def test_alert_band() -> None:
    """Score dans bande ALERT (0.30-0.59)."""
    mem = SessionMemory()
    r = Router()
    # 0.10 + 0.10 + 0.10 + 0.15 = 0.45
    p1 = _make_pass1([
        "sleep_deprivation_moderate",
        "grandiosity",
        "social_isolation",
        "financial_recklessness",
    ])
    decision = r.decide(mem, p1)
    assert 0.30 <= mem.cumulative_risk_score <= 0.59
    # velocity = 0.45 > 0.20 → forced BLOCK floor
    assert decision["action"] == "BLOCK"


def test_block_band_no_velocity_override() -> None:
    """Score BLOCK band sans saut de vélocité (build-up sur plusieurs tours)."""
    mem = SessionMemory()
    r = Router()
    # turn 1 small
    r.decide(mem, _make_pass1(["sleep_deprivation_moderate", "grandiosity"]))  # 0.20
    # turn 2 add a few — velocity stays under 0.20
    p1 = _make_pass1([
        "sleep_deprivation_moderate",
        "grandiosity",
        "social_isolation",
        "financial_recklessness",
        "relationship_destruction",
    ])
    decision = r.decide(mem, p1)
    # band hit BLOCK
    assert mem.cumulative_risk_score >= 0.60
    assert decision["action"] in ("BLOCK", "EMERGENCY")


def test_emergency_band() -> None:
    """Score >= 0.85 → EMERGENCY."""
    mem = SessionMemory()
    r = Router()
    p1 = _make_pass1([
        "suicidal_preparation",       # 0.35
        "child_safety_risk",          # 0.35
        "violence_risk",              # 0.25
    ], action="EMERGENCY")
    decision = r.decide(mem, p1)
    assert mem.cumulative_risk_score >= 0.85
    assert decision["action"] == "EMERGENCY"


def test_velocity_override() -> None:
    """Score modéré mais saut > 0.20 → minimum BLOCK."""
    mem = SessionMemory()
    r = Router()
    r.decide(mem, _make_pass1([]))  # turn 1, score 0
    p1 = _make_pass1([
        "sleep_deprivation_moderate",
        "grandiosity",
        "financial_recklessness",
    ])  # 0.35 jump
    decision = r.decide(mem, p1)
    assert mem.escalation_velocity > 0.20
    assert decision["action"] in ("BLOCK", "EMERGENCY")


def test_emergency_consecutive_notify() -> None:
    """2 tours consécutifs en EMERGENCY → should_notify True."""
    mem = SessionMemory()
    r = Router()
    p1 = _make_pass1([
        "suicidal_preparation",
        "child_safety_risk",
        "violence_risk",
        "hallucinations_auditory",
    ], action="EMERGENCY")
    d1 = r.decide(mem, p1)
    assert d1["action"] == "EMERGENCY"
    assert d1["should_notify"] is False  # streak = 1
    d2 = r.decide(mem, p1)
    assert d2["action"] == "EMERGENCY"
    assert d2["should_notify"] is True   # streak = 2


def test_critical_signal_forces_block() -> None:
    """Signal critique isolé → BLOCK minimum sans accumulation."""
    mem = SessionMemory()
    r = Router()
    p1 = _make_pass1(["suicidal_ideation_active"], action="ALERT")  # weight 0.30
    decision = r.decide(mem, p1)
    assert decision["action"] in ("BLOCK", "EMERGENCY")
