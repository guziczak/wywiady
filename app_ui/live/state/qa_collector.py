"""
QA Collector - zbieranie par pytanie+odpowiedź.

Odpowiedzialność (SRP):
- Przechowuje zebrane pary Q+A
- Śledzi progress (X/10)
- Emituje eventy przy nowej parze
"""

from dataclasses import dataclass, field
from typing import List, Optional, Callable
import time
import uuid


@dataclass
class QAPair:
    """Para pytanie + odpowiedź."""
    id: str
    question: str
    answer: str
    question_timestamp: float
    answer_timestamp: float

    @staticmethod
    def create(question: str, answer: str, question_time: float = None) -> 'QAPair':
        """Factory method."""
        now = time.time()
        return QAPair(
            id=str(uuid.uuid4())[:8],
            question=question,
            answer=answer,
            question_timestamp=question_time or now,
            answer_timestamp=now
        )

    @property
    def response_time(self) -> float:
        """Czas odpowiedzi w sekundach."""
        return self.answer_timestamp - self.question_timestamp


class QACollector:
    """
    Kolektor par Q+A z gamifikacją.

    Funkcje:
    - Dodawanie par
    - Progress tracking (current/target)
    - Callback przy nowej parze (do animacji UI)
    """

    def __init__(self, target_count: int = 10):
        self.pairs: List[QAPair] = []
        self.target_count = target_count

        # Callbacks
        self._on_pair_added: Optional[Callable[[QAPair], None]] = None
        self._on_target_reached: Optional[Callable[[], None]] = None

    def on_pair_added(self, callback: Callable[[QAPair], None]):
        """Rejestruje callback na dodanie pary."""
        self._on_pair_added = callback

    def on_target_reached(self, callback: Callable[[], None]):
        """Rejestruje callback gdy osiągnięto cel."""
        self._on_target_reached = callback

    def add(self, question: str, answer: str, question_time: float = None) -> QAPair:
        """
        Dodaje nową parę Q+A.
        Zwraca utworzoną parę.
        """
        pair = QAPair.create(question, answer, question_time)
        self.pairs.append(pair)

        print(f"[QACollector] Added pair {len(self.pairs)}/{self.target_count}", flush=True)

        # Notify
        if self._on_pair_added:
            try:
                self._on_pair_added(pair)
            except Exception as e:
                print(f"[QACollector] Callback error: {e}", flush=True)

        # Check target
        if len(self.pairs) >= self.target_count and self._on_target_reached:
            try:
                self._on_target_reached()
            except Exception as e:
                print(f"[QACollector] Target callback error: {e}", flush=True)

        return pair

    def add_from_context(self, question: str, answer: str, started_at: float) -> QAPair:
        """Dodaje parę z kontekstu ActiveQuestion."""
        return self.add(question, answer, started_at)

    @property
    def progress(self) -> tuple:
        """Zwraca (current, target)."""
        return (len(self.pairs), self.target_count)

    @property
    def progress_percent(self) -> float:
        """Zwraca progress jako procent (0-100)."""
        if self.target_count == 0:
            return 100.0
        return (len(self.pairs) / self.target_count) * 100

    @property
    def is_complete(self) -> bool:
        """Czy osiągnięto cel."""
        return len(self.pairs) >= self.target_count

    def reset(self):
        """Resetuje kolekcję."""
        self.pairs = []
        print(f"[QACollector] Reset", flush=True)

    def get_latest(self, count: int = 5) -> List[QAPair]:
        """Zwraca ostatnie N par."""
        return self.pairs[-count:] if self.pairs else []

    def get_by_id(self, pair_id: str) -> Optional[QAPair]:
        """Zwraca parę po ID."""
        for pair in self.pairs:
            if pair.id == pair_id:
                return pair
        return None

    def remove(self, pair_id: str) -> Optional[QAPair]:
        """
        Usuwa parę po ID.
        Zwraca usuniętą parę lub None jeśli nie znaleziono.
        """
        for i, pair in enumerate(self.pairs):
            if pair.id == pair_id:
                removed = self.pairs.pop(i)
                print(f"[QACollector] Removed pair {pair_id}", flush=True)
                return removed
        return None

    def update_answer(self, pair_id: str, new_answer: str) -> bool:
        """
        Aktualizuje odpowiedź w parze.
        Zwraca True jeśli zaktualizowano.
        """
        for pair in self.pairs:
            if pair.id == pair_id:
                pair.answer = new_answer
                pair.answer_timestamp = time.time()
                print(f"[QACollector] Updated pair {pair_id} answer", flush=True)
                return True
        return False

    def undo_last(self) -> Optional[QAPair]:
        """
        Cofa ostatnią parę (undo).
        Zwraca cofniętą parę lub None.
        """
        if self.pairs:
            removed = self.pairs.pop()
            print(f"[QACollector] Undo last pair: {removed.id}", flush=True)
            return removed
        return None

    def get_stats(self) -> dict:
        """Zwraca statystyki."""
        if not self.pairs:
            return {
                'count': 0,
                'avg_response_time': 0,
                'total_time': 0
            }

        response_times = [p.response_time for p in self.pairs]
        return {
            'count': len(self.pairs),
            'avg_response_time': sum(response_times) / len(response_times),
            'total_time': self.pairs[-1].answer_timestamp - self.pairs[0].question_timestamp
        }
