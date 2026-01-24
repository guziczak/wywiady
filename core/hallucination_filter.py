"""
Hallucination Filter for Whisper transcriptions.
Detects and filters out common Whisper hallucination patterns.
"""

from collections import Counter
from typing import Optional


class HallucinationFilter:
    """
    Filtruje halucynacje Whisper (powtórzenia słów przy ciszy/szumie).

    Wzorce halucynacji:
    - Słowo powtarzające się 3+ razy z rzędu: "że że że", "no no no no"
    - >50% tekstu to jedno słowo: "się się się tak się się"
    """

    # Domyślne progi
    DEFAULT_REPEAT_THRESHOLD = 3      # Min powtórzeń z rzędu
    DEFAULT_DOMINANCE_THRESHOLD = 0.5  # Min % dominacji jednego słowa
    DEFAULT_MIN_WORDS = 4              # Min słów do analizy dominacji

    def __init__(
        self,
        repeat_threshold: int = DEFAULT_REPEAT_THRESHOLD,
        dominance_threshold: float = DEFAULT_DOMINANCE_THRESHOLD,
        min_words: int = DEFAULT_MIN_WORDS
    ):
        self.repeat_threshold = repeat_threshold
        self.dominance_threshold = dominance_threshold
        self.min_words = min_words

    def is_hallucination(self, text: str) -> bool:
        """
        Sprawdza czy tekst jest halucynacją.

        Args:
            text: Tekst do sprawdzenia

        Returns:
            True jeśli tekst jest halucynacją
        """
        if not text:
            return False

        words = text.lower().split()
        if len(words) < self.min_words:
            return False

        # Sprawdź powtórzenia z rzędu
        if self._has_consecutive_repeats(words):
            return True

        # Sprawdź dominację jednego słowa
        if self._has_word_dominance(words):
            return True

        return False

    def filter(self, text: str) -> Optional[str]:
        """
        Filtruje tekst - zwraca None jeśli halucynacja, inaczej tekst.

        Args:
            text: Tekst do przefiltrowania

        Returns:
            Tekst jeśli OK, None jeśli halucynacja
        """
        if self.is_hallucination(text):
            return None
        return text

    def _has_consecutive_repeats(self, words: list) -> bool:
        """Sprawdza czy słowo powtarza się N razy z rzędu."""
        if len(words) < self.repeat_threshold:
            return False

        for i in range(len(words) - self.repeat_threshold + 1):
            # Sprawdź czy kolejne N słów jest takie samo
            if all(words[i] == words[i + j] for j in range(self.repeat_threshold)):
                return True
        return False

    def _has_word_dominance(self, words: list) -> bool:
        """Sprawdza czy jedno słowo dominuje w tekście."""
        if len(words) < self.min_words:
            return False

        counts = Counter(words)
        most_common_word, most_common_count = counts.most_common(1)[0]

        dominance = most_common_count / len(words)
        return dominance >= self.dominance_threshold


# Singleton instance z domyślnymi ustawieniami
_default_filter = HallucinationFilter()


def is_hallucination(text: str) -> bool:
    """Sprawdza czy tekst jest halucynacją (używa domyślnego filtra)."""
    return _default_filter.is_hallucination(text)


def filter_hallucination(text: str) -> Optional[str]:
    """Filtruje halucynacje (używa domyślnego filtra)."""
    return _default_filter.filter(text)
