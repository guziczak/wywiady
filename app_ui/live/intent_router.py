"""
Conversation intent router for Live mode.
Classifies the visit type and keeps it stable over time.
"""

from dataclasses import dataclass
from typing import Optional, List
import time

from app_ui.live.live_state import ConversationMode


@dataclass
class IntentResult:
    mode: ConversationMode
    confidence: float
    reason: str
    source: str = "heuristic"


def _normalize_pl(text: str) -> str:
    """Normalize Polish diacritics to ASCII for heuristic matching."""
    if not text:
        return ""
    mapping = str.maketrans({
        "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o", "ś": "s", "ż": "z", "ź": "z",
        "Ą": "a", "Ć": "c", "Ę": "e", "Ł": "l", "Ń": "n", "Ó": "o", "Ś": "s", "Ż": "z", "Ź": "z",
    })
    return text.translate(mapping).lower()


class IntentRouter:
    """Detects conversation mode using heuristics and optional LLM."""

    MIN_CHAR_DELTA = 120
    COOLDOWN_SECONDS = 12.0
    SWITCH_STREAK = 2
    CONFIDENCE_STRONG = 0.75

    def __init__(self, llm_service=None, config: Optional[dict] = None):
        self.llm_service = llm_service
        self.config = config or {}
        self._last_result = IntentResult(ConversationMode.GENERAL, 0.0, "init", source="init")
        self._last_eval_len = 0
        self._last_eval_time = 0.0
        self._pending_mode: Optional[ConversationMode] = None
        self._pending_streak = 0

    async def classify(self, transcript: str, spec_ids: Optional[List[int]] = None, force: bool = False) -> IntentResult:
        if not transcript or len(transcript.strip()) < 20:
            return self._last_result

        now = time.time()
        if not force:
            if (
                len(transcript) - self._last_eval_len < self.MIN_CHAR_DELTA
                and (now - self._last_eval_time) < self.COOLDOWN_SECONDS
            ):
                return self._last_result

        self._last_eval_len = len(transcript)
        self._last_eval_time = now

        heuristic = self._heuristic_classify(transcript)
        llm_result = None
        if self.llm_service and hasattr(self.llm_service, "classify_conversation_mode"):
            try:
                llm_result = await self.llm_service.classify_conversation_mode(
                    transcript=transcript,
                    config=self.config,
                    spec_ids=spec_ids,
                )
            except Exception:
                llm_result = None

        chosen = heuristic
        if llm_result and isinstance(llm_result, dict):
            mode = llm_result.get("mode")
            conf = float(llm_result.get("confidence", 0.0) or 0.0)
            reason = llm_result.get("reason", "") or "llm"
            try:
                mode_enum = ConversationMode(mode)
                if conf >= 0.55:
                    chosen = IntentResult(mode_enum, conf, reason, source="llm")
            except Exception:
                pass

        return self._stabilize(chosen)

    def _stabilize(self, candidate: IntentResult) -> IntentResult:
        # Strong confidence -> accept immediately
        if candidate.confidence >= self.CONFIDENCE_STRONG:
            self._pending_mode = None
            self._pending_streak = 0
            self._last_result = candidate
            return candidate

        # Same as current -> keep
        if candidate.mode == self._last_result.mode:
            self._pending_mode = None
            self._pending_streak = 0
            self._last_result = candidate
            return candidate

        # Require streak for lower confidence switches
        if self._pending_mode != candidate.mode:
            self._pending_mode = candidate.mode
            self._pending_streak = 1
            return self._last_result

        self._pending_streak += 1
        if self._pending_streak >= self.SWITCH_STREAK:
            self._pending_mode = None
            self._pending_streak = 0
            self._last_result = candidate
            return candidate

        return self._last_result

    def _heuristic_classify(self, transcript: str) -> IntentResult:
        text = _normalize_pl(transcript)

        decision_kw = [
            "porada", "porad", "konsultac", "omowic", "wybor", "opcje", "metod",
            "zalezy mi", "chce wiedziec", "chcialbym", "chcialabym", "dowiedziec",
            "rozwaz", "informacj", "co poleca", "jakie sa mozliwosci",
        ]
        follow_kw = [
            "kontrol", "po leczeniu", "po zabiegu", "po terapii", "wyniki",
            "sprawdzic", "kontynuac", "nawrot", "dalsze kroki",
        ]
        admin_kw = [
            "zaswiadczen", "zwolnien", "skierowan", "recept", "wypis",
            "formularz", "dokument", "orzeczen",
        ]
        symptom_kw = [
            "bol", "dolegliw", "objaw", "goraczk", "kaszel", "dusznos",
            "zawrot", "mdlosc", "wysyp", "krwaw", "opuch", "uraz", "rana",
        ]

        def _score(keywords):
            score = 0
            for kw in keywords:
                if kw in text:
                    score += 1
            return score

        scores = {
            ConversationMode.DECISION: _score(decision_kw),
            ConversationMode.FOLLOWUP: _score(follow_kw),
            ConversationMode.ADMIN: _score(admin_kw),
            ConversationMode.SYMPTOM: _score(symptom_kw),
        }

        best_mode = max(scores, key=scores.get)
        best_score = scores[best_mode]

        if best_score <= 0:
            return IntentResult(ConversationMode.GENERAL, 0.2, "no keywords", source="heuristic")

        confidence = min(0.4 + best_score * 0.15, 0.85)
        return IntentResult(best_mode, confidence, f"keywords={best_score}", source="heuristic")
