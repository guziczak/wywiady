"""
Active Question Context - State Machine for Q+A tracking.

Odpowiedzialność (SRP):
- Zarządza aktywnym pytaniem (po kliknięciu karty)
- State machine: IDLE -> LOADING -> READY -> WAITING -> MATCHED
- Timer countdown
- Pinning (user może przypiąć pytanie)

ODDZIELONY od puli sugestii - regeneracja sugestii NIE wpływa na aktywne pytanie.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Callable
import time


class QuestionState(Enum):
    """Stan aktywnego pytania."""
    IDLE = "idle"                    # Brak aktywnego pytania
    LOADING = "loading"              # Ładowanie odpowiedzi AI
    READY = "ready"                  # Odpowiedzi gotowe, wyświetlane
    WAITING_ANSWER = "waiting"       # Czekamy na odpowiedź pacjenta
    MATCHED = "matched"              # Dopasowano odpowiedź!
    EXPIRED = "expired"              # Timeout


@dataclass
class ActiveQuestionContext:
    """
    Kontekst aktywnego pytania - ODDZIELONY od puli sugestii.

    Lifecycle:
    1. User klika kartę -> activate(question)
    2. AI generuje odpowiedzi -> set_answers(answers)
    3. User zadaje pytanie -> start_waiting() [opcjonalne]
    4. Wykryto odpowiedź pacjenta -> match(answer) -> QAPair
    5. User zamyka lub timeout -> clear()

    Pinning: user może "przypiąć" pytanie, wtedy nie znika przy timeout/clear.
    """

    # Stan
    question: Optional[str] = None
    answers: List[str] = field(default_factory=list)
    state: QuestionState = QuestionState.IDLE

    # Timing
    started_at: float = 0.0
    expires_at: float = 0.0
    timeout_seconds: float = 120.0  # 2 minuty domyślnie

    # User control
    pinned: bool = False

    # Odpowiedz source: 'auto' (transkrypcja) lub 'manual' (klik)
    answer_source: Optional[str] = None

    # Callbacks
    _on_state_change: Optional[Callable[['ActiveQuestionContext'], None]] = None
    _on_matched: Optional[Callable[[str, str], None]] = None  # (question, answer)

    def on_state_change(self, callback: Callable[['ActiveQuestionContext'], None]):
        """Rejestruje callback na zmianę stanu."""
        self._on_state_change = callback

    def on_matched(self, callback: Callable[[str, str], None]):
        """Rejestruje callback gdy dopasowano odpowiedź."""
        self._on_matched = callback

    def activate(self, question: str, timeout: float = None):
        """
        Aktywuje pytanie (po kliknięciu karty).
        Przechodzi do stanu LOADING.
        """
        if timeout is None:
            timeout = self.timeout_seconds

        self.question = question
        self.state = QuestionState.LOADING
        self.started_at = time.time()
        self.expires_at = self.started_at + timeout
        self.answers = []
        self.pinned = False
        self.answer_source = None

        print(f"[ActiveQ] Activated: '{question[:40]}...' (timeout={timeout}s)", flush=True)
        self._notify()

    def set_answers(self, answers: List[str]):
        """
        Ustawia odpowiedzi pacjenta (po załadowaniu z AI).
        Przechodzi do stanu READY.
        """
        if self.state != QuestionState.LOADING:
            print(f"[ActiveQ] Warning: set_answers in state {self.state}", flush=True)
            return

        self.answers = answers or []
        self.state = QuestionState.READY

        print(f"[ActiveQ] Answers loaded: {len(self.answers)} options", flush=True)
        self._notify()

    def start_waiting(self):
        """
        Przechodzi do oczekiwania na odpowiedź pacjenta.
        Opcjonalne - user może manualnie włączyć tryb "nasłuchu".
        """
        if self.state not in (QuestionState.READY, QuestionState.LOADING):
            return

        self.state = QuestionState.WAITING_ANSWER
        # Reset timer od teraz
        self.started_at = time.time()
        self.expires_at = self.started_at + self.timeout_seconds

        print(f"[ActiveQ] Waiting for answer...", flush=True)
        self._notify()

    def match(self, answer: str, source: str = 'auto') -> bool:
        """
        Dopasowano odpowiedź pacjenta!
        Przechodzi do stanu MATCHED.

        Args:
            answer: Dopasowana odpowiedź
            source: Źródło dopasowania - 'auto' (transkrypcja) lub 'manual' (klik)

        Zwraca True jeśli match się udał.
        """
        if not self.question:
            return False

        if self.state not in (QuestionState.READY, QuestionState.WAITING_ANSWER):
            print(f"[ActiveQ] Cannot match in state {self.state}", flush=True)
            return False

        self.state = QuestionState.MATCHED
        self.answer_source = source

        print(f"[ActiveQ] MATCHED ({source})! Q: '{self.question[:30]}...' A: '{answer[:30]}...'", flush=True)

        # Notify o dopasowaniu
        if self._on_matched:
            try:
                self._on_matched(self.question, answer)
            except Exception as e:
                print(f"[ActiveQ] Match callback error: {e}", flush=True)

        self._notify()
        return True

    def clear(self, force: bool = False):
        """
        Czyści kontekst (manual lub timeout).
        Jeśli pinned=True i force=False, nie czyści.
        """
        if self.pinned and not force:
            print(f"[ActiveQ] Clear blocked - question is pinned", flush=True)
            return False

        prev_state = self.state
        self.question = None
        self.answers = []
        self.state = QuestionState.IDLE
        self.pinned = False
        self.started_at = 0.0
        self.expires_at = 0.0
        self.answer_source = None

        if prev_state != QuestionState.IDLE:
            print(f"[ActiveQ] Cleared", flush=True)
            self._notify()

        return True

    def toggle_pin(self) -> bool:
        """Przełącza pinning. Zwraca nowy stan."""
        self.pinned = not self.pinned
        print(f"[ActiveQ] Pinned: {self.pinned}", flush=True)
        self._notify()
        return self.pinned

    def check_timeout(self) -> bool:
        """
        Sprawdza czy minął timeout.
        Wywołuj okresowo (np. z timera UI).
        Zwraca True jeśli wygasło.
        """
        if self.state == QuestionState.IDLE:
            return False

        if self.pinned:
            return False

        if time.time() > self.expires_at:
            print(f"[ActiveQ] Timeout expired", flush=True)
            self.state = QuestionState.EXPIRED
            self._notify()
            # Auto-clear po expired
            self.clear(force=True)
            return True

        return False

    @property
    def time_remaining(self) -> float:
        """Ile sekund zostało do timeout."""
        if self.state == QuestionState.IDLE:
            return 0
        return max(0, self.expires_at - time.time())

    @property
    def time_elapsed(self) -> float:
        """Ile sekund minęło od aktywacji."""
        if self.started_at == 0:
            return 0
        return time.time() - self.started_at

    @property
    def is_active(self) -> bool:
        """Czy jest aktywne pytanie."""
        return self.state not in (QuestionState.IDLE, QuestionState.EXPIRED)

    @property
    def is_ready_for_match(self) -> bool:
        """Czy można próbować dopasować odpowiedź."""
        return self.state in (QuestionState.READY, QuestionState.WAITING_ANSWER)

    def _notify(self):
        """Powiadamia o zmianie stanu."""
        if self._on_state_change:
            try:
                self._on_state_change(self)
            except Exception as e:
                print(f"[ActiveQ] State change callback error: {e}", flush=True)
