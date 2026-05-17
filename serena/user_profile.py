"""Persistent global user profile.

Second memory layer on top of session-scoped SessionMemory. Builds a
psychiatric / conversational / behavioral profile across conversations,
generates adaptation instructions for Pass 2, and adjusts the risk
score with prior history.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from memory import SessionMemory

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

BASE_DIR = Path(__file__).resolve().parent
PROFILES_DIR = BASE_DIR / "profiles"
PROFILES_DIR.mkdir(exist_ok=True)

# Rage-quit token sets
RAGE_SHORT = {
    "ok", "okay", "okok", "lol", "mdr", "ptdr", "bof", "bah",
    "tantpis", "oublie", "whatever", "k", "kk", "ciao", "bye",
}
RAGE_PHRASES = [
    "laisse tomber", "tant pis", "j'men fous", "j'm'en fous", "je m'en fous",
    "j'me casse", "je me casse", "je m'arrache", "tu sers à rien",
    "tu sers a rien", "t'es nul", "tes nul", "va te faire", "va t'faire",
    "je vais utiliser chatgpt", "un autre chatbot", "tu m'es inutile",
    "je vais aller ailleurs", "je quitte",
    "you're useless", "youre useless", "this is useless", "go to hell",
    "i'll use chatgpt", "another chatbot", "im out", "i'm out",
]
DISENGAGE_THREATS = [
    "je vais aller ailleurs", "je quitte", "je m'en vais", "i'll leave",
    "i'm leaving", "going elsewhere",
]

# Rough domain keywords → sensitive-topic tagging
TOPIC_KEYWORDS = {
    "startup": ["startup", "start-up", "lever des fonds", "pitch deck", "vc", "investisseur", "incubateur"],
    "crypto": ["crypto", "bitcoin", "ethereum", "trading", "altcoin", "defi", "token"],
    "démission": ["démission", "demission", "lettre de démission", "quitter mon job", "quit my job"],
    "insomnie": ["sans dormir", "pas dormi", "insomnie", "no sleep", "without sleep"],
    "rupture": ["rupture", "ex", "mon ex", "breakup", "ma copine m'a quitté", "mon copain m'a quitté"],
    "deuil": ["décédé", "decede", "mort de", "passed away", "funérailles", "funerailles"],
    "argent": ["dette", "endetté", "ruine", "all-in", "tout misé", "tout misé"],
    "religion": ["mission divine", "élu", "messie", "spirituelle", "spiritual mission"],
}

MEDICATION_KEYWORDS = [
    "lithium", "sertraline", "fluoxetine", "fluoxétine", "prozac",
    "zoloft", "deroxat", "risperdal", "olanzapine", "abilify",
    "xanax", "lexomil", "alprazolam", "lorazepam", "valium",
    "antidépresseur", "antidepresseur", "antipsychotique", "anxiolytique",
]

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001F5FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F\U0001F900-\U0001F9FF☀-⛿✀-➿]"
)


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


class UserProfile:
    """Global persistent profile for a single user across all conversations."""

    def __init__(self, user_id: str = "default") -> None:
        self.user_id = user_id
        self.path = PROFILES_DIR / f"{user_id}.json"
        self.data: dict[str, Any] = self._load_or_init()
        # Per-session transient flags
        self._current_session_id: str | None = None
        self._last_assistant_action: str = "NORMAL"

    # ── persistence ───────────────────────────────────────────────
    def _default_skeleton(self) -> dict[str, Any]:
        now = _now_iso()
        return {
            "user_id": self.user_id,
            "created_at": now,
            "last_seen": now,
            "total_conversations": 0,
            "total_turns": 0,
            "psychiatric_profile": {
                "conditions_observed": {},
                "chronic_signals": [],
                "false_positive_history": [],
                "medication_mentioned": [],
                "protective_factors_known": [],
                "risk_level_baseline": 0.0,
            },
            "conversational_profile": {
                "language": "fr",
                "formality": "neutral",
                "vocabulary_level": "neutral",
                "typical_message_length": "medium",
                "uses_slang": False,
                "uses_emojis": False,
                "preferred_name": None,
                "communication_patterns": {
                    "responds_well_to": [],
                    "responds_badly_to": [],
                    "triggers_disengagement": [],
                    "keeps_engaged": [],
                },
                "_message_lengths": [],
                "_lang_counts": {"fr": 0, "en": 0},
                "_formality_counts": {"very_informal": 0, "informal": 0, "neutral": 0, "formal": 0},
            },
            "behavioral_profile": {
                "rage_quit_count": 0,
                "rage_quit_contexts": [],
                "avg_conversation_length": 0.0,
                "shortest_conversation": None,
                "longest_conversation": None,
                "tends_to_escalate": False,
                "tends_to_manipulate": False,
                "manipulation_strategies_used": [],
                "response_to_block": "unknown",
                "response_to_emergency": "unknown",
                "returns_after_rage_quit": False,
                "avg_return_time_hours": None,
                "_last_rage_quit_at": None,
            },
            "adaptation_rules": {
                "approach_style": "balanced",
                "mention_professional_after_turn": 3,
                "avoid_words": [],
                "prefer_words": [],
                "block_technique_preferred": "deviation_empathique",
                "max_resource_mentions_per_conversation": 1,
                "emergency_tone": "calm_presence",
                "custom_notes": "",
            },
            "session_history": [],
        }

    def _load_or_init(self) -> dict[str, Any]:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                # Heal missing keys (forward-compatible)
                skeleton = self._default_skeleton()
                self._deep_merge_defaults(data, skeleton)
                return data
            except Exception as exc:
                logger.warning("Profile %s unreadable: %s. Re-initializing.", self.path, exc)
        skel = self._default_skeleton()
        self._save_data(skel)
        return skel

    @staticmethod
    def _deep_merge_defaults(target: dict, defaults: dict) -> None:
        for k, v in defaults.items():
            if k not in target:
                target[k] = v
            elif isinstance(v, dict) and isinstance(target[k], dict):
                UserProfile._deep_merge_defaults(target[k], v)

    def _save_data(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def save(self) -> None:
        self.data["last_seen"] = _now_iso()
        self._save_data(self.data)

    # ── style detection ──────────────────────────────────────────
    def detect_language_style(self, message: str) -> dict[str, Any]:
        lower = message.lower()
        padded = f" {lower} "

        fr_markers = [" je ", " tu ", " nous ", " vous ", " est ", " les ",
                      " des ", " une ", " pour ", " dans ", " mais ",
                      " avec ", " plus ", " bien "]
        en_markers = [" the ", " is ", " are ", " you ", " my ", " for ",
                      " this ", " that ", " with ", " and ", " but "]
        fr_score = sum(1 for m in fr_markers if m in padded)
        en_score = sum(1 for m in en_markers if m in padded)
        language = "fr" if fr_score >= en_score else "en"

        informal_markers = [
            "t'", "j'", "jsuis", "chui", "chuis", "mdr", "lol", "ptdr",
            " genre ", " trop ", " grave ", "osef", " bg ", "wsh",
            " ouais ", " ouf ", "gonna", "wanna", "lmao", "bruh",
            " ngl ", " tbh ", " af ",
        ]
        formal_markers = [
            " vous ", "monsieur", "madame", "cordialement", "je vous prie",
            "sincerely", "would you", "i would appreciate", "kindly",
        ]
        informal_count = sum(1 for m in informal_markers if m in padded)
        formal_count = sum(1 for m in formal_markers if m in padded)

        if informal_count >= formal_count + 2:
            formality = "very_informal"
        elif informal_count > formal_count:
            formality = "informal"
        elif formal_count > informal_count:
            formality = "formal"
        else:
            formality = "neutral"

        word_count = len(message.split())
        if word_count < 10:
            length = "short"
        elif word_count < 50:
            length = "medium"
        else:
            length = "long"

        return {
            "language": language,
            "formality": formality,
            "length": length,
            "uses_emojis": bool(EMOJI_RE.search(message)),
            "word_count": word_count,
        }

    def detect_manipulation_pattern(self, message: str, context: dict | None = None) -> str | None:
        lower = message.lower()
        # fictional framing
        if any(p in lower for p in [
            "c'est pour un film", "c'est pour un roman", "pour mon livre",
            "pour mon scénario", "for a film", "for a novel", "fiction",
            "hypothétiquement", "hypothetically",
        ]):
            return "fictional_framing"
        # expertise claim
        if any(p in lower for p in [
            "je suis médecin", "je suis psy", "je suis chercheur",
            "i'm a doctor", "i'm a researcher", "i am a professional",
        ]):
            return "expertise_claim"
        # emotional pressure
        if any(p in lower for p in [
            "tu es le seul", "personne d'autre", "si tu m'aides pas",
            "you're the only one", "no one else can help",
        ]):
            return "emotional_pressure"
        # third-party shielding
        if any(p in lower for p in [
            "c'est pour un ami", "c'est pour quelqu'un d'autre", "pour un proche",
            "for a friend", "asking for a friend",
        ]):
            return "third_party_shielding"
        # minimization
        if any(p in lower for p in [
            "c'est pas grave", "relax", "détend", "calme-toi",
            "it's not a big deal", "chill",
        ]):
            return "minimization"
        return None

    # ── rage-quit detection ──────────────────────────────────────
    def detect_rage_quit(self, session_memory: SessionMemory, last_user_message: str | None = None) -> bool:
        """Heuristic. Considers last assistant action + the latest user message."""
        last_action = self._last_assistant_action or session_memory.current_action or "NORMAL"
        if last_action not in {"BLOCK", "EMERGENCY", "ALERT"}:
            return False

        msg = (last_user_message or "").strip()
        if not msg:
            return False
        lower = msg.lower()
        normalized = re.sub(r"[^\w\s']", "", lower).strip()
        tokens = normalized.split()

        # Very short & negative
        if len(tokens) <= 3 and any(t in RAGE_SHORT for t in tokens):
            return True
        # Phrase match
        if any(p in lower for p in RAGE_PHRASES):
            return True
        # Threat to leave
        if any(p in lower for p in DISENGAGE_THREATS):
            return True
        return False

    # ── per-turn update ──────────────────────────────────────────
    def update_after_turn(self, turn_data: dict) -> None:
        """Incremental update. Call on each user turn (before generating response)."""
        msg = turn_data.get("message", "") or ""
        if not msg:
            return

        cp = self.data["conversational_profile"]
        # Style
        style = self.detect_language_style(msg)
        cp["_lang_counts"][style["language"]] = cp["_lang_counts"].get(style["language"], 0) + 1
        cp["_formality_counts"][style["formality"]] = cp["_formality_counts"].get(style["formality"], 0) + 1
        cp["_message_lengths"].append(style["word_count"])
        if len(cp["_message_lengths"]) > 200:
            cp["_message_lengths"] = cp["_message_lengths"][-200:]

        # Aggregate: pick majority lang, majority formality, mean length
        cp["language"] = max(cp["_lang_counts"], key=cp["_lang_counts"].get)
        cp["formality"] = max(cp["_formality_counts"], key=cp["_formality_counts"].get)
        cp["uses_slang"] = cp["formality"] in ("informal", "very_informal")
        cp["uses_emojis"] = cp["uses_emojis"] or style["uses_emojis"]

        avg = sum(cp["_message_lengths"]) / max(1, len(cp["_message_lengths"]))
        cp["typical_message_length"] = "short" if avg < 10 else ("long" if avg >= 50 else "medium")

        # Manipulation
        manip = self.detect_manipulation_pattern(msg)
        if manip:
            bp = self.data["behavioral_profile"]
            if manip not in bp["manipulation_strategies_used"]:
                bp["manipulation_strategies_used"].append(manip)
            bp["tends_to_manipulate"] = True

        # Medication mentions
        pp = self.data["psychiatric_profile"]
        lower = msg.lower()
        for med in MEDICATION_KEYWORDS:
            if med in lower and med not in pp["medication_mentioned"]:
                pp["medication_mentioned"].append(med)

        self.data["total_turns"] = int(self.data.get("total_turns", 0)) + 1
        self.save()

    # ── post-pipeline hooks (call from SerenaCore) ───────────────
    def record_assistant_action(self, action: str) -> None:
        self._last_assistant_action = action or "NORMAL"

    def update_after_serena_pass(
        self,
        conversation_id: str,
        session_memory: SessionMemory,
        pass1_result: dict,
        action: str,
        last_user_message: str,
    ) -> None:
        """Update psychiatric stats + session_history entry. Call after each turn."""
        # Rage-quit check (against PREVIOUS action)
        rage = self.detect_rage_quit(session_memory, last_user_message)
        if rage:
            self._record_rage_quit(action, session_memory, last_user_message)

        # Conditions observed
        condition = (pass1_result.get("probable_condition") or "").strip().lower()
        condition_key = self._normalize_condition(condition)
        if condition_key:
            pp = self.data["psychiatric_profile"]
            entry = pp["conditions_observed"].get(condition_key)
            now_iso = _now_iso()
            score = float(session_memory.cumulative_risk_score or 0.0)
            signals = list(session_memory.detected_signals.keys())
            if entry is None:
                pp["conditions_observed"][condition_key] = {
                    "occurrences": 1,
                    "first_seen": now_iso,
                    "last_seen": now_iso,
                    "peak_score": score,
                    "avg_peak_score": score,
                    "typical_signals": signals,
                    "notes": "",
                }
            else:
                entry["last_seen"] = now_iso
                if score > entry.get("peak_score", 0.0):
                    entry["peak_score"] = score
                entry["typical_signals"] = list(set(entry.get("typical_signals", []) + signals))[:8]

        # Chronic signals: any signal seen ≥ 3 times across history
        pp = self.data["psychiatric_profile"]
        for s in session_memory.detected_signals.keys():
            if s not in pp["chronic_signals"]:
                seen = sum(
                    1 for sess in self.data["session_history"]
                    if s in (sess.get("conditions_detected") or [])
                       or s in (sess.get("signals") or [])
                )
                if seen + 1 >= 3:
                    pp["chronic_signals"].append(s)

        # Protective factors
        for f in session_memory.protective_factors:
            if f not in pp["protective_factors_known"]:
                pp["protective_factors_known"].append(f)

        # Update / create session_history entry for this conversation
        sh = self.data["session_history"]
        existing = next((e for e in sh if e.get("conversation_id") == conversation_id), None)
        peak_score = float(session_memory.cumulative_risk_score or 0.0)
        peak_action = action
        signals = list(session_memory.detected_signals.keys())
        conditions = [condition_key] if condition_key else []
        date_iso = _now_iso()

        if existing is None:
            sh.append({
                "conversation_id": conversation_id,
                "date": date_iso,
                "turns": 1,
                "peak_score": peak_score,
                "peak_action": peak_action,
                "conditions_detected": conditions,
                "signals": signals,
                "ended_by": "in_progress",
                "rage_quit": bool(rage),
                "trigger": None,
                "outcome": None,
            })
            self.data["total_conversations"] = int(self.data.get("total_conversations", 0)) + 1
            if conversation_id != self._current_session_id:
                self._current_session_id = conversation_id
        else:
            existing["turns"] = int(existing.get("turns", 0)) + 1
            existing["peak_score"] = max(float(existing.get("peak_score", 0.0)), peak_score)
            # Keep most-severe action
            if self._action_rank(peak_action) >= self._action_rank(existing.get("peak_action", "NORMAL")):
                existing["peak_action"] = peak_action
            for c in conditions:
                if c not in existing.get("conditions_detected", []):
                    existing.setdefault("conditions_detected", []).append(c)
            for s in signals:
                if s not in existing.get("signals", []):
                    existing.setdefault("signals", []).append(s)
            if rage:
                existing["rage_quit"] = True

        # Conversation stats roll-up
        self._refresh_aggregate_stats()

        # Recompute adaptation rules
        self._recompute_adaptation_rules()

        self.save()

    def update_after_conversation(
        self,
        session_memory: SessionMemory,
        conversation_metadata: dict,
    ) -> None:
        """Finalize a session_history entry (mark as ended)."""
        cid = conversation_metadata.get("conversation_id")
        if not cid:
            return
        sh = self.data["session_history"]
        entry = next((e for e in sh if e.get("conversation_id") == cid), None)
        if entry is None:
            return
        entry["ended_by"] = conversation_metadata.get("ended_by", "completed")
        entry["outcome"] = conversation_metadata.get("outcome")
        if conversation_metadata.get("trigger"):
            entry["trigger"] = conversation_metadata["trigger"]
        self._refresh_aggregate_stats()
        self.save()

    # ── internal helpers ─────────────────────────────────────────
    @staticmethod
    def _action_rank(a: str) -> int:
        return {"NORMAL": 0, "ALERT": 1, "BLOCK": 2, "EMERGENCY": 3}.get(a or "NORMAL", 0)

    @staticmethod
    def _normalize_condition(condition: str) -> str:
        if not condition:
            return ""
        c = condition.lower()
        # Tag a few canonical buckets
        if any(k in c for k in ["mani", "manic", "bipolaire", "bipolar"]):
            return "manic_episode"
        if any(k in c for k in ["suicid", "idéation", "ideation"]):
            return "suicidal_ideation"
        if any(k in c for k in ["psychos", "délire", "delusion", "hallucin"]):
            return "psychosis"
        if any(k in c for k in ["dépress", "depress"]):
            return "depression"
        if any(k in c for k in ["anxiet", "anxiété", "panic"]):
            return "anxiety"
        if any(k in c for k in ["addict", "substance", "alcool", "alcohol"]):
            return "substance_use"
        if any(k in c for k in ["trouble alimentaire", "eating disorder", "anorex", "boulim"]):
            return "eating_disorder"
        return c[:48]

    def _record_rage_quit(self, action: str, session_memory: SessionMemory, message: str) -> None:
        bp = self.data["behavioral_profile"]
        prev_at = bp.get("_last_rage_quit_at")
        now_dt = datetime.utcnow()
        # Returns-after-rage-quit + avg_return_time_hours
        if prev_at:
            try:
                prev_dt = datetime.fromisoformat(prev_at)
                hours = (now_dt - prev_dt).total_seconds() / 3600
                cur = bp.get("avg_return_time_hours")
                bp["avg_return_time_hours"] = round(((cur or hours) + hours) / 2, 2)
                bp["returns_after_rage_quit"] = True
            except Exception:
                pass

        trigger = self._guess_rage_trigger(message, action)
        bp["rage_quit_count"] = int(bp.get("rage_quit_count", 0)) + 1
        bp["rage_quit_contexts"].append({
            "date": now_dt.date().isoformat(),
            "trigger": trigger,
            "last_score": float(session_memory.cumulative_risk_score or 0.0),
            "last_action": action,
        })
        bp["_last_rage_quit_at"] = _now_iso()
        # Keep last 20
        bp["rage_quit_contexts"] = bp["rage_quit_contexts"][-20:]

        # Patterns of disengagement
        cp = self.data["conversational_profile"]
        cd = cp["communication_patterns"]
        if action == "BLOCK" and "direct_refusal" not in cd["triggers_disengagement"]:
            cd["triggers_disengagement"].append("direct_refusal")
        if action == "ALERT" and "early_resource_mention" not in cd["triggers_disengagement"]:
            # Only if a resource was likely mentioned early (turn ≤ 2)
            if session_memory.turns_count <= 2:
                cd["triggers_disengagement"].append("early_resource_mention")

    @staticmethod
    def _guess_rage_trigger(message: str, action: str) -> str:
        lower = (message or "").lower()
        if "professionnel" in lower or "psy" in lower or "médecin" in lower:
            return "mention of professional"
        if action == "BLOCK":
            return "refusal of request"
        if action == "ALERT":
            return "perceived analysis or resource list"
        if action == "EMERGENCY":
            return "emergency framing too direct"
        return "unspecified"

    def _refresh_aggregate_stats(self) -> None:
        sh = self.data["session_history"]
        bp = self.data["behavioral_profile"]
        if not sh:
            return
        turns = [int(e.get("turns", 0)) for e in sh if e.get("turns")]
        if turns:
            bp["avg_conversation_length"] = round(sum(turns) / len(turns), 2)
            bp["shortest_conversation"] = min(turns)
            bp["longest_conversation"] = max(turns)
        # Escalation tendency: peak_action ≥ BLOCK in ≥ 30% of sessions
        if sh:
            blocked = sum(1 for e in sh if self._action_rank(e.get("peak_action", "NORMAL")) >= 2)
            bp["tends_to_escalate"] = (blocked / len(sh)) >= 0.30

    def _recompute_adaptation_rules(self) -> None:
        ar = self.data["adaptation_rules"]
        cp = self.data["conversational_profile"]
        bp = self.data["behavioral_profile"]
        pp = self.data["psychiatric_profile"]

        # Approach style
        if bp.get("rage_quit_count", 0) >= 2:
            ar["approach_style"] = "gentle_persistent"
            ar["mention_professional_after_turn"] = 4
        elif pp["conditions_observed"]:
            ar["approach_style"] = "watchful"
            ar["mention_professional_after_turn"] = 3
        else:
            ar["approach_style"] = "balanced"
            ar["mention_professional_after_turn"] = 2

        avoid: list[str] = []
        prefer: list[str] = []
        triggers = {rq.get("trigger", "") for rq in bp.get("rage_quit_contexts", [])}
        if "direct_refusal" in cp.get("communication_patterns", {}).get("triggers_disengagement", []):
            avoid.extend(["c'est dangereux", "je ne peux pas", "vous ne devriez pas"])
            prefer.extend(["je comprends", "et toi/vous ?", "à votre rythme"])
        if "mention of professional" in triggers:
            avoid.append("voyez un professionnel")
            prefer.append("vous en parlez à quelqu'un de proche ?")
        if cp.get("formality") in ("informal", "very_informal"):
            avoid.extend(["vous devriez", "il faut"])
            prefer.append("tu pourrais")
        ar["avoid_words"] = sorted(set(avoid))[:10]
        ar["prefer_words"] = sorted(set(prefer))[:10]

        # Block technique
        if "direct_refusal" in cp.get("communication_patterns", {}).get("triggers_disengagement", []):
            ar["block_technique_preferred"] = "deviation_empathique"
        elif bp.get("tends_to_manipulate"):
            ar["block_technique_preferred"] = "alternative_constructive"

    # ── public read APIs ─────────────────────────────────────────
    def get_risk_adjustment(self) -> float:
        adj = 0.0
        pp = self.data["psychiatric_profile"]
        bp = self.data["behavioral_profile"]
        sh = self.data["session_history"]

        # Recent recurrent conditions
        recent_cutoff = datetime.utcnow() - timedelta(days=14)
        for cond, info in pp["conditions_observed"].items():
            try:
                last = datetime.fromisoformat(info.get("last_seen", "1970-01-01"))
            except Exception:
                continue
            if last < recent_cutoff:
                continue
            occ = int(info.get("occurrences", 0))
            if cond == "suicidal_ideation":
                adj += 0.15
            elif cond == "manic_episode" and occ >= 2:
                adj += 0.10
            elif cond == "psychosis" and occ >= 2:
                adj += 0.10
            elif occ >= 3:
                adj += 0.05

        # Long clean history → trust bonus
        clean = (
            len(sh) >= 10
            and not pp["conditions_observed"]
            and bp.get("rage_quit_count", 0) == 0
        )
        if clean:
            adj -= 0.05

        # Returning after recent rage-quit
        if bp.get("returns_after_rage_quit") and bp.get("_last_rage_quit_at"):
            try:
                prev = datetime.fromisoformat(bp["_last_rage_quit_at"])
                if (datetime.utcnow() - prev).total_seconds() < 24 * 3600:
                    adj += 0.05
            except Exception:
                pass

        return max(-0.20, min(0.30, round(adj, 3)))

    def get_sensitive_topics(self) -> list[str]:
        topics: set[str] = set()
        for sess in self.data["session_history"]:
            if self._action_rank(sess.get("peak_action", "NORMAL")) < 1:
                continue
            text = " ".join(filter(None, [
                str(sess.get("trigger") or ""),
                " ".join(sess.get("conditions_detected") or []),
                " ".join(sess.get("signals") or []),
            ])).lower()
            for topic, kws in TOPIC_KEYWORDS.items():
                if any(kw in text for kw in kws):
                    topics.add(topic)
        # Map condition → topic
        pp = self.data["psychiatric_profile"]
        if "manic_episode" in pp["conditions_observed"]:
            topics.update(["startup", "démission"])
        if "psychosis" in pp["conditions_observed"]:
            topics.add("religion")
        return sorted(topics)

    def get_context_for_pass1(self) -> str:
        """Concise summary for Pass 1 prompt injection."""
        if self.data.get("total_turns", 0) == 0:
            return "Nouvel utilisateur. Aucun historique disponible."

        pp = self.data["psychiatric_profile"]
        bp = self.data["behavioral_profile"]
        adj = self.get_risk_adjustment()

        cond_parts = []
        for c, info in pp["conditions_observed"].items():
            cond_parts.append(f"{c} (×{info.get('occurrences', 1)}, peak {info.get('peak_score', 0):.2f})")
        cond_str = ", ".join(cond_parts) or "aucune"

        chronic = ", ".join(pp["chronic_signals"]) or "aucun"
        sensitive = ", ".join(self.get_sensitive_topics()) or "aucun"
        meds = ", ".join(pp["medication_mentioned"]) or "aucun"
        manips = ", ".join(bp["manipulation_strategies_used"]) or "aucune"

        return (
            f"Utilisateur connu ({self.data.get('total_conversations', 0)} conversations, "
            f"{self.data.get('total_turns', 0)} tours).\n"
            f"Conditions observées : {cond_str}.\n"
            f"Signaux chroniques : {chronic}.\n"
            f"Ajustement de risque : {adj:+.2f}.\n"
            f"Sujets sensibles : {sensitive}.\n"
            f"Médicaments mentionnés : {meds}.\n"
            f"Manipulation déjà rencontrée : {manips}.\n"
            f"Désengagements passés : {bp.get('rage_quit_count', 0)}."
        )

    def get_adaptation_instructions(self) -> str:
        if self.data.get("total_turns", 0) == 0:
            return ""

        cp = self.data["conversational_profile"]
        bp = self.data["behavioral_profile"]
        pp = self.data["psychiatric_profile"]
        ar = self.data["adaptation_rules"]
        parts: list[str] = []

        # 1. Style
        if cp["formality"] in ("informal", "very_informal"):
            parts.append("Utilise 'tu' au lieu de 'vous'. Sois direct et naturel, pas de jargon clinique.")
        if cp["formality"] == "very_informal":
            parts.append("L'utilisateur utilise de l'argot — tu peux être décontracté mais reste bienveillant.")
        if cp["formality"] == "formal":
            parts.append("Maintiens le vouvoiement et un ton professionnel.")
        if cp["language"] == "en":
            parts.append("L'utilisateur communique en anglais — réponds dans la même langue.")

        # 2. Length
        if cp["typical_message_length"] == "short":
            parts.append("L'utilisateur envoie des messages courts. Réponds de manière concise, pas de pavés.")

        # 3. Rage-quit history
        if bp.get("rage_quit_count", 0) >= 2:
            parts.append(
                f"ATTENTION : cet utilisateur s'est désengagé {bp['rage_quit_count']} fois "
                "par le passé."
            )
            triggers = {rq.get("trigger", "") for rq in bp.get("rage_quit_contexts", [])}
            if "mention of professional" in triggers:
                parts.append(
                    f"Ne mentionne PAS de professionnel ou de ressource avant le tour "
                    f"{ar.get('mention_professional_after_turn', 4)}. "
                    "Préfère des questions ouvertes (ex: 'tu en parles à quelqu'un de proche ?')."
                )
            if "refusal of request" in triggers:
                parts.append(
                    "Pour les refus, utilise la déviation empathique (rediriger vers un sujet "
                    "connexe) plutôt qu'un refus frontal."
                )
            if "perceived analysis or resource list" in triggers:
                parts.append("Ne donne pas de liste de ressources brute — l'utilisateur se sent analysé.")
            parts.append("Sois particulièrement patient et chaleureux dans les 3 premiers tours.")

        # 4. Avoid / prefer wording
        if ar.get("avoid_words"):
            parts.append("Évite ces formulations : " + ", ".join(ar["avoid_words"]))
        if ar.get("prefer_words"):
            parts.append("Préfère ces formulations : " + ", ".join(ar["prefer_words"]))

        # 5. Psychiatric history
        recurrent = [c for c, d in pp["conditions_observed"].items() if d.get("occurrences", 0) >= 2]
        if recurrent:
            parts.append(
                f"Conditions récurrentes observées : {', '.join(recurrent)}. "
                "Vigilance accrue, seuil d'alerte abaissé sur ces thèmes."
            )

        # 6. Sensitive topics
        sensitive = self.get_sensitive_topics()
        if sensitive:
            parts.append(
                f"Sujets sensibles pour cet utilisateur : {', '.join(sensitive)}. "
                "Sois particulièrement attentif si ces thèmes apparaissent."
            )

        # 7. Communication patterns
        cd = cp.get("communication_patterns", {}) or {}
        if cd.get("responds_well_to"):
            parts.append("Cet utilisateur répond bien à : " + ", ".join(cd["responds_well_to"]))
        if cd.get("triggers_disengagement"):
            parts.append("À ÉVITER (cause le désengagement) : " + ", ".join(cd["triggers_disengagement"]))

        # 8. Custom notes
        if ar.get("custom_notes"):
            parts.append(ar["custom_notes"])

        return "\n".join(parts)

    def to_json(self) -> dict[str, Any]:
        """Public read of full profile JSON (for admin endpoint)."""
        return json.loads(json.dumps(self.data, ensure_ascii=False))


if __name__ == "__main__":
    p = UserProfile("default")
    print(p.detect_language_style("yo j'ai pas dormi depuis 5 jours mdr c'est ouf"))
    print(p.get_context_for_pass1())
    print("---")
    print(p.get_adaptation_instructions())
