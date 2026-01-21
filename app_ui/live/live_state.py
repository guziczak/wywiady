"""
Live Interview State Management
Centralne zarządzanie stanem transkrypcji i sugestii.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Callable, Dict, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from core.diarization import DiarizationResult, DiarizationSegment, SpeakerRole


class SessionStatus(Enum):
    """Status sesji live."""
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"


class PrompterMode(Enum):
    """Tryb panelu promptera."""
    SUGGESTIONS = "suggestions"  # Normalne karty sugestii
    CONFIRMING = "confirming"    # Potwierdzenie zakończenia
    SUMMARY = "summary"          # Podsumowanie po zakończeniu


@dataclass
class TranscriptSegment:
    """Pojedynczy segment transkrypcji."""
    text: str
    start_sample: int = 0
    end_sample: int = 0
    is_validated: bool = False


@dataclass
class Suggestion:
    """Sugestia pytania z metadanymi."""
    question: str
    used: bool = False
    clicked_at: Optional[float] = None


@dataclass
class DiarizationInfo:
    """Informacje o diaryzacji sesji."""
    segments: List['DiarizationSegment'] = field(default_factory=list)
    speaker_mapping: Dict[str, 'SpeakerRole'] = field(default_factory=dict)
    enabled: bool = False
    is_processing: bool = False
    num_speakers: int = 0

    @property
    def has_data(self) -> bool:
        """Czy są dane diaryzacji."""
        return len(self.segments) > 0

    def get_formatted_transcript(self) -> str:
        """Zwraca transkrypcję z oznaczeniami mówców."""
        if not self.segments:
            return ""
        lines = []
        for seg in self.segments:
            if seg.text:
                label = seg.role.display_name if hasattr(seg.role, 'display_name') else str(seg.role)
                lines.append(f"{label}: {seg.text}")
        return "\n".join(lines)


@dataclass
class InterviewStats:
    """Statystyki sesji wywiadu."""
    duration_seconds: float = 0.0
    word_count: int = 0
    speaker_count: int = 0
    is_complete: bool = False

    @property
    def duration_formatted(self) -> str:
        """Formatuje czas jako MM:SS."""
        minutes = int(self.duration_seconds // 60)
        seconds = int(self.duration_seconds % 60)
        return f"{minutes}:{seconds:02d}"

    @property
    def duration_display(self) -> str:
        """Wyświetlana wartość czasu."""
        if self.duration_seconds < 60:
            return f"{int(self.duration_seconds)}s"
        return self.duration_formatted


class LiveState:
    """
    Centralny stan sesji Live Interview.
    Single Source of Truth dla wszystkich komponentów.
    """

    def __init__(self):
        # Session
        self.status: SessionStatus = SessionStatus.IDLE

        # Transkrypcja - 3 warstwy
        self.provisional_text: str = ""    # Real-time (szary, italic)
        self.final_text: str = ""          # Po ciszy, czeka na walidację
        self.validated_text: str = ""      # Zwalidowane przez AI (finalne)

        # Pełna transkrypcja (dla AI)
        self._full_transcript: str = ""
        self._words_since_last_regen: int = 0

        # Sugestie
        self.suggestions: List[Suggestion] = []
        self.asked_questions: List[str] = []  # Historia użytych pytań

        # Podpowiedzi odpowiedzi pacjenta
        self.selected_question: Optional[str] = None
        self.answer_suggestions: List[str] = []
        self.answer_loading: bool = False

        # Pending validation queue
        self.pending_validation: List[str] = []

        # Diaryzacja
        self.diarization: Optional[DiarizationInfo] = None

        # Tryb panelu i statystyki (dla nowego flow)
        self.prompter_mode: PrompterMode = PrompterMode.SUGGESTIONS
        self.interview_stats: Optional[InterviewStats] = None
        self.analyze_speakers_preference: bool = True  # Zapamiętana preferencja
        self._recording_start_time: Optional[float] = None

        # Callbacks dla UI updates
        self._on_transcript_change: Optional[Callable] = None
        self._on_suggestions_change: Optional[Callable] = None
        self._on_status_change: Optional[Callable] = None
        self._on_diarization_change: Optional[Callable] = None
        self._on_mode_change: Optional[Callable] = None

    # === SUBSCRIPTION ===

    def on_transcript_change(self, callback: Callable):
        """Rejestruje callback na zmianę transkrypcji."""
        self._on_transcript_change = callback

    def on_suggestions_change(self, callback: Callable):
        """Rejestruje callback na zmianę sugestii."""
        self._on_suggestions_change = callback

    def on_status_change(self, callback: Callable):
        """Rejestruje callback na zmianę statusu."""
        self._on_status_change = callback

    def on_diarization_change(self, callback: Callable):
        """Rejestruje callback na zmianę diaryzacji."""
        self._on_diarization_change = callback

    def on_mode_change(self, callback: Callable):
        """Rejestruje callback na zmianę trybu panelu."""
        self._on_mode_change = callback

    # === TRANSCRIPT MANAGEMENT ===

    def set_provisional(self, text: str):
        """Ustawia tekst provisional (real-time)."""
        text = text.strip()
        if not text:
            return
        self.provisional_text = self._smart_join(self.provisional_text, text)
        self._rebuild_full_transcript()
        self._notify_transcript_change()

    def set_improved(self, text: str):
        """Improved zastępuje provisional (lepszy kontekst dla bieżącego segmentu)."""
        text = text.strip()
        if not text:
            return
        
        # Improved po prostu zastępuje cały provisional
        # (streaming service wysyła tekst tylko dla niesfinalizowanego segmentu)
        self.provisional_text = text
        self._rebuild_full_transcript()
        self._notify_transcript_change()

    def set_final(self, text: str):
        """Przenosi tekst do final (po ciszy)."""
        text = text.strip()
        if not text:
            return

        self.final_text = self._smart_join(self.final_text, text)
        self.provisional_text = ""
        self.pending_validation.append(text)

        # Zlicz słowa dla smart triggers
        self._words_since_last_regen += len(text.split())

        self._rebuild_full_transcript()
        self._notify_transcript_change()

    def validate_segment(self, corrected_text: str, needs_newline: bool = False):
        """Przenosi zwalidowany tekst do validated."""
        print(f"[STATE] validate_segment called: '{corrected_text[:50]}...'", flush=True)
        
        if needs_newline and self.validated_text:
            self.validated_text = self.validated_text.rstrip() + "\n"

        self.validated_text = self._smart_join(self.validated_text, corrected_text)
        self.final_text = ""

        self._rebuild_full_transcript()
        self._notify_transcript_change()
        print(f"[STATE] validated_text now: '{self.validated_text[:50] if self.validated_text else ''}'", flush=True)

    def clear_pending_validation(self) -> List[str]:
        """Pobiera i czyści kolejkę walidacji."""
        segments = self.pending_validation.copy()
        self.pending_validation = []
        return segments

    # === SUGGESTIONS MANAGEMENT ===

    def set_suggestions(self, questions: List[str]):
        """Ustawia nowe sugestie (wykluczając już użyte)."""
        self.suggestions = [
            Suggestion(question=q)
            for q in questions
            if q not in self.asked_questions
        ][:3]  # Max 3 sugestie
        self._words_since_last_regen = 0
        # Jesli wybrane pytanie nie jest juz w nowych sugestiach, wyczysc panel odpowiedzi
        if self.selected_question and all(s.question != self.selected_question for s in self.suggestions):
            self.selected_question = None
            self.answer_suggestions = []
            self.answer_loading = False
        self._notify_suggestions_change()

    def mark_suggestion_used(self, question: str):
        """Oznacza sugestię jako użytą."""
        import time
        for s in self.suggestions:
            if s.question == question:
                s.used = True
                s.clicked_at = time.time()
                break
        self.asked_questions.append(question)
        self._notify_suggestions_change()

    def get_active_suggestions(self) -> List[Suggestion]:
        """Zwraca nieużyte sugestie."""
        return [s for s in self.suggestions if not s.used]

    def set_answer_context(self, question: Optional[str], answers: List[str]):
        """Ustawia wybrane pytanie i przykładowe odpowiedzi pacjenta."""
        self.selected_question = question.strip() if question else None
        self.answer_suggestions = [a.strip() for a in answers if a and a.strip()]
        self.answer_loading = False
        if self.selected_question:
            print(f"[STATE] Answer context set ({len(self.answer_suggestions)} answers)", flush=True)
        self._notify_suggestions_change()

    def set_answer_loading(self, question: Optional[str]):
        """Ustawia stan ladowania odpowiedzi pacjenta dla wybranego pytania."""
        self.selected_question = question.strip() if question else None
        self.answer_suggestions = []
        self.answer_loading = bool(self.selected_question)
        self._notify_suggestions_change()

    def clear_answer_context(self):
        """Czyści podpowiedzi odpowiedzi pacjenta."""
        self.selected_question = None
        self.answer_suggestions = []
        self.answer_loading = False
        self._notify_suggestions_change()

    # === STATUS ===

    def set_status(self, status: SessionStatus):
        """Zmienia status sesji."""
        self.status = status
        self._notify_status_change()

    def reset(self):
        """Resetuje stan do początkowego."""
        self.provisional_text = ""
        self.final_text = ""
        self.validated_text = ""
        self._full_transcript = ""
        self._words_since_last_regen = 0
        self.suggestions = []
        self.asked_questions = []
        self.selected_question = None
        self.answer_suggestions = []
        self.answer_loading = False
        self.pending_validation = []
        self.diarization = None
        self.prompter_mode = PrompterMode.SUGGESTIONS
        self.interview_stats = None
        self._recording_start_time = None
        self._notify_transcript_change()
        self._notify_suggestions_change()

    # === MODE & STATS ===

    def set_mode(self, mode: PrompterMode):
        """Zmienia tryb panelu promptera."""
        if self.prompter_mode != mode:
            self.prompter_mode = mode
            print(f"[STATE] Mode changed to: {mode.value}", flush=True)
            self._notify_mode_change()

    def start_recording_timer(self):
        """Rozpoczyna liczenie czasu nagrywania."""
        import time
        self._recording_start_time = time.time()

    def compute_stats(self) -> InterviewStats:
        """Oblicza statystyki sesji."""
        import time

        # Czas nagrywania
        duration = 0.0
        if self._recording_start_time:
            duration = time.time() - self._recording_start_time

        # Liczba słów
        word_count = len(self._full_transcript.split()) if self._full_transcript else 0

        # Liczba mówców
        speaker_count = 0
        if self.diarization and self.diarization.has_data:
            speaker_count = self.diarization.num_speakers

        self.interview_stats = InterviewStats(
            duration_seconds=duration,
            word_count=word_count,
            speaker_count=speaker_count,
            is_complete=True
        )

        return self.interview_stats

    def show_confirmation(self):
        """Przełącza na tryb potwierdzenia zakończenia."""
        self.set_mode(PrompterMode.CONFIRMING)

    def show_summary(self):
        """Przełącza na tryb podsumowania."""
        self.compute_stats()
        self.set_mode(PrompterMode.SUMMARY)

    def cancel_confirmation(self):
        """Anuluje potwierdzenie i wraca do sugestii."""
        self.set_mode(PrompterMode.SUGGESTIONS)

    # === DIARIZATION ===

    def set_diarization_processing(self, processing: bool = True):
        """Ustawia stan przetwarzania diaryzacji."""
        if self.diarization is None:
            self.diarization = DiarizationInfo()
        self.diarization.is_processing = processing
        self._notify_diarization_change()

    def set_diarization_result(self, result: 'DiarizationResult'):
        """Ustawia wynik diaryzacji."""
        from core.diarization import SpeakerRole

        self.diarization = DiarizationInfo(
            segments=result.segments,
            speaker_mapping=result.speaker_mapping,
            num_speakers=result.num_speakers,
            enabled=True,
            is_processing=False
        )
        print(f"[STATE] Diarization set: {len(result.segments)} segments, {result.num_speakers} speakers", flush=True)
        self._notify_diarization_change()

    def toggle_diarization(self) -> bool:
        """Włącza/wyłącza wyświetlanie diaryzacji."""
        if self.diarization is None:
            return False
        self.diarization.enabled = not self.diarization.enabled
        self._notify_diarization_change()
        return self.diarization.enabled

    def swap_speaker_roles(self):
        """Zamienia role mówców (Lekarz <-> Pacjent)."""
        if not self.diarization or not self.diarization.has_data:
            return

        from core.diarization import SpeakerRole

        # Zamień w mapowaniu
        new_mapping = {}
        for speaker_id, role in self.diarization.speaker_mapping.items():
            if role == SpeakerRole.DOCTOR:
                new_mapping[speaker_id] = SpeakerRole.PATIENT
            elif role == SpeakerRole.PATIENT:
                new_mapping[speaker_id] = SpeakerRole.DOCTOR
            else:
                new_mapping[speaker_id] = role

        self.diarization.speaker_mapping = new_mapping

        # Zastosuj do segmentów
        for segment in self.diarization.segments:
            if segment.speaker_id in new_mapping:
                segment.role = new_mapping[segment.speaker_id]

        print(f"[STATE] Speaker roles swapped", flush=True)
        self._notify_diarization_change()

    # === HELPERS ===

    @property
    def full_transcript(self) -> str:
        """Pełna transkrypcja ze wszystkich warstw."""
        return self._full_transcript

    @property
    def words_since_last_regen(self) -> int:
        """Liczba słów od ostatniej regeneracji sugestii."""
        return self._words_since_last_regen

    def has_question_mark(self) -> bool:
        """Sprawdza czy w ostatnim final jest znak zapytania."""
        return "?" in self.final_text

    def _rebuild_full_transcript(self):
        """Odbudowuje pełną transkrypcję."""
        parts = []
        if self.validated_text:
            parts.append(self.validated_text)
        if self.final_text:
            parts.append(self.final_text)
        if self.provisional_text:
            parts.append(self.provisional_text)
        self._full_transcript = " ".join(parts).strip()

    def _smart_join(self, existing: str, new: str) -> str:
        """Inteligentne łączenie tekstu."""
        existing = existing.strip()
        new = new.strip()

        if not existing:
            return new
        if not new:
            return existing

        # Po interpunkcji - spacja
        if existing[-1] in '.!?':
            return existing + ' ' + new

        # Wielka litera = nowe zdanie
        if new[0].isupper():
            return existing + '. ' + new

        return existing + ' ' + new

    def _notify_transcript_change(self):
        if self._on_transcript_change:
            try:
                self._on_transcript_change()
            except Exception as e:
                print(f"[LiveState] Transcript callback error: {e}")

    def _notify_suggestions_change(self):
        if self._on_suggestions_change:
            try:
                self._on_suggestions_change()
            except Exception as e:
                print(f"[LiveState] Suggestions callback error: {e}")

    def _notify_status_change(self):
        if self._on_status_change:
            try:
                self._on_status_change()
            except Exception as e:
                print(f"[LiveState] Status callback error: {e}")

    def _notify_diarization_change(self):
        if self._on_diarization_change:
            try:
                self._on_diarization_change()
            except Exception as e:
                print(f"[LiveState] Diarization callback error: {e}")

    def _notify_mode_change(self):
        if self._on_mode_change:
            try:
                self._on_mode_change()
            except Exception as e:
                print(f"[LiveState] Mode callback error: {e}")
