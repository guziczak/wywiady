"""
Live Interview View - Refactored
Główny widok Live Interview z komponentami i smart AI triggers.
"""

from nicegui import ui, app
import asyncio
from typing import Optional, List

from app_ui.components.header import create_header
from app_ui.live.live_state import LiveState, SessionStatus
from app_ui.live.live_ai_controller import AIController
from app_ui.live.components.transcript_panel import TranscriptPanel
from app_ui.live.components.prompter_panel import PrompterPanel
from app_ui.live.components.pipeline_panel import PipelinePanel
from app_ui.live.components.qa_collection_panel import QACollectionPanel
from app_ui.live.components.active_question_panel import ActiveQuestionPanel

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

# Specialization Manager (opcjonalny)
try:
    from core.specialization_manager import get_specialization_manager
except ImportError:
    get_specialization_manager = None


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
        self.transcriber_error = None
        if StreamingTranscriber:
            try:
                # 1. Pobierz konfigurację
                config_backend = self.app.config.get("transcriber_backend", "")
                selected_device = self.app.config.get("selected_device", "auto")
                
                # 2. Inteligentna detekcja OpenVINO
                # Domyślnie z configu
                use_openvino = (config_backend == "openvino_whisper")
                
                # Jeśli wybrano NPU -> ZAWSZE wymuś OpenVINO (faster-whisper nie wspiera NPU)
                if selected_device == "NPU":
                    use_openvino = True
                    print("[LIVE] Force OpenVINO for NPU", flush=True)
                
                # Jeśli wybrano GPU (Intel) -> ZAWSZE wymuś OpenVINO (faster-whisper nie wspiera Intel GPU)
                # Zakładamy, że user z Intel Arc/iGPU chce OpenVINO. 
                # Jeśli ma NVIDIA, powinien używać 'cuda' w faster-whisper, ale tu UI daje ogólne 'GPU'.
                # Dla bezpieczeństwa: Jeśli GPU i nie OpenVINO -> fallback do CPU (chyba że wykryjemy CUDA, ale to trudne tu)
                if selected_device == "GPU" and not use_openvino:
                    # Sprawdźmy czy to może być Intel GPU (w przyszłości można dodać detekcję vendora)
                    # Na razie: Live View na Windows z Intel NPU/GPU -> preferuj OpenVINO
                    # Ale jeśli user uparł się na faster-whisper... to on nie zadziała na Intel GPU.
                    # Więc bezpieczny fallback:
                    print("[LIVE] GPU selected with faster-whisper. Forcing CPU fallback (faster-whisper requires CUDA)", flush=True)
                    selected_device = "cpu"

                # 3. Sprawdź manager (jeśli config zawiódł)
                if not use_openvino and self.app.transcriber_manager:
                    from core.transcriber import TranscriberType
                    if self.app.transcriber_manager.get_current_type() == TranscriberType.OPENVINO_WHISPER:
                        use_openvino = True

                # 4. Pipeline config (live)
                enable_medium = bool(self.app.config.get("live_enable_medium", True))
                enable_large = bool(self.app.config.get("live_enable_large", True))
                try:
                    improved_interval = float(self.app.config.get("live_improved_interval", 5.0))
                except Exception:
                    improved_interval = 5.0
                try:
                    silence_threshold = float(self.app.config.get("live_silence_threshold", 2.0))
                except Exception:
                    silence_threshold = 2.0

                print(f"[LIVE] Initializing StreamingTranscriber with device={selected_device} (OpenVINO={use_openvino})", flush=True)
                
                self.transcriber = StreamingTranscriber(
                    model_size="tiny", 
                    use_openvino=use_openvino,
                    device=selected_device,
                    enable_medium=enable_medium,
                    enable_large=enable_large,
                    improved_interval=improved_interval,
                    silence_threshold=silence_threshold
                )
                
                # Asynchroniczne ładowanie modeli (non-blocking UI)
                # Przeniesione do _start_background_loading wywoływanego przez timer
                
            except Exception as e:
                self.transcriber_error = str(e)
                print(f"[LIVE] Could not init transcriber: {e}", flush=True)

        # UI Components
        self.transcript_panel: Optional[TranscriptPanel] = None
        self.prompter_panel: Optional[PrompterPanel] = None
        self.qa_panel: Optional[QACollectionPanel] = None
        self.active_question_panel: Optional[ActiveQuestionPanel] = None

        # Diarization service
        self.diarization_service: Optional[DiarizationService] = None
        if DIARIZATION_AVAILABLE:
            self.diarization_service = get_diarization_service()
            print(f"[LIVE] Diarization available: {self.diarization_service.backend.name if self.diarization_service.backend else 'None'}", flush=True)

        # Model status refs
        self._model_status_container = None
        self.pipeline_panel: Optional[PipelinePanel] = None
        self._pipeline_loading: bool = False
        self._client = None

    def create_ui(self):
        """Buduje interfejs użytkownika."""

        # Timer do aktualizacji statusu w headerze
        ui.timer(1.0, self.app._update_status_ui)
        # Timer do aktualizacji statusu modeli
        ui.timer(2.0, self._update_model_status)
        
        # Timer do rozpoczęcia ładowania modeli (po załadowaniu UI)
        ui.timer(1.0, self._start_background_loading, once=True)

        # Header (z głównej aplikacji)
        create_header(self.app, show_spec_switcher=True, show_status=False)
        
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

            # === ŚRODEK: AKTYWNE PYTANIE (ODDZIELONY OD SUGESTII!) ===
            with ui.element('div').classes('w-full shrink-0'):
                self.active_question_panel = ActiveQuestionPanel(
                    context=self.state.active_question,
                    on_answer_click=self._on_answer_copied,
                    on_manual_answer=self._on_manual_answer_selected,
                    on_close=self._on_active_question_closed
                )
                self.active_question_panel.create()

            # === ŚRODEK: KOLEKCJA Q+A (GAMIFIKACJA) ===
            with ui.element('div').classes('w-full shrink-0'):
                self.qa_panel = QACollectionPanel(self.state)
                self.qa_panel.create()

            # === DÓŁ: SUFLER ===
            with ui.element('div').classes('w-full shrink-0'):
                self.prompter_panel = PrompterPanel(
                    state=self.state,
                    app_instance=self.app,
                    on_toggle_session=self._toggle_session,
                    on_finish=self._finish_interview,
                    on_continue=self._navigate_next,
                    on_card_click=self._on_card_click
                )
                self.prompter_panel.create()

        # AI Controller callbacks
        self.ai_controller.on_regen_start(self._on_ai_start)
        self.ai_controller.on_regen_end(self._on_ai_end)
        
        # Cleanup on disconnect
        ui.context.client.on_disconnect(self._on_disconnect)

        # Capture client context for background updates
        self._client = ui.context.client

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
        self._pipeline_loading = True
        self._update_model_status()
        try:
            # Load Tiny (Real-time)
            await asyncio.to_thread(self.transcriber.load_model)
            
            # Load Cascade (Medium/Large) jeśli włączone
            if getattr(self.transcriber, 'enable_medium', True) or getattr(self.transcriber, 'enable_large', True):
                await asyncio.to_thread(self.transcriber.load_cascade_models)
            
            print("[LIVE] Async model preload finished.", flush=True)
            self._update_model_status()
        except Exception as e:
            print(f"[LIVE] Model preload error: {e}", flush=True)
        finally:
            self._pipeline_loading = False
            self._update_model_status()

    def _create_model_info_bar(self):
        """Tworzy pasek informacyjny o pipeline modeli."""
        self.pipeline_panel = PipelinePanel(
            get_config=self._get_pipeline_config,
            on_apply=self._apply_pipeline_config
        )
        self.pipeline_panel.create()
        self._update_model_status()  # Initial update

    def _update_model_status(self):
        """Aktualizuje status pipeline modeli w UI."""
        if not self.pipeline_panel:
            return

        cfg = self._get_pipeline_config()
        backend = "OpenVINO" if (self.transcriber and getattr(self.transcriber, 'use_openvino', False)) else "faster-whisper"
        device = getattr(self.transcriber, 'device', 'auto') if self.transcriber else 'auto'

        def stage_state(enabled: bool, model_obj, error_msg: str | None, ready_detail: str):
            if self.transcriber_error:
                return "error", self.transcriber_error
            if not enabled:
                detail = "Wyłączony"
                if model_obj:
                    detail = "Wyłączony (model w pamięci)"
                return "disabled", detail
            if error_msg:
                return "error", "Błąd ładowania"
            if model_obj:
                return "ready", ready_detail
            if self._pipeline_loading:
                return "loading", "Ładowanie w tle..."
            return "idle", "Oczekuje"

        tiny_state, tiny_detail = stage_state(
            True,
            getattr(self.transcriber, 'model_tiny', None) if self.transcriber else None,
            getattr(self.transcriber, 'model_tiny_error', None) if self.transcriber else None,
            f"{backend} • {device}"
        )
        medium_state, medium_detail = stage_state(
            cfg["enable_medium"],
            getattr(self.transcriber, 'model_medium', None) if self.transcriber else None,
            getattr(self.transcriber, 'model_medium_error', None) if self.transcriber else None,
            f"{backend} • {device}"
        )
        large_state, large_detail = stage_state(
            cfg["enable_large"],
            getattr(self.transcriber, 'model_large', None) if self.transcriber else None,
            getattr(self.transcriber, 'model_large_error', None) if self.transcriber else None,
            f"{backend} • {device}"
        )

        summary = f"Backend: {backend} • Urządzenie: {device} • Cisza: {cfg['silence_threshold']:.1f}s • Improved: co {cfg['improved_interval']:.0f}s"

        self.pipeline_panel.update({
            "summary": summary,
            "stages": {
                "tiny": {"state": tiny_state, "detail": tiny_detail},
                "medium": {"state": medium_state, "detail": medium_detail},
                "large": {"state": large_state, "detail": large_detail},
            },
            "config": cfg,
        })

    def _get_pipeline_config(self) -> dict:
        """Zwraca aktualne ustawienia pipeline z configu."""
        cfg = self.app.config
        try:
            improved_interval = float(cfg.get("live_improved_interval", 5.0))
        except Exception:
            improved_interval = 5.0
        try:
            silence_threshold = float(cfg.get("live_silence_threshold", 2.0))
        except Exception:
            silence_threshold = 2.0

        return {
            "enable_medium": bool(cfg.get("live_enable_medium", True)),
            "enable_large": bool(cfg.get("live_enable_large", True)),
            "improved_interval": improved_interval,
            "silence_threshold": silence_threshold,
        }

    async def _load_cascade_async(self):
        """Ładuje modele medium/large w tle po zmianie ustawień."""
        if not self.transcriber or self._pipeline_loading:
            return
        self._pipeline_loading = True
        self._update_model_status()
        try:
            # Upewnij się, że tiny jest załadowany
            if not getattr(self.transcriber, 'model_tiny', None):
                await asyncio.to_thread(self.transcriber.load_model)
            await asyncio.to_thread(self.transcriber.load_cascade_models)
        except Exception as e:
            print(f"[LIVE] Cascade load error: {e}", flush=True)
        finally:
            self._pipeline_loading = False
            self._update_model_status()

    def _apply_pipeline_config(self, cfg: dict):
        """Zapisuje i aplikuje ustawienia pipeline."""
        updates = {
            "live_enable_medium": bool(cfg.get("enable_medium", True)),
            "live_enable_large": bool(cfg.get("enable_large", True)),
            "live_improved_interval": float(cfg.get("improved_interval", 5.0)),
            "live_silence_threshold": float(cfg.get("silence_threshold", 2.0)),
        }

        if hasattr(self.app, 'config_manager') and self.app.config_manager:
            self.app.config_manager.update(**updates)
        else:
            for key, value in updates.items():
                try:
                    self.app.config[key] = value
                except Exception:
                    pass

        if self.transcriber:
            self.transcriber.update_pipeline_config(
                enable_medium=updates["live_enable_medium"],
                enable_large=updates["live_enable_large"],
                improved_interval=updates["live_improved_interval"],
                silence_threshold=updates["live_silence_threshold"]
            )

            # Jeśli włączono etap(y) i model nie jest w pamięci, doładuj
            needs_cascade = (
                updates["live_enable_medium"] and not getattr(self.transcriber, 'model_medium', None)
            ) or (
                updates["live_enable_large"] and not getattr(self.transcriber, 'model_large', None)
            )
            if needs_cascade:
                asyncio.create_task(self._load_cascade_async())

        self._update_model_status()

    # === SESSION CONTROL ===

    def _toggle_session(self):
        """Przełącza sesję nagrywania."""
        if not self.transcriber:
            ui.notify(self.transcriber_error or "Brak modułu transkrypcji", type='negative')
            return

        if self.state.status == SessionStatus.IDLE:
            self._start_session()
        else:
            self._stop_session()

    def _start_session(self):
        """Rozpoczyna sesję."""
        print("[LIVE] Starting session...", flush=True)

        # Ustaw specjalizacje w AI Controller (multi-select)
        if get_specialization_manager:
            spec_manager = get_specialization_manager()
            spec_ids = spec_manager.get_active_ids()
            if self.ai_controller:
                self.ai_controller.set_spec_ids(spec_ids)
                spec_names = [spec_manager.get_by_id(sid).name for sid in spec_ids]
                print(f"[LIVE] Using specializations: {', '.join(spec_names)} (IDs={spec_ids})", flush=True)

        # Reset stanu
        self.state.reset()
        if self.transcript_panel:
            self.transcript_panel.clear()
        self.state.set_status(SessionStatus.RECORDING)
        
        # Ustaw event loop dla AI controller (do thread-safe scheduling)
        self.ai_controller.set_event_loop(asyncio.get_running_loop())

        # Start transcriber (używa wewnętrznych modeli cascade: tiny → medium → large)
        self.transcriber.start(
            callback_provisional=self._on_provisional,
            callback_improved=self._on_improved,
            callback_final=self._on_final
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

    def _finish_interview(self, analyze_speakers: bool = True):
        """Kończy wywiad i przekazuje transkrypt."""
        print(f"[LIVE] Finishing interview (analyze={analyze_speakers})...", flush=True)

        # Zatrzymaj jeśli aktywne
        if self.state.status == SessionStatus.RECORDING:
            if self.transcriber:
                self.transcriber.force_finalize()
                self.transcriber.stop()
            self.ai_controller.stop()
            self.state.set_status(SessionStatus.PAUSED)

        # Zbierz pełny transkrypt
        final_transcript = self.state.full_transcript

        if self._client:
            with self._client:
                if not final_transcript:
                    ui.notify("Brak transkryptu do zapisania", type='warning')
                # Zapisz do storage (wersja surowa)
                app.storage.user['live_transcript'] = final_transcript

        # Uruchom diaryzację w tle (jeśli wybrano)
        if analyze_speakers:
            asyncio.create_task(self._run_diarization(final_transcript))

    async def _run_diarization(self, final_transcript: str):
        """Uruchamia diaryzację (async)."""
        # Diaryzacja (jeśli dostępna i mamy audio)
        if self.diarization_service and self.transcriber:
            try:
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

                    # Zapisz transkrypt z mówcami do storage (opcjonalnie, jako backup)
                    if result.segments:
                        diarized_transcript = self.state.diarization.get_formatted_transcript()
                        if self._client:
                            with self._client:
                                app.storage.user['live_transcript_diarized'] = diarized_transcript
                else:
                    print(f"[LIVE] Audio too short for diarization: {len(audio)} samples", flush=True)

            except Exception as e:
                print(f"[LIVE] Diarization error: {e}", flush=True)
                import traceback
                traceback.print_exc()
            finally:
                self.state.set_diarization_processing(False)

    def _navigate_next(self):
        """Przechodzi do ekranu generowania opisu."""
        # Przygotuj finalny transkrypt (z mówcami jeśli są)
        transcript = self.state.full_transcript

        if self.state.diarization and self.state.diarization.has_data and self.state.diarization.enabled:
            transcript = self.state.diarization.get_formatted_transcript()

        # Dodaj zebrane pary Q+A do transkryptu
        qa_pairs = self.state.qa_collector.pairs
        if qa_pairs:
            qa_section = self._format_qa_pairs_for_transcript(qa_pairs)
            transcript = transcript + "\n\n" + qa_section
            print(f"[LIVE] Added {len(qa_pairs)} Q+A pairs to transcript", flush=True)

        if self._client:
            with self._client:
                app.storage.user['live_transcript'] = transcript
                print(f"[LIVE] Navigating next with {len(transcript)} chars", flush=True)
                ui.navigate.to('/')

    def _format_qa_pairs_for_transcript(self, pairs) -> str:
        """Formatuje pary Q+A jako sekcję do transkryptu."""
        if not pairs:
            return ""

        lines = ["", "=== ZEBRANE PYTANIA I ODPOWIEDZI ===", ""]
        for i, pair in enumerate(pairs, 1):
            lines.append(f"[{i}] Pytanie: {pair.question}")
            lines.append(f"    Odpowiedź: {pair.answer}")
            lines.append("")

        return "\n".join(lines)

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
        """
        Callback: kliknięcie w kartę sugestii.

        NOWA ARCHITEKTURA:
        1. Aktywuje pytanie w ActiveQuestionContext (ODDZIELONY od sugestii)
        2. Ładuje odpowiedzi asynchronicznie
        3. Kopiuje pytanie do schowka
        4. Triggeruje regenerację sugestii Z OPÓŹNIENIEM (8s)
        """
        print(f"[LIVE] Card clicked: {question[:30]}...", flush=True)

        # === 1. AKTYWUJ PYTANIE W NOWYM KONTEKŚCIE ===
        # To NIE znika przy regeneracji sugestii!
        self.state.start_question(question, [])

        # === 2. ZAŁADUJ ODPOWIEDZI ===
        asyncio.create_task(self._load_patient_answers(question))

        # === 3. KOPIUJ DO SCHOWKA ===
        import json
        client = ui.context.client or self._client
        if client:
            try:
                client.run_javascript(f'navigator.clipboard.writeText({json.dumps(question)})')
            except Exception:
                pass
            try:
                with client:
                    ui.notify("Skopiowano pytanie!", type='positive', position='top')
            except Exception:
                pass

        # === 4. TRIGGER AI Z OPÓŹNIENIEM ===
        # Regeneracja sugestii po 8s - daje czas na przeczytanie odpowiedzi
        if self.ai_controller:
            self.ai_controller.on_card_clicked(question)

    async def _load_patient_answers(self, question: str) -> None:
        """
        Generuje podpowiedzi odpowiedzi pacjenta przez AI.

        NOWA ARCHITEKTURA: Ustawia odpowiedzi w ActiveQuestionContext.
        """
        if not question:
            return

        # Sprawdź czy to wciąż aktywne pytanie
        if self.state.active_question.question != question:
            print(f"[LIVE] Skipping answers - question changed", flush=True)
            return

        answers: List[str] = []
        try:
            if self.app.llm_service:
                spec_id = self.ai_controller.current_spec_id if self.ai_controller else None
                answers = await self.app.llm_service.generate_patient_answers(
                    question,
                    self.app.config,
                    spec_id=spec_id
                )
        except Exception as e:
            print(f"[LIVE] Patient answers error: {e}", flush=True)

        # Ponownie sprawdź czy pytanie się nie zmieniło podczas generowania
        if self.state.active_question.question != question:
            print(f"[LIVE] Skipping answers - question changed during generation", flush=True)
            return

        # Ustaw odpowiedzi w nowym kontekście
        self.state.active_question.set_answers(answers)

        # Deprecated: zachowaj dla kompatybilności wstecznej
        self.state.set_answer_context(question, answers)

        # Odśwież panele
        if self.active_question_panel:
            self.active_question_panel.refresh()
        if self.prompter_panel:
            self.prompter_panel.refresh()

    def _on_answer_copied(self, answer: str):
        """Callback: skopiowano odpowiedź z panelu aktywnego pytania."""
        print(f"[LIVE] Answer copied: {answer[:30]}...", flush=True)
        # Opcjonalnie: można tu dodać logikę

    def _on_manual_answer_selected(self, question: str, answer: str):
        """
        Callback: ręcznie wybrano odpowiedź (kliknięcie karty).
        Para Q+A jest już dodana przez LiveState._on_question_matched (via match()).
        Tu tylko odświeżamy UI i czyścimy aktywne pytanie.
        """
        print(f"[LIVE] Manual answer selected: Q='{question[:30]}...' A='{answer[:30]}...'", flush=True)

        # Para już została dodana przez callback _on_question_matched w LiveState
        # (wywoływany automatycznie przez match())

        # Odśwież panel Q+A (na wypadek gdyby callback nie zadziałał)
        if self.qa_panel:
            self.qa_panel.refresh()

        # Wyczyść aktywne pytanie po chwili (pozwól zobaczyć animację)
        async def _clear_after_delay():
            await asyncio.sleep(1.5)
            if self._client:
                try:
                    with self._client:
                        self.state.active_question.clear(force=True)
                        if self.active_question_panel:
                            self.active_question_panel.refresh()
                except Exception:
                    pass

        asyncio.create_task(_clear_after_delay())

    def _on_active_question_closed(self):
        """Callback: zamknięto panel aktywnego pytania."""
        print(f"[LIVE] Active question closed by user", flush=True)
        # Wyczyść deprecated pola
        self.state.clear_answer_context()
        if self.prompter_panel:
            self.prompter_panel.refresh()

    def _extract_keywords(self, answers: List[str]) -> List[str]:
        """Wyciąga słowa kluczowe z przykładowych odpowiedzi AI."""
        if not answers:
            return []

        # Proste wyciąganie słów kluczowych (>4 znaki, bez powtórek)
        keywords = set()
        stopwords = {'jest', 'są', 'był', 'była', 'było', 'będzie', 'tak', 'nie', 'może', 'bardzo', 'trochę', 'dużo'}

        for answer in answers:
            words = answer.lower().split()
            for word in words:
                # Usuń interpunkcję
                word = word.strip('.,!?;:()[]"\'')
                if len(word) > 4 and word not in stopwords:
                    keywords.add(word)

        return list(keywords)[:10]  # Max 10 keywords


    # === AI CALLBACKS ===

    def _on_ai_start(self):
        """Callback: AI zaczyna generować."""
        if self.prompter_panel:
            self.prompter_panel.set_loading(True)

    def _on_ai_end(self):
        """Callback: AI skończyło generować."""
        if self.prompter_panel:
            self.prompter_panel.set_loading(False)
