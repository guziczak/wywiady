"""
Live Interview View - Refactored
Główny widok Live Interview z komponentami i smart AI triggers.
"""

from nicegui import ui, app
import asyncio
from typing import Optional

from app_ui.components.header import create_header
from app_ui.live.live_state import LiveState, SessionStatus
from app_ui.live.live_ai_controller import AIController
from app_ui.live.components.transcript_panel import TranscriptPanel
from app_ui.live.components.prompter_panel import PrompterPanel

# Streaming transcriber (opcjonalny)
try:
    from core.streaming_service import StreamingTranscriber
except ImportError:
    StreamingTranscriber = None

# Diarization service (opcjonalny)
try:
    from core.diarization import get_diarization_service, DiarizationService
    DIARIZATION_AVAILABLE = True
except ImportError:
    get_diarization_service = None
    DiarizationService = None
    DIARIZATION_AVAILABLE = False


class LiveInterviewView:
    """
    Widok Live Interview - zrefaktoryzowany.

    Architektura:
    - LiveState: centralny stan (transcript, suggestions)
    - AIController: smart triggers dla AI
    - TranscriptPanel: UI transkrypcji
    - PrompterPanel: UI suflera z kartami
    """

    def __init__(self, app_instance):
        self.app = app_instance

        # Stan
        self.state = LiveState()

        # AI Controller
        self.ai_controller = AIController(
            state=self.state,
            llm_service=self.app.llm_service,
            config=self.app.config
        )

        # Streaming transcriber
        self.transcriber = None
        if StreamingTranscriber:
            try:
                # Sprawdź czy używamy OpenVINO (sprawdź config bezpośrednio dla pewności)
                use_openvino = False
                config_backend = self.app.config.get("transcriber_backend", "")
                if config_backend == "openvino_whisper":
                    use_openvino = True
                    print("[LIVE] Using OpenVINO (detected from config)", flush=True)
                elif self.app.transcriber_manager:
                    from core.transcriber import TranscriberType
                    if self.app.transcriber_manager.get_current_type() == TranscriberType.OPENVINO_WHISPER:
                        use_openvino = True
                        print("[LIVE] Using OpenVINO (detected from manager)", flush=True)

                # Pobierz wybrane urządzenie z configu
                # Uwaga: self.app.config to ConfigManager instance
                selected_device = self.app.config.get("selected_device", "auto")
                print(f"[LIVE] Config reports selected_device: '{selected_device}'", flush=True)
                
                # Jeśli auto, pozwól OpenVINO zdecydować (lub jeśli backend to faster-whisper, auto=cpu/cuda)
                
                print(f"[LIVE] Initializing StreamingTranscriber with device={selected_device} (OpenVINO={use_openvino})", flush=True)
                self.transcriber = StreamingTranscriber(
                    model_size="tiny", 
                    use_openvino=use_openvino,
                    device=selected_device
                )
                
                # Asynchroniczne ładowanie modeli (non-blocking UI)
                # Przeniesione do _start_background_loading wywoływanego przez timer
                
            except Exception as e:
                print(f"[LIVE] Could not init transcriber: {e}", flush=True)

        # UI Components
        self.transcript_panel: Optional[TranscriptPanel] = None
        self.prompter_panel: Optional[PrompterPanel] = None

        # Diarization service
        self.diarization_service: Optional[DiarizationService] = None
        if DIARIZATION_AVAILABLE:
            self.diarization_service = get_diarization_service()
            print(f"[LIVE] Diarization available: {self.diarization_service.backend.name if self.diarization_service.backend else 'None'}", flush=True)

        # Model status refs
        self._model_status_container = None

    def create_ui(self):
        """Buduje interfejs użytkownika."""

        # Timer do aktualizacji statusu w headerze
        ui.timer(1.0, self.app._update_status_ui)
        # Timer do aktualizacji statusu modeli
        ui.timer(2.0, self._update_model_status)
        
        # Timer do rozpoczęcia ładowania modeli (po załadowaniu UI)
        ui.timer(1.0, self._start_background_loading, once=True)

        # Header (z głównej aplikacji)
        create_header(self.app)
        
        # Model Info Bar (new)
        self._create_model_info_bar()

        # Main layout
        with ui.column().classes(
            'w-full h-[calc(100vh-100px)] '  # Adjusted for model bar
            'p-2 sm:p-4 '
            'gap-2 sm:gap-4 '
            'max-w-6xl mx-auto'
        ):
            # === GÓRA: TRANSKRYPCJA ===
            with ui.element('div').classes('w-full flex-1 min-h-[200px] overflow-hidden'):
                self.transcript_panel = TranscriptPanel(self.state)
                self.transcript_panel.create()

            # === DÓŁ: SUFLER ===
            with ui.element('div').classes('w-full shrink-0'):
                self.prompter_panel = PrompterPanel(
                    state=self.state,
                    app_instance=self.app,
                    on_toggle_session=self._toggle_session,
                    on_finish=self._finish_interview,
                    on_card_click=self._on_card_click
                )
                self.prompter_panel.create()

        # AI Controller callbacks
        self.ai_controller.on_regen_start(self._on_ai_start)
        self.ai_controller.on_regen_end(self._on_ai_end)
        
        # Cleanup on disconnect
        ui.context.client.on_disconnect(self._on_disconnect)

    async def _on_disconnect(self):
        """Sprzątanie po zamknięciu karty."""
        print("[LIVE] Client disconnected, cleaning up...", flush=True)
        if self.transcriber:
            self.transcriber.stop()
        if self.ai_controller:
            self.ai_controller.force_stop()

    async def _start_background_loading(self):
        """Ładuje modele w tle po załadowaniu UI."""
        if not self.transcriber:
            return
            
        print("[LIVE] Starting async model preload...", flush=True)
        try:
            # Load Tiny (Real-time)
            await asyncio.to_thread(self.transcriber.load_model)
            
            # Load Cascade (Medium/Large)
            await asyncio.to_thread(self.transcriber.load_cascade_models)
            
            print("[LIVE] Async model preload finished.", flush=True)
            self._update_model_status()
        except Exception as e:
            print(f"[LIVE] Model preload error: {e}", flush=True)

    def _create_model_info_bar(self):
        """Tworzy pasek informacyjny o modelach."""
        with ui.row().classes('w-full max-w-6xl mx-auto px-4 py-1 items-center gap-4 text-xs text-gray-500'):
            ui.label("Status Modeli:").classes('font-bold')
            self._model_status_container = ui.row().classes('items-center gap-3')
            self._update_model_status() # Initial update

    def _update_model_status(self):
        """Aktualizuje status modeli w UI."""
        if not self._model_status_container:
            return
            
        try:
            loaded = []
            if self.transcriber:
                # Check directly loaded model attributes
                if getattr(self.transcriber, 'model_tiny', None):
                    loaded.append('tiny')
                if getattr(self.transcriber, 'model_medium', None):
                    loaded.append('medium')
                if getattr(self.transcriber, 'model_large', None):
                    loaded.append('large')
            
            self._model_status_container.clear()
            with self._model_status_container:
                # Helper do badge'a
                def model_badge(name, label):
                    is_loaded = name in loaded
                    color = 'green-100' if is_loaded else 'gray-100'
                    text_color = 'green-700' if is_loaded else 'gray-400'
                    icon = 'check_circle' if is_loaded else 'hourglass_empty'
                    
                    with ui.row().classes(f'bg-{color} px-2 py-0.5 rounded-full items-center gap-1'):
                        ui.icon(icon).classes(f'text-{text_color} text-[10px]')
                        ui.label(label).classes(f'text-{text_color} font-medium')

                model_badge('tiny', 'Tiny (Szybki)')
                model_badge('medium', 'Medium (Dokładny)')
                model_badge('large', 'Large (Finalny)')
                
        except Exception:
            pass

    # === SESSION CONTROL ===

    def _toggle_session(self):
        """Przełącza sesję nagrywania."""
        if not self.transcriber:
            ui.notify("Brak modułu transkrypcji", type='negative')
            return

        if self.state.status == SessionStatus.IDLE:
            self._start_session()
        else:
            self._stop_session()

    def _start_session(self):
        """Rozpoczyna sesję."""
        print("[LIVE] Starting session...", flush=True)

        # Reset stanu
        self.state.reset()
        if self.transcript_panel:
            self.transcript_panel.clear()
        self.state.set_status(SessionStatus.RECORDING)
        
        # Ustaw event loop dla AI controller (do thread-safe scheduling)
        self.ai_controller.set_event_loop(asyncio.get_running_loop())

        # Przygotuj backend OpenVINO jeśli wybrany
        external_backend = None
        if self.app.transcriber_manager:
            try:
                from core.transcriber import TranscriberType, OpenVINOWhisperTranscriber
                current_type = self.app.transcriber_manager.get_current_type()
                if current_type == TranscriberType.OPENVINO_WHISPER:
                    backend = self.app.transcriber_manager.get_current_backend()
                    if isinstance(backend, OpenVINOWhisperTranscriber) and backend.is_model_loaded():
                        print("[LIVE] Using OpenVINO for finalization", flush=True)
                        external_backend = backend
            except Exception as e:
                print(f"[LIVE] OpenVINO check error: {e}", flush=True)

        # Start transcriber
        self.transcriber.start(
            callback_provisional=self._on_provisional,
            callback_improved=self._on_improved,
            callback_final=self._on_final,
            external_backend=external_backend
        )

        # Wymuś wygenerowanie początkowych sugestii
        self.ai_controller.force_regeneration()

        ui.notify("Sesja rozpoczęta!", type='positive')

    def _stop_session(self):
        """Zatrzymuje sesję."""
        print("[LIVE] Stopping session...", flush=True)

        # 1. Natychmiast zmień status (UI responsywne)
        self.state.set_status(SessionStatus.IDLE)
        
        # 2. Zatrzymaj regenerację (ale NIE walidację)
        self.ai_controller.stop()

        # 3. Finalizuj i zatrzymaj streaming w tle (nie blokuj UI)
        import threading
        def _finalize_async():
            if self.transcriber:
                self.transcriber.force_finalize()
                self.transcriber.stop()
        
        threading.Thread(target=_finalize_async, daemon=True).start()

        ui.notify("Sesja zatrzymana", type='info')

    def _finish_interview(self):
        """Kończy wywiad i przekazuje transkrypt."""
        print("[LIVE] Finishing interview...", flush=True)

        # Zatrzymaj jeśli aktywne
        if self.state.status == SessionStatus.RECORDING:
            if self.transcriber:
                self.transcriber.force_finalize()
                self.transcriber.stop()
            self.ai_controller.stop()

        # Zbierz pełny transkrypt
        final_transcript = self.state.full_transcript

        if not final_transcript:
            ui.notify("Brak transkryptu do zapisania", type='warning')
            return

        # Uruchom diaryzację w tle
        asyncio.create_task(self._finish_with_diarization(final_transcript))

    async def _finish_with_diarization(self, final_transcript: str):
        """Kończy wywiad z diaryzacją (async)."""
        # Diaryzacja (jeśli dostępna i mamy audio)
        if self.diarization_service and self.transcriber:
            try:
                ui.notify("Analizuję mówców...", type='info')
                self.state.set_diarization_processing(True)

                audio = self.transcriber.get_full_audio()
                if len(audio) >= 16000:  # Min 1 sekunda
                    print(f"[LIVE] Running diarization on {len(audio)} samples...", flush=True)

                    # Uruchom diaryzację w wątku (nie blokuj UI)
                    result = await self.diarization_service.diarize_with_transcript(
                        audio=audio,
                        transcript=final_transcript,
                        sample_rate=16000
                    )

                    self.state.set_diarization_result(result)
                    print(f"[LIVE] Diarization done: {result.num_speakers} speakers, {len(result.segments)} segments", flush=True)

                    # Zapisz transkrypt z mówcami do storage
                    if result.segments:
                        diarized_transcript = self.state.diarization.get_formatted_transcript()
                        app.storage.user['live_transcript_diarized'] = diarized_transcript
                else:
                    print(f"[LIVE] Audio too short for diarization: {len(audio)} samples", flush=True)

            except Exception as e:
                print(f"[LIVE] Diarization error: {e}", flush=True)
                import traceback
                traceback.print_exc()
            finally:
                self.state.set_diarization_processing(False)

        # Zapisz zwykły transkrypt do storage
        app.storage.user['live_transcript'] = final_transcript
        print(f"[LIVE] Saved {len(final_transcript)} chars to storage", flush=True)

        ui.notify("Wywiad zakończony! Przekierowuję...", type='positive')

        # Przekieruj do głównej strony
        ui.navigate.to('/')

    # === TRANSCRIBER CALLBACKS ===

    def _on_provisional(self, text: str, start_sample: int, end_sample: int):
        """Callback: tekst provisional (real-time)."""
        # Ignoruj jeśli sesja zatrzymana
        if self.state.status != SessionStatus.RECORDING:
            return
        text = text.strip()
        if not text:
            return

        print(f"[LIVE] Provisional: {text[:50]}...", flush=True)
        self.state.set_provisional(text)

    def _on_improved(self, text: str, start_sample: int, end_sample: int):
        """Callback: tekst improved (kontekstowy)."""
        # Ignoruj jeśli sesja zatrzymana
        if self.state.status != SessionStatus.RECORDING:
            return
        text = text.strip()
        if not text:
            return

        print(f"[LIVE] Improved: {text[:50]}...", flush=True)

        # Zapisz poprzedni tekst dla diff PRZED zmianą stanu
        prev_text = self.state.provisional_text

        # Zmień stan
        self.state.set_improved(text)

        # Trigger animację shimmer PO zmianie stanu (jeśli tekst się zmienił)
        if self.transcript_panel and prev_text and prev_text != text:
            self.transcript_panel.trigger_regeneration_animation("improved", prev_text)

    def _on_final(self, text: str, start_sample: int, end_sample: int):
        """Callback: tekst final (po ciszy lub STOP)."""
        # Final ZAWSZE akceptujemy - to finalizacja (nawet po STOP)
        text = text.strip()
        if not text:
            return

        print(f"[LIVE] Final: {text[:50]}...", flush=True)

        # Zapisz poprzedni tekst dla diff PRZED zmianą stanu
        prev_provisional = self.state.provisional_text

        # Zmień stan
        self.state.set_final(text)

        # Trigger animację shimmer dla final
        # Dla final porównujemy z provisional (który właśnie został sfinalizowany)
        if self.transcript_panel and prev_provisional:
            self.transcript_panel.trigger_regeneration_animation("final", prev_provisional)

        # Trigger walidację AI (zawsze - również po STOP)
        self.ai_controller.on_final_text()

    # === CARD INTERACTION ===

    def _on_card_click(self, question: str):
        """Callback: kliknięcie w kartę sugestii."""
        print(f"[LIVE] Card clicked: {question[:30]}...", flush=True)

        # Kopiuj do schowka
        import json
        ui.run_javascript(f'navigator.clipboard.writeText({json.dumps(question)})')
        ui.notify("Skopiowano pytanie!", type='positive', position='top')

        # Trigger AI (regeneruj pozostałe)
        self.ai_controller.on_card_clicked(question)

    # === AI CALLBACKS ===

    def _on_ai_start(self):
        """Callback: AI zaczyna generować."""
        if self.prompter_panel:
            self.prompter_panel.set_loading(True)

    def _on_ai_end(self):
        """Callback: AI skończyło generować."""
        if self.prompter_panel:
            self.prompter_panel.set_loading(False)
