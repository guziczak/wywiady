"""
Diff Engine for Word-Level Text Comparison
Porównuje teksty słowo-po-słowie i oznacza zmiany.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple
import difflib


class WordStatus(Enum):
    """Status słowa w diffie."""
    UNCHANGED = "unchanged"
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


@dataclass
class WordToken:
    """Pojedyncze słowo z metadanymi."""
    text: str
    status: WordStatus = WordStatus.UNCHANGED
    animation_delay: float = 0.0

    def __post_init__(self):
        # Normalizuj tekst
        self.text = self.text.strip() if self.text else ""


class DiffEngine:
    """
    Engine do porównywania tekstów słowo-po-słowie.
    Używa difflib.SequenceMatcher dla optymalnego dopasowania.
    """

    # Bazowe opóźnienie między słowami (sekundy)
    STAGGER_DELAY = 0.08

    @classmethod
    def tokenize(cls, text: str) -> List[str]:
        """Dzieli tekst na słowa zachowując interpunkcję."""
        if not text:
            return []

        words = []
        current_word = ""

        for char in text:
            if char.isspace():
                if current_word:
                    words.append(current_word)
                    current_word = ""
            else:
                current_word += char

        if current_word:
            words.append(current_word)

        return words

    @classmethod
    def compute_diff(
        cls,
        old_text: str,
        new_text: str
    ) -> Tuple[List[WordToken], List[int]]:
        """
        Porównuje stary tekst z nowym.

        Returns:
            Tuple[List[WordToken], List[int]]:
                - Lista tokenów z nowego tekstu z oznaczeniami statusu
                - Indeksy słów które się zmieniły (do animacji)
        """
        old_words = cls.tokenize(old_text)
        new_words = cls.tokenize(new_text)

        if not old_words:
            # Wszystko nowe
            return (
                [WordToken(w, WordStatus.ADDED, i * cls.STAGGER_DELAY)
                 for i, w in enumerate(new_words)],
                list(range(len(new_words)))
            )

        if not new_words:
            return [], []

        # Użyj SequenceMatcher do znalezienia różnic
        matcher = difflib.SequenceMatcher(None, old_words, new_words)

        result_tokens: List[WordToken] = []
        changed_indices: List[int] = []
        animation_index = 0

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                # Słowa bez zmian
                for word in new_words[j1:j2]:
                    result_tokens.append(WordToken(word, WordStatus.UNCHANGED))

            elif tag == 'replace':
                # Słowa zmienione
                for idx, word in enumerate(new_words[j1:j2]):
                    token = WordToken(
                        word,
                        WordStatus.MODIFIED,
                        animation_index * cls.STAGGER_DELAY
                    )
                    result_tokens.append(token)
                    changed_indices.append(len(result_tokens) - 1)
                    animation_index += 1

            elif tag == 'insert':
                # Nowe słowa
                for idx, word in enumerate(new_words[j1:j2]):
                    token = WordToken(
                        word,
                        WordStatus.ADDED,
                        animation_index * cls.STAGGER_DELAY
                    )
                    result_tokens.append(token)
                    changed_indices.append(len(result_tokens) - 1)
                    animation_index += 1

            # 'delete' - ignorujemy, bo renderujemy nowy tekst

        return result_tokens, changed_indices

    @classmethod
    def compute_regeneration_diff(
        cls,
        old_text: str,
        new_text: str,
        layer: str = "improved"
    ) -> List[WordToken]:
        """
        Specjalna wersja dla regeneracji transkrypcji.

        Args:
            old_text: Poprzedni tekst (provisional/improved)
            new_text: Nowy tekst (improved/final)
            layer: Typ warstwy ("improved" lub "final")

        Returns:
            Lista tokenów gotowych do renderowania z animacją
        """
        tokens, changed = cls.compute_diff(old_text, new_text)

        # Dla warstwy final - wszystkie słowa przechodzą przez animację
        if layer == "final" and tokens:
            for i, token in enumerate(tokens):
                if token.status == WordStatus.UNCHANGED:
                    # Nawet unchanged dostają krótką animację "potwierdzenia"
                    token.animation_delay = i * (cls.STAGGER_DELAY / 2)

        return tokens
