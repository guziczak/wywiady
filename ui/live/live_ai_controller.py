"""
Live Interview AI Controller
Smart triggers dla regeneracji sugestii i walidacji.
"""

import asyncio
from typing import Optional, TYPE_CHECKING
from enum import Enum
from nicegui import ui, app

if TYPE_CHECKING:
    from ui.live.live_state import LiveState


class TriggerReason(Enum):
    """Powód triggera regeneracji."""
    QUESTION_DETECTED = "question_detected"      # Wykryto ? w transkrypcji
    CARD_CLICKED = "card_clicked"                # User kliknął kartę
    SIGNIFICANT_CONTEXT = "significant_context"  # >50 nowych słów
    INITIAL = "initial"                          # Start sesji
    MANUAL = "manual"                            # Ręczne wywołanie


class AIController:
    """
    Kontroler AI dla Live Interview.
    Zarządza smart triggers zamiast głupiego timera.
    """

    # Konfiguracja triggerów
    MIN_WORDS_FOR_REGEN = 40          # Minimalna liczba nowych słów
    DEBOUNCE_DELAY = 2.0              # Sekundy opóźnienia debounce
    VALIDATION_DELAY = 2.5            # Sekundy przed walidacją segmentu
    REGEN_COOLDOWN = 5.0              # Minimalny czas między regeneracjami

    def __init__(self, state: 'LiveState', llm_service, config):
        self.state = state
        self.llm_service = llm_service
        self.config = config

        # Debounce tasks
        self._regen_task: Optional[asyncio.Task] = None
        self._validation_task: Optional[asyncio.Task] = None

        # Cooldown tracking
        self._last_regen_time: float = 0

        # Callbacks
        self._on_regen_start: Optional[callable] = None
        self._on_regen_end: Optional[callable] = None
        
        # Main event loop reference (set during create_ui)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def on_regen_start(self, callback: callable):
        """Callback gdy zaczyna się regeneracja."""
        self._on_regen_start = callback

    def on_regen_end(self, callback: callable):
        """Callback gdy kończy się regeneracja."""
        self._on_regen_end = callback

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Ustawia referencję do głównego event loop."""
        self._loop = loop

    # === SMART TRIGGERS ===

    def on_final_text(self):
        """
        Wywoływane gdy tekst przechodzi do final (po ciszy).
        Sprawdza czy powinien triggerować regenerację.
        """
        should_regen = False
        reason = None

        # 1. Wykryto pytanie (znak ?)
        if self.state.has_question_mark():
            should_regen = True
            reason = TriggerReason.QUESTION_DETECTED
            print(f"[AI] Trigger: question mark detected", flush=True)

        # 2. Znaczący nowy kontekst (>N słów)
        elif self.state.words_since_last_regen >= self.MIN_WORDS_FOR_REGEN:
            should_regen = True
            reason = TriggerReason.SIGNIFICANT_CONTEXT
            print(f"[AI] Trigger: {self.state.words_since_last_regen} new words", flush=True)

        if should_regen:
            self._schedule_regeneration(reason)

        # Zawsze scheduluj walidację
        self._schedule_validation()

    def on_card_clicked(self, question: str):
        """
        Wywoływane gdy user kliknie kartę z pytaniem.
        Natychmiast triggeruje regenerację.
        """
        print(f"[AI] Trigger: card clicked - '{question[:30]}...'", flush=True)

        # Oznacz jako użyte
        self.state.mark_suggestion_used(question)

        # Natychmiastowa regeneracja (bez debounce)
        self._schedule_regeneration(TriggerReason.CARD_CLICKED, immediate=True)

    def force_regeneration(self):
        """Wymusza regenerację (np. na starcie sesji)."""
        print(f"[AI] Trigger: manual/initial", flush=True)
        self._schedule_regeneration(TriggerReason.INITIAL, immediate=True)

    # === SCHEDULING ===

    def _schedule_regeneration(self, reason: TriggerReason, immediate: bool = False):
        """Scheduluje regenerację z debounce."""
        # Anuluj poprzedni task
        if self._regen_task and not self._regen_task.done():
            self._regen_task.cancel()

        delay = 0 if immediate else self.DEBOUNCE_DELAY
        
        # Użyj głównego event loop (thread-safe)
        if self._loop and self._loop.is_running():
            self._regen_task = asyncio.run_coroutine_threadsafe(
                self._debounced_regeneration(reason, delay),
                self._loop
            )
        else:
            # Fallback - próbuj bezpośrednio (UI thread)
            try:
                self._regen_task = asyncio.create_task(
                    self._debounced_regeneration(reason, delay)
                )
            except RuntimeError:
                print(f"[AI] Cannot schedule regeneration - no event loop", flush=True)

    def _schedule_validation(self):
        """Scheduluje walidację segmentu."""
        # Anuluj poprzedni task
        if self._validation_task and not self._validation_task.done():
            self._validation_task.cancel()

        # Użyj głównego event loop (thread-safe)
        if self._loop and self._loop.is_running():
            self._validation_task = asyncio.run_coroutine_threadsafe(
                self._debounced_validation(),
                self._loop
            )
        else:
            # Fallback - próbuj bezpośrednio (UI thread)
            try:
                self._validation_task = asyncio.create_task(
                    self._debounced_validation()
                )
            except RuntimeError:
                print(f"[AI] Cannot schedule validation - no event loop", flush=True)

    async def _debounced_regeneration(self, reason: TriggerReason, delay: float):
        """Regeneracja z debounce."""
        try:
            if delay > 0:
                await asyncio.sleep(delay)

            # Sprawdź cooldown
            import time
            now = time.time()
            if now - self._last_regen_time < self.REGEN_COOLDOWN:
                remaining = self.REGEN_COOLDOWN - (now - self._last_regen_time)
                print(f"[AI] Cooldown active, waiting {remaining:.1f}s", flush=True)
                await asyncio.sleep(remaining)

            await self._do_regeneration(reason)
            self._last_regen_time = time.time()

        except asyncio.CancelledError:
            print(f"[AI] Regeneration cancelled (newer trigger)", flush=True)
        except Exception as e:
            print(f"[AI] Regeneration error: {e}", flush=True)

    async def _debounced_validation(self):
        """Walidacja z debounce."""
        try:
            await asyncio.sleep(self.VALIDATION_DELAY)
            await self._do_validation()
        except asyncio.CancelledError:
            pass  # Nowy tekst przyszedł, poczekamy
        except Exception as e:
            print(f"[AI] Validation error: {e}", flush=True)

    # === AI OPERATIONS ===

    async def _do_regeneration(self, reason: TriggerReason):
        """Wykonuje regenerację sugestii."""
        if not self.llm_service:
            print(f"[AI] No LLM service available", flush=True)
            return

        if self._on_regen_start:
            self._on_regen_start()

        print(f"[AI] Generating suggestions (reason: {reason.value})...", flush=True)

        try:
            # Pobierz kontekst
            transcript = self.state.full_transcript
            exclude = self.state.asked_questions

            # Generuj sugestie z wykluczeniem użytych
            suggestions = await self.llm_service.generate_suggestions(
                transcript,
                self.config,
                exclude_questions=exclude
            )

            if suggestions:
                self.state.set_suggestions(suggestions[:3])
                print(f"[AI] Generated {len(suggestions)} suggestions", flush=True)
            else:
                print(f"[AI] No suggestions returned", flush=True)

        except Exception as e:
            print(f"[AI] Generation error: {e}", flush=True)
        finally:
            if self._on_regen_end:
                self._on_regen_end()

    async def _do_validation(self):
        """Wykonuje walidację segmentu przez AI."""
        if not self.llm_service:
            return

        # Pobierz segmenty do walidacji
        segments = self.state.clear_pending_validation()
        if not segments:
            return

        combined = " ".join(segments)
        print(f"[AI] Validating: '{combined[:50]}...'", flush=True)

        try:
            result = await self.llm_service.validate_segment(
                segment=combined,
                context=self.state.validated_text,
                suggested_questions=self.state.asked_questions,
                config=self.config
            )

            if result.get("is_complete", False):
                corrected = result.get("corrected_text", combined)
                needs_newline = result.get("needs_newline", False)
                self.state.validate_segment(corrected, needs_newline)
                print(f"[AI] Validated: '{corrected[:50]}...'", flush=True)
            else:
                # Nie kompletne - zwróć do kolejki
                print(f"[AI] Not complete, keeping in queue", flush=True)
                self.state.pending_validation.append(combined)

        except Exception as e:
            print(f"[AI] Validation error: {e}", flush=True)
            # W razie błędu - przepuść bez walidacji
            self.state.validate_segment(combined)

    # === CLEANUP ===

    def stop(self):
        """Zatrzymuje regenerację, ale NIE walidację (niech się dokończy)."""
        if self._regen_task:
            try:
                self._regen_task.cancel()
            except:
                pass
        # Walidacja niech się dokończy - nie anulujemy
        
    def force_stop(self):
        """Zatrzymuje WSZYSTKO (przy zamknięciu)."""
        if self._regen_task:
            try:
                self._regen_task.cancel()
            except:
                pass
        if self._validation_task:
            try:
                self._validation_task.cancel()
            except:
                pass
