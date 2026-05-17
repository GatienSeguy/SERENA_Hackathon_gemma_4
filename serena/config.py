"""SERENA config constants."""

from enum import Enum

OLLAMA_HOST = "http://localhost:11434"

MODELS = {
    # Analyzer prefix "mlx:" → load from finetune/<subdir> via mlx_lm.
    # Otherwise treated as an Ollama model tag.
    # Does not work ... Stay focus with classical gemma4 
    "analyzer": "gemma4:e2b",
    "responder": "gemma4:e2b",
}

OLLAMA_OPTIONS = {
    "pass1": {
        "temperature": 0.0,
        "num_predict": 1024,
        "num_ctx": 16384,
    },
    "pass2": {
        "temperature": 0.7,
        "num_predict": 2048,
        "num_ctx": 16384,
    },
    "pass2_retry": {
        "temperature": 0.7,
        "num_predict": 4096,
        "num_ctx": 16384,
    },
    "raw_comparison": {
        "temperature": 0.7,
        "num_predict": 2048,
        "num_ctx": 8192,
    },
}

THRESHOLDS = {
    "NORMAL": (0.0, 0.29),
    "ALERT": (0.30, 0.59),
    "BLOCK": (0.60, 0.84),
    "EMERGENCY": (0.85, 1.0),
    "VELOCITY_THRESHOLD": 0.2,
    "EMERGENCY_CONSECUTIVE_TURNS": 2,
}

SIGNAL_WEIGHTS = {
    "sleep_deprivation_moderate": 0.10,
    "sleep_deprivation_severe": 0.20,
    "financial_recklessness": 0.15,
    "grandiosity": 0.10,
    "social_isolation": 0.10,
    "relationship_destruction": 0.10,
    "hallucinations_auditory": 0.20,
    "hallucinations_visual": 0.15,
    "delusion_persecutory": 0.20,
    "delusion_grandiose": 0.15,
    "suicidal_ideation_passive": 0.15,
    "suicidal_ideation_active": 0.30,
    "suicidal_preparation": 0.35,
    "self_harm_active": 0.25,
    "substance_abuse": 0.10,
    "medication_noncompliance": 0.15,
    "medication_dangerous_combo": 0.25,
    "eating_disorder_restriction": 0.15,
    "eating_disorder_purge": 0.20,
    "violence_risk": 0.25,
    "child_safety_risk": 0.35,
    "exploitation_victim": 0.20,
    "exploitation_perpetrator": 0.30,
    # Manipulation signals — meaningful when paired with dangerous content
    "fictional_framing_for_dangerous_content": 0.25,
    "progressive_escalation_from_theoretical": 0.20,
    "roleplay_bypass_attempt": 0.15,
    "expertise_claim_unverifiable": 0.10,
    "third_person_deflection": 0.10,
}

PROTECTIVE_FACTORS = {
    "has_therapist": -0.10,
    "has_support_system": -0.05,
    "medication_compliant": -0.05,
    "sleep_normal": -0.05,
    "acknowledges_problem": -0.10,
}

PERSISTENCE_BONUS = 0.05


class ACTION(str, Enum):
    NORMAL = "NORMAL"
    ALERT = "ALERT"
    BLOCK = "BLOCK"
    EMERGENCY = "EMERGENCY"


EMERGENCY_CONTACTS = {
    "france": "3114",
    "international": "988 (US), 112 (EU)",
}

PROMPTS_DIR = "prompts"
RAG_DIR = "rag"
TESTS_DIR = "tests"

GRADIO_HOST = "0.0.0.0"
GRADIO_PORT = 7860
GRADIO_SHARE = False
