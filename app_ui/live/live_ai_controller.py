"""
Live Interview AI Controller
Smart triggers dla regeneracji sugestii i walidacji.
"""

import asyncio
import time
from typing import Optional, List, TYPE_CHECKING
from enum import Enum

from app_ui.live.intent_router import IntentRouter
from app_ui.live.live_state import ConversationMode, CardsMode, Suggestion

if TYPE_CHECKING:
    from app_ui.live.live_state import LiveState


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

    KLUCZOWA ZMIANA (UX fix):
    - Po kliknięciu karty: delay 8s zamiast natychmiastowej regeneracji
    - Pozwala userowi zobaczyć odpowiedzi zanim sugestie się zmienią
    """

    # Konfiguracja triggerów
    MIN_WORDS_FOR_REGEN = 40          # Minimalna liczba nowych słów
    DEBOUNCE_DELAY = 2.0              # Sekundy opóźnienia debounce
    VALIDATION_DELAY = 2.5            # Sekundy przed walidacją segmentu
    REGEN_COOLDOWN = 5.0              # Minimalny czas między regeneracjami

    # NOWE: Delay po kliknięciu karty (żeby user widział odpowiedzi)
    CARD_CLICK_REGEN_DELAY = 8.0      # Sekundy przed regeneracją po kliknięciu

    # Q+A matching configuration
    QA_TIMEOUT_SECONDS = 120.0        # Okno czasowe na odpowiedź (zwiększone z 60s)
    QA_MIN_WORDS = 3                  # Minimalna liczba słów w odpowiedzi (zmniejszone z 5)
    MANUAL_OVERRIDE_TTL = 90.0        # Jak długo utrzymać tryb z ręcznej pary Q+A
    FREEZE_DECISION_AUTO_REGEN = True # W trybie poradniczym nie odswiezaj automatycznie

    def __init__(self, state: 'LiveState', llm_service, config):
        self.state = state
        self.llm_service = llm_service
        self.config = config
        self.intent_router = IntentRouter(llm_service=llm_service, config=config)

        # Debounce tasks
        self._regen_task: Optional[asyncio.Task] = None
        self._validation_task: Optional[asyncio.Task] = None

        # Cooldown tracking
        self._last_regen_time: float = 0
        self._last_processed_text_len: int = 0  # Długość tekstu przy ostatnim triggerze

        # Callbacks
        self._on_regen_start: Optional[callable] = None
        self._on_regen_end: Optional[callable] = None
        
        # Main event loop reference (set during create_ui)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # ID specjalizacji (do kontekstowych sugestii) - multi-select
        self.current_spec_ids: Optional[List[int]] = None

        # Manual Q+A context (np. wybrane odpowiedzi nieobecne w transkrypcji)
        self._manual_mode_override: Optional[ConversationMode] = None
        self._manual_mode_until: float = 0.0
        self._manual_context: Optional[str] = None
        self._manual_context_until: float = 0.0

    def on_regen_start(self, callback: callable):
        """Callback gdy zaczyna się regeneracja."""
        self._on_regen_start = callback

    def on_regen_end(self, callback: callable):
        """Callback gdy kończy się regeneracja."""
        self._on_regen_end = callback

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Ustawia referencję do głównego event loop."""
        self._loop = loop

    def set_spec_ids(self, spec_ids: List[int]):
        """Ustawia listę aktywnych specjalizacji (multi-select)."""
        self.current_spec_ids = spec_ids

    # === SMART TRIGGERS ===

    def on_final_text(self):
        """
        Wywoływane gdy tekst przechodzi do final (po ciszy).
        Sprawdza czy powinien triggerować regenerację.
        """
        should_regen = False
        reason = None
        
        current_len = len(self.state.full_transcript)
        # Ignoruj jeśli tekst się nie zmienił lub urósł minimalnie (<5 znaków)
        if current_len - self._last_processed_text_len < 5:
            return

        auto_allowed = not self._is_decision_freeze()

        # 1. Wykryto pytanie (znak ?)
        if self.state.has_question_mark():
            # Sprawdź czy to NOWE pytanie (tekst urósł od ostatniego razu)
            # has_question_mark sprawdza ostatni segment, ale my chcemy unikać spamu
            should_regen = True
            reason = TriggerReason.QUESTION_DETECTED
            print(f"[AI] Trigger: question mark detected", flush=True)

        # 2. Znaczący nowy kontekst (>N słów)
        elif self.state.words_since_last_regen >= self.MIN_WORDS_FOR_REGEN:
            should_regen = True
            reason = TriggerReason.SIGNIFICANT_CONTEXT
            print(f"[AI] Trigger: {self.state.words_since_last_regen} new words", flush=True)

        if should_regen:
            self._last_processed_text_len = current_len
            if auto_allowed:
                self._schedule_regeneration(reason)
            else:
                print(f"[AI] Auto regen blocked (decision mode)", flush=True)
                if reason == TriggerReason.QUESTION_DETECTED:
                    try:
                        self.state.set_return_to_questions_hint(True)
                    except Exception:
                        pass

        # Zawsze scheduluj walidację
        self._schedule_validation()

    def on_card_clicked(self, suggestion):
        """
        Wywolywane gdy user kliknie karte sugestii.

        Dla pytan: opozniona regeneracja (czas na odpowiedzi).
        Dla skryptow/checklisty: szybsza regeneracja.
        """
        if isinstance(suggestion, Suggestion):
            text = suggestion.question
            kind = suggestion.kind or "question"
        else:
            text = str(suggestion)
            kind = "question"

        print(f"[AI] Trigger: card clicked ({kind}) - '{text[:30]}...'", flush=True)

        # Oznacz jako uzyte
        self.state.mark_suggestion_used(suggestion)

        # Opozniona regeneracja tylko dla pytan (check/skrypt nie powinny resetowac checklisty)
        if kind == "question" and not self._is_decision_freeze():
            delay = self.CARD_CLICK_REGEN_DELAY
            self._schedule_regeneration(
                TriggerReason.CARD_CLICKED,
                immediate=False,
                delay=delay
            )

    def on_qa_pair_created(self, question: str, answer: str):
        """Reakcja na ręcznie wybraną parę Q+A (np. z kart odpowiedzi)."""
        if not question and not answer:
            return

        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._handle_qa_pair(question, answer),
                self._loop
            )
        else:
            try:
                asyncio.create_task(self._handle_qa_pair(question, answer))
            except RuntimeError:
                print(f"[AI] Cannot handle Q+A - no event loop", flush=True)

    async def _handle_qa_pair(self, question: str, answer: str):
        """Wymusza intent routing na bazie ręcznej pary Q+A."""
        text_parts = []
        if question:
            text_parts.append(f"Pytanie: {question}")
        if answer:
            text_parts.append(f"Odpowiedz: {answer}")
        combined = "\n".join(text_parts).strip()
        if not combined:
            return

        now = time.time()
        self._manual_context = combined
        self._manual_context_until = now + self.MANUAL_OVERRIDE_TTL

        try:
            intent = await self.intent_router.classify(
                combined,
                spec_ids=self.current_spec_ids,
                force=True
            )
        except Exception as e:
            print(f"[AI] Intent routing error (QA): {e}", flush=True)
            intent = None

        if intent:
            # Dla trybu DECISION zawsze wymus (mini-gra/checklista)
            if intent.mode == ConversationMode.DECISION:
                self._manual_mode_override = intent.mode
                self._manual_mode_until = now + self.MANUAL_OVERRIDE_TTL
                self.state.set_conversation_mode(intent.mode, intent.confidence, f"qa:{intent.reason}")
            else:
                # Aktualizuj tryb tylko przy mocniejszej pewności
                if intent.confidence >= 0.65 and intent.mode != ConversationMode.GENERAL:
                    self._manual_mode_override = intent.mode
                    self._manual_mode_until = now + self.MANUAL_OVERRIDE_TTL
                    self.state.set_conversation_mode(intent.mode, intent.confidence, f"qa:{intent.reason}")

        # Wymus szybka regeneracja
        self._schedule_regeneration(TriggerReason.MANUAL, immediate=True)

    def force_regeneration(self):
        """Wymusza regenerację (np. na starcie sesji)."""
        print(f"[AI] Trigger: manual/initial", flush=True)
        # Reset manual overrides at session start
        self._manual_mode_override = None
        self._manual_mode_until = 0.0
        self._manual_context = None
        self._manual_context_until = 0.0
        self._schedule_regeneration(TriggerReason.INITIAL, immediate=True)

    def request_new_pool(self, force_decision: bool = False):
        """Ręczne odświeżenie puli kart (np. przycisk Nowa pula)."""
        now = time.time()
        if force_decision and self.state.conversation_mode == ConversationMode.DECISION:
            self._manual_mode_override = ConversationMode.DECISION
            self._manual_mode_until = now + self.MANUAL_OVERRIDE_TTL
        self._schedule_regeneration(TriggerReason.MANUAL, immediate=True)

    def _is_decision_freeze(self) -> bool:
        if not self.FREEZE_DECISION_AUTO_REGEN:
            return False
        cards_mode = getattr(self.state, "cards_mode", CardsMode.AUTO)
        if cards_mode == CardsMode.QUESTIONS:
            return False
        return self.state.conversation_mode == ConversationMode.DECISION

    # === SCHEDULING ===

    def _schedule_regeneration(self, reason: TriggerReason, immediate: bool = False, delay: float = None):
        """
        Scheduluje regenerację z debounce.

        Args:
            reason: Powód regeneracji
            immediate: Jeśli True, bez delay (0s)
            delay: Opcjonalny custom delay (nadpisuje immediate i DEBOUNCE_DELAY)
        """
        # Anuluj poprzedni task
        if self._regen_task and not self._regen_task.done():
            self._regen_task.cancel()

        # Określ delay
        if delay is not None:
            final_delay = delay
        elif immediate:
            final_delay = 0
        else:
            final_delay = self.DEBOUNCE_DELAY

        delay = final_delay
        
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
        # NIE anuluj poprzedniej walidacji - niech się dokończy
        # (anulowanie powoduje utratę segmentów bo clear_pending jest wywoływane przed LLM)
        if self._validation_task and not self._validation_task.done():
            # Poprzednia walidacja w toku - nie scheduluj nowej, ta pobierze wszystkie segmenty
            return

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
        """Walidacja z debounce - pętla do wyczerpania pending."""
        try:
            while True:
                await asyncio.sleep(self.VALIDATION_DELAY)

                # Sprawdź czy są segmenty do walidacji
                if not self.state.pending_validation:
                    break

                await self._do_validation()

                # Po walidacji sprawdź czy przyszły nowe segmenty
                # (mogły przyjść podczas wywołania LLM)
                if not self.state.pending_validation:
                    break
                # Jeśli są nowe - kontynuuj pętlę (z nowym delay)

        except asyncio.CancelledError:
            pass  # Stop sesji
        except Exception as e:
            print(f"[AI] Validation error: {e}", flush=True)

    # === AI OPERATIONS ===

    async def _do_regeneration(self, reason: TriggerReason):
        """Wykonuje regeneracje sugestii."""
        if self._on_regen_start:
            self._on_regen_start()

        print(f"[AI] Generating suggestions (reason: {reason.value})...", flush=True)

        transcript = self.state.full_transcript

        # Manual override/context (np. wybrane odpowiedzi nieobecne w transkrypcji)
        now = time.time()
        manual_override = None
        if self._manual_mode_override and now <= self._manual_mode_until:
            manual_override = self._manual_mode_override
        else:
            self._manual_mode_override = None

        manual_context = None
        if self._manual_context and now <= self._manual_context_until:
            manual_context = self._manual_context
        else:
            self._manual_context = None

        if manual_context:
            if transcript:
                transcript_for_llm = f"{transcript}\n\n[Manual Q+A]\n{manual_context}"
            else:
                transcript_for_llm = manual_context
        else:
            transcript_for_llm = transcript

        # 1) Intent routing (mode)
        if manual_override:
            mode = manual_override
        else:
            try:
                intent = await self.intent_router.classify(transcript_for_llm, spec_ids=self.current_spec_ids)
                if intent:
                    self.state.set_conversation_mode(intent.mode, intent.confidence, intent.reason)
            except Exception as e:
                print(f"[AI] Intent routing error: {e}", flush=True)
        mode = self.state.conversation_mode
        cards_mode = getattr(self.state, "cards_mode", CardsMode.AUTO)
        use_decision_cards = (
            cards_mode == CardsMode.DECISION
            or (cards_mode == CardsMode.AUTO and mode == ConversationMode.DECISION)
        )
        if not use_decision_cards:
            try:
                self.state.set_return_to_questions_hint(False)
            except Exception:
                pass

        # 2) Jeśli brak LLM - uzyj fallback (tylko tryb poradniczy)
        if not self.llm_service:
            fallback = self._fallback_cards_for_mode(ConversationMode.DECISION if use_decision_cards else mode)
            if fallback:
                self.state.set_suggestions(fallback)
            if self._on_regen_end:
                self._on_regen_end()
            return

        try:
            if use_decision_cards:
                cards = await self.llm_service.generate_decision_cards(
                    transcript_for_llm,
                    self.config,
                    spec_ids=self.current_spec_ids
                )
                has_support = False
                for item in cards or []:
                    if isinstance(item, dict):
                        kind = (item.get("type") or item.get("kind") or "").strip().lower()
                    elif isinstance(item, Suggestion):
                        kind = (item.kind or "").strip().lower()
                    else:
                        kind = ""
                    if kind in ("check", "script"):
                        has_support = True
                        break
                if not cards or not has_support:
                    cards = self._fallback_cards_for_mode(ConversationMode.DECISION)
                    if cards:
                        print("[AI] Decision cards fallback used", flush=True)
                if cards:
                    self.state.set_suggestions(cards)
                    print(f"[AI] Generated {len(cards)} decision cards", flush=True)
                else:
                    print("[AI] No decision cards returned", flush=True)
            else:
                exclude = self.state.asked_questions
                suggestions = await self.llm_service.generate_suggestions(
                    transcript_for_llm,
                    self.config,
                    exclude_questions=exclude,
                    spec_ids=self.current_spec_ids
                )

                if suggestions:
                    self.state.set_suggestions(suggestions[:3])
                    print(f"[AI] Generated {len(suggestions)} suggestions", flush=True)
                else:
                    print("[AI] No suggestions returned", flush=True)

        except Exception as e:
            print(f"[AI] Generation error: {e}", flush=True)
        finally:
            if self._on_regen_end:
                self._on_regen_end()

    def _fallback_cards_for_mode(self, mode: ConversationMode):
        if mode == ConversationMode.DECISION:
            return [
                {"type": "check", "text": "Preferencje pacjenta (skutecznosc / wygoda)"},
                {"type": "check", "text": "Plany na najblizsze miesiace / czas stosowania"},
                {"type": "script", "text": "Omowie krotko dostepne opcje i roznice."},
            ]
        return []

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

            corrected = result.get("corrected_text", combined)
            needs_newline = result.get("needs_newline", False)

            # === SAFETY CHECK (GUARDRAILS) ===
            # Sprawdź czy AI nie zwariowało (np. zamiana długiego zdania na "Dziękuję")
            len_in = len(combined)
            len_out = len(corrected)
            
            # Jeśli tekst skurczył się o ponad 30% lub zmienił się drastycznie przy krótkim tekście
            is_suspicious = False
            if len_in > 10 and len_out < len_in * 0.7:
                is_suspicious = True
            elif len_in > 5 and len_out < 3: # "Co tam..." -> "."
                is_suspicious = True
            
            if is_suspicious:
                print(f"[AI] REJECTED HALLUCINATION: '{combined}' -> '{corrected}'", flush=True)
                # Użyj oryginału, ale spróbuj zachować newline jeśli AI wykryło
                corrected = combined
            
            self.state.validate_segment(corrected, needs_newline)
            print(f"[AI] Validated: '{corrected[:50]}...'", flush=True)

            # === Q+A MATCHING ===
            # Sprawdź czy to odpowiedź na oczekujące pytanie
            if self._is_answer_to_pending_question(corrected):
                pair = self.state.complete_qa_pair(corrected)
                if pair:
                    print(f"[AI] Q+A pair matched!", flush=True)

        except Exception as e:
            print(f"[AI] Validation error: {e}", flush=True)
            # W razie błędu - przepuść bez walidacji
            self.state.validate_segment(combined)

    def _is_answer_to_pending_question(self, text: str) -> bool:
        """
        Sprawdza czy tekst jest odpowiedzią na aktywne pytanie.

        Używa nowego ActiveQuestionContext zamiast starego pending_question.

        Kryteria:
        - Jest aktywne pytanie w stanie READY lub WAITING
        - Nie minął timeout
        - Tekst ma minimum QA_MIN_WORDS słów
        - Tekst NIE kończy się znakiem zapytania (to byłoby pytanie)
        """
        active = self.state.active_question

        # Sprawdź czy jest aktywne pytanie gotowe do dopasowania
        if not active.is_ready_for_match:
            return False

        # Sprawdź timeout (active_question sam to obsłuży, ale sprawdźmy)
        if active.check_timeout():
            print(f"[AI] Q+A timeout expired", flush=True)
            return False

        # Sprawdź długość tekstu
        word_count = len(text.split())
        if word_count < self.QA_MIN_WORDS:
            print(f"[AI] Q+A too short: {word_count} < {self.QA_MIN_WORDS} words", flush=True)
            return False

        # Sprawdź że nie kończy się znakiem zapytania (to byłoby pytanie, nie odpowiedź)
        text_stripped = text.strip()
        if text_stripped.endswith('?'):
            print(f"[AI] Q+A rejected: ends with '?' (likely a question)", flush=True)
            return False

        elapsed = active.time_elapsed
        print(f"[AI] Q+A match criteria passed (words={word_count}, elapsed={elapsed:.1f}s)", flush=True)
        return True

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




