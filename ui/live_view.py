from nicegui import ui
from ui.components.header import create_header
import asyncio

try:
    from core.streaming_service import StreamingTranscriber
except ImportError:
    StreamingTranscriber = None


class LiveInterviewView:
    """
    Widok Live Interview z 4-warstwową kaskadową transkrypcją:
    - Warstwa 1 (provisional): jasny szary, italic - real-time
    - Warstwa 2 (improved): ciemniejszy szary - kontekstowy
    - Warstwa 3 (final): czarny, NIE pogrubiony - po ciszy
    - Warstwa 4 (validated): czarny, POGRUBIONY - po walidacji AI
    """

    def __init__(self, app):
        self.app = app
        self.is_running = False
        self.suggestions_container = None
        self.transcriber = StreamingTranscriber(model_size="small") if StreamingTranscriber else None

        # Transkrypcja - 4 warstwy
        self.provisional_text = ""   # Szary jasny (real-time)
        self.final_text = ""         # Czarny niepogrubiony (po ciszy, czeka na walidację)
        self.validated_text = ""     # Czarny pogrubiony (po AI)

        # Kolejka do walidacji AI
        self.pending_validation = []  # Segmenty czekające na walidację

        # AI State
        self.full_transcript = ""
        self.last_ai_processed_len = 0
        self.ai_timer = None
        self.current_suggestions = []  # Aktualne pytania sugerowane

        # UI elements
        self.transcript_html = None

    def create_ui(self):
        # Timers
        ui.timer(1.0, self.app._update_status_ui)
        self.ai_timer = ui.timer(8.0, self._ai_loop)

        # Timer do walidacji AI (co 3s sprawdzamy czy jest coś do walidacji)
        ui.timer(3.0, self._validation_loop)

        # Header
        create_header(self.app)

        with ui.column().classes('w-full h-[calc(100vh-100px)] p-4 gap-4'):

            # === GÓRA: TRANSKRYPCJA ===
            with ui.card().classes('w-full flex-grow bg-gray-50 overflow-y-auto p-6 relative') as self.transcript_card:
                ui.label('Transkrypcja na żywo').classes('text-xs text-gray-400 absolute top-2 left-4')
                self.transcript_html = ui.html('', sanitize=False).classes('text-xl leading-relaxed mt-4')
                self._update_transcript_display()

            # === DÓŁ: SUFLER ===
            with ui.card().classes('w-full h-1/3 p-4 rounded-none').style(
                'background: linear-gradient(180deg, #1a1a1a 0%, #0f0f0f 100%);'
                'border-top: 3px solid #c9a227;'
            ):
                with ui.row().classes('w-full justify-between items-center mb-3'):
                    ui.label('AI Asystent').classes('font-light text-[#c9a227] text-xl tracking-widest uppercase')
                    with ui.row().classes('gap-4 items-center'):
                        self.status_badge = ui.badge('GOTOWY', color='gray')
                        self.action_btn = ui.button('START', icon='mic', color='green', on_click=self.toggle_session).props('size=lg')
                        # Przycisk zakończenia wywiadu
                        ui.button('Zakończ wywiad', icon='check_circle', color='amber', on_click=self._finish_interview).props('outline size=md').classes('ml-4')

                self.suggestions_container = ui.row().classes('w-full gap-6 justify-center')
                with self.suggestions_container:
                    self._create_placeholder_suggestion("Tu pojawią się pytania...")
                    self._create_placeholder_suggestion("Analizuję rozmowę...")
                    self._create_placeholder_suggestion("Czekam na kontekst...")

    def _create_placeholder_suggestion(self, text):
        with ui.card().classes(
            'w-72 h-48 flex items-center justify-center rounded-xl border-2 border-[#3d3d3d] opacity-40'
        ).style(
            'background: linear-gradient(145deg, #2a2a2a 0%, #1a1a1a 100%);'
        ):
            ui.label(text).classes('text-center text-[#666] font-light italic text-sm')

    def _create_suggestion_card(self, question: str):
        """Karta pytania w stylu Gwint - ciemna, klimatyczna."""
        with ui.card().classes(
            'w-72 h-48 flex flex-col items-center justify-center p-4 '
            'rounded-xl cursor-pointer transition-all duration-300 '
            'hover:scale-105 hover:-translate-y-1 relative overflow-hidden'
        ).style(
            'background: linear-gradient(145deg, #2d2d2d 0%, #1a1a1a 50%, #0d0d0d 100%);'
            'border: 2px solid #4a4a4a;'
            'box-shadow: 0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.05);'
        ):
            # Górna ramka ozdobna (złoto-brązowa)
            ui.element('div').classes('absolute top-0 left-0 w-full h-1').style(
                'background: linear-gradient(90deg, transparent 0%, #8b7355 20%, #c9a227 50%, #8b7355 80%, transparent 100%);'
            )

            # Ikona pytania
            ui.icon('help_outline', size='sm').classes('text-[#c9a227] mb-2 opacity-70')

            # Tekst pytania
            ui.label(question).classes(
                'text-center text-[#e8e8e8] text-base leading-relaxed px-3 font-light'
            ).style('text-shadow: 0 2px 4px rgba(0,0,0,0.5);')

            # Dolna ramka ozdobna
            ui.element('div').classes('absolute bottom-0 left-0 w-full h-1').style(
                'background: linear-gradient(90deg, transparent 0%, #8b7355 20%, #c9a227 50%, #8b7355 80%, transparent 100%);'
            )

            # Subtelny efekt winiety w rogach
            ui.element('div').classes('absolute inset-0 pointer-events-none').style(
                'background: radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.3) 100%);'
            )

    def _update_transcript_display(self):
        """Renderuje transkrypcję z 4 warstwami kolorystycznymi."""
        if not self.transcript_html:
            return

        html_parts = []

        # 1. Validated (czarny, pogrubiony) - AI potwierdzone
        if self.validated_text:
            # Zamieniamy \n na <br> dla nowych linii
            validated_html = self.validated_text.replace('\n', '<br>')
            html_parts.append(f'<span style="color: #1a1a1a; font-weight: 600;">{validated_html}</span>')

        # 2. Final (czarny, NIE pogrubiony) - po ciszy, czeka na walidację
        if self.final_text:
            final_html = self.final_text.replace('\n', '<br>')
            html_parts.append(f'<span style="color: #1a1a1a; font-weight: 400;">{final_html}</span>')

        # 3. Provisional (szary, italic) - real-time
        if self.provisional_text:
            prov_html = self.provisional_text.replace('\n', '<br>')
            html_parts.append(f'<span style="color: #6b7280; font-style: italic;">{prov_html}</span>')

        if html_parts:
            self.transcript_html.content = ' '.join(html_parts)
        else:
            self.transcript_html.content = '<span style="color: #9ca3af; font-style: italic;">Naciśnij START aby rozpocząć...</span>'

    def toggle_session(self):
        if not self.transcriber:
            ui.notify("Brak biblioteki faster-whisper", type='negative')
            return

        self.is_running = not self.is_running
        if self.is_running:
            self.action_btn.props('color=red icon=stop')
            self.action_btn.text = 'STOP'
            self.status_badge.text = 'NAGRYWANIE'
            self.status_badge.props('color=red animate-pulse')

            # Reset
            self.provisional_text = ""
            self.final_text = ""
            self.validated_text = ""
            self.full_transcript = ""
            self.pending_validation = []
            self.current_suggestions = []
            self._update_transcript_display()

            # START STREAMING
            self.transcriber.start(
                callback_provisional=self._on_provisional,
                callback_improved=self._on_improved,
                callback_final=self._on_final
            )

            asyncio.create_task(self._ai_loop_force())
            ui.notify("Sesja live uruchomiona!", type='positive')
        else:
            self.action_btn.props('color=green icon=mic')
            self.action_btn.text = 'START'
            self.status_badge.text = 'ZATRZYMANO'
            self.status_badge.props('color=gray')

            if self.transcriber:
                self.transcriber.force_finalize()
                self.transcriber.stop()

    def _on_provisional(self, text, start_sample, end_sample):
        """Warstwa 1: Real-time (jasny szary)."""
        text = text.strip()
        if not text:
            return

        print(f"[LIVE] Provisional: {text[:50]}...", flush=True)

        # Provisional kumuluje się (do czasu improved)
        self.provisional_text = self._smart_join(self.provisional_text, text)
        self._rebuild_full_transcript()

        try:
            self._update_transcript_display()
        except Exception as e:
            print(f"[LIVE] UI error: {e}", flush=True)

    def _on_improved(self, text, start_sample, end_sample):
        """Warstwa 2: Kontekstowy (ciemniejszy szary) - zastępuje provisional."""
        text = text.strip()
        if not text:
            return

        print(f"[LIVE] Improved: {text[:50]}...", flush=True)

        # Improved ZASTĘPUJE provisional (ma lepszy kontekst)
        self.provisional_text = text
        self._rebuild_full_transcript()

        try:
            self._update_transcript_display()
        except Exception as e:
            print(f"[LIVE] UI error: {e}", flush=True)

    def _on_final(self, text, start_sample, end_sample):
        """Warstwa 3: Po ciszy (czarny, niepogrubiony) - czeka na walidację AI."""
        text = text.strip()
        if not text:
            return

        print(f"[LIVE] Final: {text[:50]}...", flush=True)

        # Przenieś z provisional do final
        self.final_text = self._smart_join(self.final_text, text)
        self.provisional_text = ""  # Wyczyść provisional

        # Dodaj do kolejki walidacji
        self.pending_validation.append(text)

        self._rebuild_full_transcript()

        try:
            self._update_transcript_display()
        except Exception as e:
            print(f"[LIVE] UI error: {e}", flush=True)

    async def _validation_loop(self):
        """Pętla walidacji AI - sprawdza co 3s czy jest coś do walidacji."""
        if not self.is_running or not self.app.llm_service:
            return

        if not self.pending_validation:
            return

        # Weź wszystkie oczekujące segmenty
        segments_to_validate = self.pending_validation.copy()
        self.pending_validation = []

        combined_segment = " ".join(segments_to_validate)

        print(f"[LIVE] Validating: {combined_segment[:50]}...", flush=True)

        try:
            result = await self.app.llm_service.validate_segment(
                segment=combined_segment,
                context=self.validated_text,
                suggested_questions=self.current_suggestions,
                config=self.app.config
            )

            if result.get("is_complete", False):
                # AI potwierdza - przenieś do validated
                corrected = result.get("corrected_text", combined_segment)
                needs_newline = result.get("needs_newline", False)

                # Dodaj newline jeśli trzeba
                if needs_newline and self.validated_text:
                    self.validated_text = self.validated_text.rstrip() + "\n"

                self.validated_text = self._smart_join(self.validated_text, corrected)

                # Wyczyść final (został zwalidowany)
                self.final_text = ""

                print(f"[LIVE] Validated: {corrected[:50]}...", flush=True)
            else:
                # Nie kompletne - zostaw w final, może dojdzie więcej
                print(f"[LIVE] Not complete yet, keeping in final", flush=True)
                # Zwróć do pending (poczekamy na więcej tekstu)
                self.pending_validation.append(combined_segment)

            self._rebuild_full_transcript()
            self._update_transcript_display()

        except Exception as e:
            print(f"[LIVE] Validation error: {e}", flush=True)
            # W razie błędu - przepuść bez walidacji
            self.validated_text = self._smart_join(self.validated_text, combined_segment)
            self.final_text = ""
            self._rebuild_full_transcript()
            self._update_transcript_display()

    def _rebuild_full_transcript(self):
        """Odbudowuje pełną transkrypcję ze wszystkich warstw."""
        parts = []
        if self.validated_text:
            parts.append(self.validated_text)
        if self.final_text:
            parts.append(self.final_text)
        if self.provisional_text:
            parts.append(self.provisional_text)
        self.full_transcript = " ".join(parts).strip()

    def _smart_join(self, existing: str, new: str) -> str:
        """Inteligentne łączenie tekstu."""
        existing = existing.strip()
        new = new.strip()

        if not existing:
            return new
        if not new:
            return existing

        # Jeśli existing kończy się interpunkcją, dodaj spację
        if existing[-1] in '.!?':
            return existing + ' ' + new

        # Jeśli new zaczyna się wielką literą, to prawdopodobnie nowe zdanie
        if new[0].isupper():
            return existing + '. ' + new

        return existing + ' ' + new

    async def _ai_loop_force(self):
        """Wymusza generowanie pytań na starcie."""
        if not self.app.llm_service:
            return
        print("[LIVE] Force generating initial suggestions...", flush=True)
        try:
            suggestions = await self.app.llm_service.generate_suggestions(self.full_transcript, self.app.config)
            if suggestions:
                self.current_suggestions = suggestions[:3]
                self.suggestions_container.clear()
                with self.suggestions_container:
                    for q in self.current_suggestions:
                        self._create_suggestion_card(q)
        except Exception as e:
            print(f"[LIVE] Force AI error: {e}", flush=True)

    async def _ai_loop(self):
        """Cykliczne generowanie pytań."""
        if not self.is_running or not self.app.llm_service:
            return

        current_len = len(self.full_transcript)
        if current_len - self.last_ai_processed_len < 10:
            return

        print(f"[LIVE] Generating suggestions...", flush=True)
        self.last_ai_processed_len = current_len

        try:
            suggestions = await self.app.llm_service.generate_suggestions(self.full_transcript, self.app.config)

            if suggestions:
                self.current_suggestions = suggestions[:3]
                self.suggestions_container.clear()
                with self.suggestions_container:
                    for q in self.current_suggestions:
                        self._create_suggestion_card(q)
            else:
                print("[LIVE] No suggestions returned", flush=True)

        except Exception as e:
            print(f"[LIVE] AI error: {e}", flush=True)

    def _finish_interview(self):
        """Kończy wywiad i przekazuje transkrypt do głównego widoku."""
        # Zatrzymaj nagrywanie jeśli aktywne
        if self.is_running:
            self.is_running = False
            if self.transcriber:
                self.transcriber.force_finalize()
                self.transcriber.stop()

        # Zbierz pełny transkrypt (validated + final + provisional)
        final_transcript = ""
        if self.validated_text:
            final_transcript += self.validated_text
        if self.final_text:
            if final_transcript:
                final_transcript += " "
            final_transcript += self.final_text
        if self.provisional_text:
            if final_transcript:
                final_transcript += " "
            final_transcript += self.provisional_text

        final_transcript = final_transcript.strip()

        if not final_transcript:
            ui.notify("Brak transkryptu do zapisania", type='warning')
            return

        # Zapisz transkrypt w storage użytkownika (persystentne między stronami)
        from nicegui import app
        app.storage.user['live_transcript'] = final_transcript
        print(f"[LIVE] Saved transcript ({len(final_transcript)} chars) to app.storage.user", flush=True)

        ui.notify("Wywiad zakończony! Przekierowuję...", type='positive')

        # Przekieruj do głównej strony
        ui.navigate.to('/')
