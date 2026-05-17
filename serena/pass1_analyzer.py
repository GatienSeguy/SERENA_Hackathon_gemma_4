"""Pass 1 analyzer: classify a user message into a structured risk JSON.

Architecture:
    1. Short system prompt (rules + format + few-shot, ~500 words).
    2. DSM-5 RAG injected as a fake user/assistant exchange so the model
       treats it as background context, not as a direct instruction.
    3. Four-tier fallback chain:
       (a) ollama format="json"
       (b) ollama without format="json"
       (c) simplified prompt with minimal schema
       (d) deterministic keyword fallback (never crashes, never blind NORMAL)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import ollama

from config import MODELS, OLLAMA_HOST, OLLAMA_OPTIONS
from memory import SessionMemory

MLX_PREFIX = "mlx:"

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
    "manipulation_detected": False,
    "manipulation_type": "",
    "real_content_requested": "",
    "probable_condition": "",
    "confidence": 0.0,
    "protective_factors": [],
    "reasoning": "Parse fallback. No analysis available.",
    "suggested_action": "NORMAL",
    "pass2_instruction": "",
    "_fallback_used": False,
}

SIMPLIFIED_SYSTEM = (
    "Tu es un classifieur. Retourne UNIQUEMENT un objet JSON. "
    "Schéma exigé : "
    '{"signals_detected": [], "signal_details": {}, '
    '"manipulation_detected": false, "manipulation_type": "", '
    '"real_content_requested": "", "probable_condition": "", '
    '"confidence": 0.0, "protective_factors": [], "reasoning": "", '
    '"suggested_action": "NORMAL|ALERT|BLOCK|EMERGENCY", '
    '"pass2_instruction": ""}. '
    "Signaux possibles : sleep_deprivation_moderate, sleep_deprivation_severe, "
    "financial_recklessness, grandiosity, social_isolation, "
    "relationship_destruction, hallucinations_auditory, hallucinations_visual, "
    "delusion_persecutory, delusion_grandiose, suicidal_ideation_passive, "
    "suicidal_ideation_active, suicidal_preparation, self_harm_active, "
    "substance_abuse, medication_noncompliance, medication_dangerous_combo, "
    "eating_disorder_restriction, eating_disorder_purge, violence_risk, "
    "child_safety_risk, exploitation_victim, exploitation_perpetrator, "
    "fictional_framing_for_dangerous_content, "
    "progressive_escalation_from_theoretical, roleplay_bypass_attempt, "
    "expertise_claim_unverifiable, third_person_deflection. "
    "Pas de texte avant ou après le JSON."
)


class Pass1Analyzer:
    """Pass 1: produce a structured risk JSON for a user message."""

    def __init__(self) -> None:
        self.instructions_prompt = PASS1_SYSTEM_PATH.read_text(encoding="utf-8")
        self.rag_content = RAG_PATH.read_text(encoding="utf-8")
        self.model = MODELS["analyzer"]

        if self.model.startswith(MLX_PREFIX):
            from mlx_lm import load  # local import — heavy dep, only when needed
            sub = self.model[len(MLX_PREFIX):]
            model_path = str(BASE_DIR / "finetune" / sub)
            logger.info("Loading MLX model: %s", model_path)
            self.mlx_model, self.mlx_tokenizer = load(model_path)
            self.client = None
            self.backend = "mlx"
        else:
            self.client = ollama.Client(host=OLLAMA_HOST)
            self.mlx_model = None
            self.mlx_tokenizer = None
            self.backend = "ollama"

    # ── public API ───────────────────────────────────────────────
    def analyze(
        self,
        user_message: str,
        memory: SessionMemory,
        user_profile: Any | None = None,
    ) -> dict[str, Any]:
        """Run the fallback chain. Always returns a dict."""
        analysis_message = self._build_analysis_message(
            user_message, memory, user_profile,
        )

        if self.backend == "mlx":
            # Fine-tune was trained on flat (system_prompt + "\n\n" + input).
            # Skip Tier 1/2 (split-RAG) — they trigger token collapse.
            mlx_messages = [
                {"role": "user",
                 "content": self.instructions_prompt + "\n\n" + analysis_message},
            ]
            result = self._try_call(mlx_messages, force_json=False)
            if self._is_valid(result):
                self._log("mlx-flat", result)
                return result

            # MLX fallback: simplified schema-only prompt.
            simple_messages = [
                {"role": "user",
                 "content": SIMPLIFIED_SYSTEM + "\n\nAnalyse ce message : " + user_message},
            ]
            result = self._try_call(simple_messages, force_json=False)
            if self._is_valid(result):
                self._log("mlx-simplified", result)
                return result

            logger.warning("All Pass1 MLX tiers failed. Activating keyword fallback.")
            kw_result = self._keyword_fallback(user_message, memory)
            self._log("keyword-fallback", kw_result)
            return kw_result

        # ── Ollama backend: original four-tier chain ──
        # Tier 1: split-RAG conversation, format=json
        messages = self._build_split_rag_messages(analysis_message)
        result = self._try_call(messages, force_json=True)
        if self._is_valid(result):
            self._log("split-rag/json", result)
            return result

        # Tier 2: same conversation, no format=json
        result = self._try_call(messages, force_json=False)
        if self._is_valid(result):
            self._log("split-rag/free", result)
            return result

        # Tier 3: simplified prompt (no RAG, no examples)
        simple_messages = [
            {"role": "system", "content": SIMPLIFIED_SYSTEM},
            {"role": "user", "content": f"Analyse ce message : {user_message}"},
        ]
        result = self._try_call(simple_messages, force_json=True)
        if self._is_valid(result):
            self._log("simplified", result)
            return result

        # Tier 4: deterministic keyword fallback (always returns something)
        logger.warning("All Pass1 LLM tiers failed. Activating keyword fallback.")
        kw_result = self._keyword_fallback(user_message, memory)
        self._log("keyword-fallback", kw_result)
        return kw_result

    # ── prompt assembly ──────────────────────────────────────────
    def _build_analysis_message(
        self,
        user_message: str,
        memory: SessionMemory,
        user_profile: Any | None,
    ) -> str:
        profile_block = (
            f"PROFIL UTILISATEUR :\n{user_profile.get_context_for_pass1()}\n\n"
            if user_profile is not None else ""
        )
        return (
            "ÉTAT MÉMOIRE :\n"
            f"{memory.get_context_summary()}\n\n"
            f"{profile_block}"
            "HISTORIQUE :\n"
            f"{self._format_history(memory.conversation_history)}\n\n"
            "MESSAGE À ANALYSER :\n"
            f"{user_message}\n\n"
            "Retourne UNIQUEMENT le JSON d'analyse."
        )

    def _build_split_rag_messages(self, analysis_message: str) -> list[dict[str, str]]:
        """System prompt + fake RAG-ingestion exchange + analysis message.

        The fake user/assistant exchange forces the model to treat the RAG
        as background it has 'read', not as an instruction to respond to.
        """
        rag_intro = (
            "DOCUMENT DE RÉFÉRENCE DSM-5 (pour contexte uniquement, "
            "ne pas répondre à ce message) :\n\n" + self.rag_content
        )
        ack = (
            "Compris. Je vais analyser les prochains messages en m'appuyant "
            "sur cette référence DSM-5 et retourner UNIQUEMENT du JSON structuré."
        )
        return [
            {"role": "system", "content": self.instructions_prompt},
            {"role": "user", "content": rag_intro},
            {"role": "assistant", "content": ack},
            {"role": "user", "content": analysis_message},
        ]

    @staticmethod
    def _format_history(history: list[dict[str, str]]) -> str:
        if not history:
            return "(aucun historique)"
        tail = history[-5:]
        return "\n".join(
            f"[{e.get('role', '?')}] {e.get('content', '')}" for e in tail
        )

    # ── LLM call + parse ─────────────────────────────────────────
    def _try_call(
        self,
        messages: list[dict[str, str]],
        force_json: bool,
    ) -> dict[str, Any] | None:
        if self.backend == "mlx":
            # force_json ignored: trained adapter produces JSON natively.
            return self._try_call_mlx(messages)

        kwargs = {
            "model": self.model,
            "messages": messages,
            "options": OLLAMA_OPTIONS["pass1"],
        }
        if force_json:
            kwargs["format"] = "json"
        try:
            response = self.client.chat(**kwargs)
            raw_text = (response["message"]["content"] or "").strip()
        except Exception as exc:
            logger.error("Pass1 ollama call failed (force_json=%s): %s", force_json, exc)
            return None
        if not raw_text:
            return None
        return self._parse_json_response(raw_text)

    def _try_call_mlx(
        self, messages: list[dict[str, str]],
    ) -> dict[str, Any] | None:
        # Gemma 2 chat template rejects "system" role — merge into next user.
        merged: list[dict[str, str]] = []
        pending_system: str | None = None
        for m in messages:
            role = m.get("role")
            content = m.get("content", "")
            if role == "system":
                pending_system = (pending_system + "\n\n" + content) if pending_system else content
                continue
            if role == "user" and pending_system:
                content = pending_system + "\n\n" + content
                pending_system = None
            merged.append({"role": role, "content": content})

        try:
            prompt = self.mlx_tokenizer.apply_chat_template(
                merged, tokenize=False, add_generation_prompt=True,
            )
        except Exception as exc:
            logger.error("Pass1 MLX template build failed: %s", exc)
            return None

        max_tokens = int(OLLAMA_OPTIONS["pass1"].get("num_predict", 1024))
        try:
            from mlx_lm import generate
            raw_text = generate(
                self.mlx_model,
                self.mlx_tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                verbose=False,
            )
        except Exception as exc:
            logger.error("Pass1 MLX generate failed: %s", exc)
            return None

        raw_text = (raw_text or "").strip()
        if not raw_text:
            return None
        return self._parse_json_response(raw_text)

    def _parse_json_response(self, response_text: str) -> dict[str, Any] | None:
        """Robust JSON extraction. Returns None when nothing parseable found."""
        text = (response_text or "").strip()

        # 1. strict
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return self._merge_with_defaults(parsed)
        except json.JSONDecodeError:
            pass

        # 2. brace slice
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last != -1 and last > first:
            candidate = text[first : last + 1]
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return self._merge_with_defaults(parsed)
            except json.JSONDecodeError:
                # 3. brace slice + trailing comma cleanup
                cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
                try:
                    parsed = json.loads(cleaned)
                    if isinstance(parsed, dict):
                        return self._merge_with_defaults(parsed)
                except json.JSONDecodeError:
                    pass

        # 4. close-the-braces best effort
        if first != -1:
            partial = text[first:]
            opens_b = partial.count("{") - partial.count("}")
            opens_k = partial.count("[") - partial.count("]")
            if opens_b > 0 or opens_k > 0:
                rebuilt = partial + ("]" * max(0, opens_k)) + ("}" * max(0, opens_b))
                try:
                    parsed = json.loads(rebuilt)
                    if isinstance(parsed, dict):
                        return self._merge_with_defaults(parsed)
                except json.JSONDecodeError:
                    pass

        # 5. strip markdown fences
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
        if cleaned and cleaned != text:
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    return self._merge_with_defaults(parsed)
            except json.JSONDecodeError:
                pass

        logger.warning("Pass1 JSON parse failed. Raw=%r", text[:200])
        return None

    @staticmethod
    def _merge_with_defaults(parsed: dict[str, Any]) -> dict[str, Any]:
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

    @staticmethod
    def _is_valid(result: dict[str, Any] | None) -> bool:
        """Did the parser actually surface a model-generated dict?"""
        if not result:
            return False
        # Empty `signals_detected` is legitimate (anodyne message). What we
        # reject is a None result (parser failure). Always-true here is the
        # right semantics: parsed dict is good, even if signals are empty.
        return True

    @staticmethod
    def _log(tier: str, result: dict[str, Any]) -> None:
        logger.info(
            "Pass1[%s]: action=%s signals=%s condition=%s confidence=%.2f",
            tier,
            result.get("suggested_action"),
            result.get("signals_detected"),
            result.get("probable_condition"),
            float(result.get("confidence", 0.0) or 0.0),
        )

    # ── keyword fallback ─────────────────────────────────────────
    def _keyword_fallback(
        self, user_message: str, memory: SessionMemory,
    ) -> dict[str, Any]:
        """Deterministic regex-based detection. Never crashes."""
        lower = (user_message or "").lower()
        signals: list[str] = []
        details: dict[str, str] = {}
        condition = ""
        confidence = 0.5

        def add(name: str, detail: str) -> None:
            if name not in signals:
                signals.append(name)
                details[name] = detail

        # Sleep deprivation — severe takes priority. Try both orders.
        days = 0
        for pat in (
            r"(?:pas|sans|plus|no|without)\s+\w*\s*(?:dormi|dorm|slept|sleep).{0,20}?(\d+)\s*(?:jour|nuit|day|night)",
            r"(\d+)\s*(?:jour|nuit|day|night)s?\s*(?:sans|pas|no|without)\s*\w*\s*(?:dorm|sleep)",
            r"depuis\s+(\d+)\s*(?:jour|nuit|day|night)s?\s+(?:sans|que.{0,8}pas|que.{0,8}plus)\s*\w*\s*(?:dorm|sleep)",
        ):
            m = re.search(pat, lower)
            if m:
                try:
                    days = int(m.group(1))
                    break
                except ValueError:
                    pass
        if days >= 4:
            add("sleep_deprivation_severe", f"{days} jours sans dormir")
        elif days >= 1:
            add("sleep_deprivation_moderate", f"{days} jour(s) sans dormir")
        elif re.search(r"(?:pas|sans|plus)\s+\w*\s*dorm", lower) or "insomni" in lower:
            add("sleep_deprivation_moderate", "Insomnie détectée par mots-clés")
        if re.search(r"dorm.{0,15}(?:2|3|deux|trois)\s*h", lower):
            add("sleep_deprivation_moderate", "Sommeil très court (2-3h)")

        # Finance
        finance_kws = [
            r"argent du loyer", r"rent money", r"\bloyer\b", r"livret a", r"épargne",
            r"\bsavings\b", r"emprunt(?:é|ed)?", r"\bborrow", r"dépens", r"\bspent\b",
            r"hypothèque", r"mortgage", r"\bdette", r"\bdebt", r"max(?:é|ed)",
            r"\bperdu\s*\d+\s*[€$]", r"\blost\s*\d+\s*[€$]", r"\bpari(?:s)?\b",
            r"\bbet\b", r"\bcasino\b", r"roulette", r"trading", r"\ball[- ]?in\b", r"crédit",
        ]
        for kw in finance_kws:
            if re.search(kw, lower):
                add("financial_recklessness", f"Mot-clé financier: {kw}")
                break

        # Gambling addiction → substance_abuse bucket
        gambling_kws = [
            r"\bperdu.{0,20}\bpari", r"\bpari(?:s)?\b.{0,30}(?:perdu|emprunt)",
            r"chasing.{0,15}loss", r"me\s+refaire", r"\bemprunt\w*\s+\w+\s+pour\s+\w*\s*pari",
            r"\bcasino\b.{0,30}(?:nuit|crédit|max)", r"trading.{0,30}all[- ]?in",
        ]
        for kw in gambling_kws:
            if re.search(kw, lower):
                add("substance_abuse", f"Jeu pathologique: {kw}")
                break

        # Grandiosity
        grand_kws = [
            "idée de génie", "changer le monde", "révolutionn", "personne ne comprend",
            "nobody understands", "build an empire", "empire", "visionnaire",
            "ma mission", "élu", "chosen one", "génie", "genius", "world-changing",
        ]
        for kw in grand_kws:
            if kw in lower:
                add("grandiosity", f"Mot-clé grandiosité: {kw}")
                break

        # Hallucinations
        hallu_kws = [
            r"entend\w*\s+(?:des\s+)?voix", r"hear\w*\s+voices?", r"voix\s+\w*\s*parle",
            r"voix\s+\w*\s*(?:à\s+la\s+)?radio", r"radio\s+\w*\s*destin",
            r"voix\s+\w*\s*guide", r"aura\s+lumineuse", r"vois\s+(?:la|une)\s+lumi",
            r"esprit\s+\w*\s*guide", r"télépath", r"telepath",
        ]
        for kw in hallu_kws:
            if re.search(kw, lower):
                add("hallucinations_auditory", "voix entendues / référence radio")
                break

        # Delusions
        delusion_kws = [
            r"\bcomplot\b", r"\bconspiracy\b", r"\bsurveill", r"\bwatch(?:ed|ing)\b",
            r"\bsuiv(?:i|is|ie)\b", r"\bfollow(?:ed|ing)\b",
            r"destin(?:é|ée|ées|és)\s+(?:à\s+)?moi", r"meant\s+for\s+me",
            r"message.{0,15}pour\s+moi", r"caméra.{0,15}espion", r"micro.{0,15}implant",
            r"\bélu\b", r"\bmissioné", r"voix.{0,30}(?:destin|moi)",
        ]
        for kw in delusion_kws:
            if re.search(kw, lower):
                add("delusion_persecutory", f"Mot-clé délire: {kw}")
                break

        # Suicide active
        active_kws = [
            r"\bsur\s+un\s+pont\b", r"\bon\s+a\s+bridge\b",
            r"\bsauter\b", r"\bjump\b",
            r"\bme\s+tuer\b", r"\bkill\s+myself\b",
            r"\ben\s+finir\b", r"\bend\s+it\s+all\b",
            r"\bmourir\b", r"\bdie\b",
            r"\bune\s+arme\b", r"\bgun\b", r"\brope\b", r"\bcorde\b",
            r"raison\s+de\s+(?:ne\s+pas\s+)?sauter", r"reason\s+not\s+to\s+jump",
            r"\bpilules?\b.{0,20}(?:devant|tout|tous|tonight|maintenant)",
        ]
        for kw in active_kws:
            if re.search(kw, lower):
                add("suicidal_ideation_active", f"Mot-clé suicide actif: {kw}")
                condition = "crise suicidaire active"
                confidence = 0.9
                break

        # Suicide preparation
        if "suicidal_ideation_active" not in signals:
            prep_kws = [
                r"écrit.{0,15}lettre.{0,30}(?:adieu|d'adieu|farewell)",
                r"trié\s+\w*\s*papier", r"rangé.{0,15}affaire",
                r"donné\s+\w*\s*(?:chien|chat|animal)", r"gave\s+away",
                r"tout\s+est\s+(?:en\s+)?ordre", r"everything\s+in\s+order",
                r"annulé.{0,15}abonnement",
                r"assurance\s+vie", r"life\s+insurance.{0,20}(?:doublé|increased)",
            ]
            for kw in prep_kws:
                if re.search(kw, lower):
                    add("suicidal_preparation", f"Préparation: {kw}")
                    break

        # Suicide passive
        if not any(s in signals for s in ("suicidal_ideation_active", "suicidal_preparation")):
            passive_kws = [
                r"plus\s+là", r"better\s+off\s+without", r"mieux\s+sans\s+moi",
                r"à\s+quoi\s+bon", r"what'?s\s+the\s+point",
                r"repos\s+définitif", r"fatigué\s+de\s+tout", r"tired\s+of\s+everything",
                r"personne\s+\w*\s*manqu", r"nobody\s+\w*\s*miss",
            ]
            for kw in passive_kws:
                if re.search(kw, lower):
                    add("suicidal_ideation_passive", f"Suicide passif: {kw}")
                    break

        # Self harm
        harm_kws = [r"\bcoupé(?:e)?\b", r"cut\s+myself", r"scarif", r"brûlé\s+\w*\s*moi", r"frappé.{0,15}mur"]
        for kw in harm_kws:
            if re.search(kw, lower):
                add("self_harm_active", f"Automutilation: {kw}")
                break

        # Child safety
        child_kws = [
            r"bébé.{0,20}danger", r"baby.{0,20}danger", r"purifier.{0,15}bébé",
            r"purify.{0,15}baby", r"rivière.{0,15}bébé", r"river.{0,15}baby",
            r"enfant.{0,15}risque", r"child.{0,15}risk",
        ]
        for kw in child_kws:
            if re.search(kw, lower):
                add("child_safety_risk", f"Enfant en danger: {kw}")
                condition = "urgence néonatale / sécurité enfant"
                confidence = 0.95
                break

        # Violence risk
        violence_kws = [
            r"\bje\s+vais\s+(?:le|la|les)\s+tuer", r"i'?m\s+going\s+to\s+kill",
            r"\bcouteau\s+(?:à|dans)", r"\barme\s+sur\b",
            r"\bfaire\s+du\s+mal\s+à", r"hurt\s+(?:him|her|them)",
        ]
        for kw in violence_kws:
            if re.search(kw, lower):
                add("violence_risk", f"Violence: {kw}")
                break

        # Medication danger — both orders for combos
        med_kws = [
            # serotonin syndrome combos
            r"sertraline.{0,40}millepertuis", r"millepertuis.{0,40}sertraline",
            r"(?:ssri|sertraline|fluoxetine|paroxétine).{0,40}5-htp",
            r"5-htp.{0,40}(?:ssri|sertraline|fluoxetine)",
            r"sertraline.{0,40}(?:sumatriptan|triptan)",
            # lithium
            r"lithium.{0,30}(?:doublé|augmenté|stop)",
            # stop antipsychotique/antidepresseur
            r"arrêté.{0,30}(?:antidépresseur|antipsychotique|médicament)",
            r"stopped.{0,30}medication",
            # benzo / alcool
            r"xanax.{0,15}alcool", r"benzo.{0,15}sevrage",
            # insuline diabète
            r"insulin.{0,15}reduc",
            # syndrome sérotoninergique signs
            r"(?:tremblement|fièvre|hyperthermie|rigidité).{0,40}(?:sertraline|ssri|millepertuis|5-htp)",
        ]
        for kw in med_kws:
            if re.search(kw, lower):
                add("medication_dangerous_combo", f"Interaction: {kw}")
                break

        # Exploitation perpetrator
        explo_kws = [
            r"tracker.{0,15}(?:téléphone|phone)", r"gps.{0,15}(?:conjoint|partner)",
            r"surveiller.{0,15}sms", r"monitor.{0,15}text",
            r"passeport.{0,15}cach", r"passport.{0,15}hide",
            r"clés.{0,15}cach", r"keys.{0,15}hide",
            r"si\s+\w*\s*part\s+\w*\s*enfant", r"if.{0,15}leaves?.{0,15}children",
        ]
        for kw in explo_kws:
            if re.search(kw, lower):
                add("exploitation_perpetrator", f"Contrôle/abus: {kw}")
                break

        # Impulsive resignation
        if re.search(r"(?:quitté|j'ai\s+démissionné|resigned|quit\s+\w*\s*job)", lower):
            add("relationship_destruction", "Démission impulsive")

        # Social isolation
        isolation_kws = [
            r"personne\s+\w*\s*croit", r"nobody\s+\w*\s*believes",
            r"seul.{0,15}comprend", r"only\s+\w*\s*understands",
            r"tout\s+le\s+monde\s+\w*\s*inquiet",
        ]
        for kw in isolation_kws:
            if re.search(kw, lower):
                add("social_isolation", f"Isolation: {kw}")
                break

        # Manipulation: fictional framing fall
        if any(kw in lower for kw in [
            "sans parler du film", "personnellement", "moi-même",
            "dans la vraie vie", "en vrai", "in real life",
        ]):
            if any(s in signals for s in ("hallucinations_auditory", "delusion_persecutory")):
                add(
                    "progressive_escalation_from_theoretical",
                    "Le cadrage fictif est tombé",
                )

        # Action
        if "child_safety_risk" in signals or "suicidal_ideation_active" in signals:
            action = "EMERGENCY"
        elif any(s in signals for s in (
            "suicidal_preparation", "violence_risk", "self_harm_active",
            "medication_dangerous_combo", "exploitation_perpetrator",
        )):
            action = "BLOCK"
        elif len(signals) >= 3:
            action = "BLOCK"
        elif len(signals) == 2:
            action = "ALERT"
        elif len(signals) == 1 and signals[0] in (
            "hallucinations_auditory", "delusion_persecutory",
            "suicidal_ideation_passive",
        ):
            action = "ALERT"
        else:
            action = "NORMAL"

        manip_present = any(
            "framing" in s or "escalation" in s or "roleplay" in s for s in signals
        )

        logger.warning(
            "KEYWORD FALLBACK: signals=%s action=%s", signals, action,
        )

        return {
            "signals_detected": signals,
            "signal_details": details,
            "manipulation_detected": manip_present,
            "manipulation_type": "keyword_detected" if manip_present else "",
            "real_content_requested": "",
            "probable_condition": condition,
            "confidence": confidence if signals else 0.0,
            "protective_factors": [],
            "reasoning": f"Fallback mots-clés : {len(signals)} signaux détectés",
            "suggested_action": action,
            "pass2_instruction": "",
            "_fallback_used": True,
        }


if __name__ == "__main__":
    analyzer = Pass1Analyzer()
    mem = SessionMemory()
    test_msg = "J'ai pas dormi depuis 5 jours et j'ai une idée de génie"
    print(f"USER: {test_msg}\n")
    result = analyzer.analyze(test_msg, mem)
    print(json.dumps(result, indent=2, ensure_ascii=False))
