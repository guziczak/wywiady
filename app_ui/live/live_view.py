"""
Live Interview View - Refactored
Główny widok Live Interview z komponentami i smart AI triggers.
"""

from nicegui import ui, app
import asyncio
from typing import Optional, List

from app_ui.components.header import create_header
from app_ui.live.live_state import LiveState, SessionStatus, Suggestion
from app_ui.live.live_ai_controller import AIController
from app_ui.live.components.transcript_panel import TranscriptPanel
from app_ui.live.components.prompter_panel import PrompterPanel
from app_ui.live.components.pipeline_panel import PipelinePanel
from app_ui.live.components.qa_collection_panel import QACollectionPanel
from app_ui.live.components.active_question_panel import ActiveQuestionPanel
from app_ui.live.components.desk_styles import inject_desk_styles
from app_ui.live.components.feedback import inject_feedback_script
from app_ui.live.ui_labels import (
    STATUS_READY,
    STATUS_RECORDING,
    DOCK_TRANSCRIPT,
    DOCK_PROMPTER,
    DOCK_PIPELINE,
    DOCK_FOCUS,
    OVERLAY_PIPELINE_TITLE,
)

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
        # Trigger AI routing when a Q+A pair is created (manual answers too)
        self.state.on_qa_pair_created(self._on_qa_pair_created)

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

        # Desk-first layout refs
        self._desk_shell = None
        self._active_overlay = None
        self._transcript_overlay = None
        self._prompter_overlay = None
        self._pipeline_overlay = None
        self._dock = None
        self._record_btn = None
        self._status_badge = None
        self._progress_badge = None
        self._toggle_transcript_btn = None
        self._toggle_prompter_btn = None
        self._toggle_pipeline_btn = None
        self._transcript_size_btn = None
        self._prompter_size_btn = None
        self._toggle_fx_btn = None
        self._focus_btn = None
        self._transcript_visible = False
        self._prompter_visible = True
        self._pipeline_visible = False
        self._fx_enabled = True
        self._focus_mode = False
        self._focus_restore = {}
        self._transcript_size = 'peek'
        self._prompter_size = 'full'

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
        self._timers = []

    def create_ui(self):
        """Buduje interfejs użytkownika."""

        # Timer do aktualizacji statusu w headerze
        self._timers.append(ui.timer(1.0, self.app._update_status_ui))
        # Timer do aktualizacji statusu modeli
        self._timers.append(ui.timer(2.0, self._update_model_status))
        
        # Timer do rozpoczęcia ładowania modeli (po załadowaniu UI)
        self._timers.append(ui.timer(1.0, self._start_background_loading, once=True))

        # Header (z głównej aplikacji)
        create_header(self.app, show_spec_switcher=True, show_status=False)
        
        # Desk-first immersive layout
        inject_desk_styles()
        inject_feedback_script()
        with ui.element('div').classes('live-mode live-desk-shell') as self._desk_shell:
            # === DESK (MAIN STAGE) ===
            self.qa_panel = QACollectionPanel(self.state, immersive=True)
            self.qa_panel.create()
            if self.qa_panel.container:
                self.qa_panel.container.classes(add='h-full')

            # === ACTIVE QUESTION (SPOTLIGHT) ===
            self._active_overlay = ui.element('div').classes('live-overlay live-overlay--spotlight is-open')
            with self._active_overlay:
                self.active_question_panel = ActiveQuestionPanel(
                    context=self.state.active_question,
                    on_answer_click=self._on_answer_copied,
                    on_manual_answer=self._on_manual_answer_selected,
                    on_close=self._on_active_question_closed,
                    card_classes='live-active-card'
                )
                self.active_question_panel.create()

            # === TRANSCRIPT (TAPE) ===
            self._transcript_overlay = ui.element('div').classes('live-overlay live-overlay--transcript flex flex-col gap-2 min-h-0')
            with self._transcript_overlay:
                with ui.element('div').classes('overlay-header'):
                    ui.label('Transkrypt').classes('overlay-title')
                    with ui.row().classes('items-center gap-1'):
                        self._transcript_size_btn = ui.button(icon='open_in_full', on_click=self._toggle_transcript_size).props('flat dense').classes('overlay-btn')
                        ui.button(icon='close', on_click=lambda: self._set_transcript_visible(False)).props('flat dense').classes('overlay-btn')
                self.transcript_panel = TranscriptPanel(self.state)
                self.transcript_panel.create()
                if self.transcript_panel.container:
                    self.transcript_panel.container.classes(add='live-panel live-transcript-panel flex-1 min-h-0')

            # === PROMPTER (DRAWER) ===
            self._prompter_overlay = ui.element('div').classes('live-overlay live-overlay--drawer flex flex-col gap-2 min-h-0')
            with self._prompter_overlay:
                with ui.element('div').classes('overlay-header'):
                    ui.label('Sufler').classes('overlay-title')
                    with ui.row().classes('items-center gap-1'):
                        self._prompter_size_btn = ui.button(icon='close_fullscreen', on_click=self._toggle_prompter_size).props('flat dense').classes('overlay-btn')
                        ui.button(icon='close', on_click=lambda: self._set_prompter_visible(False)).props('flat dense').classes('overlay-btn')
                self.prompter_panel = PrompterPanel(
                    state=self.state,
                    app_instance=self.app,
                    on_toggle_session=self._toggle_session,
                    on_finish=self._finish_interview,
                    on_continue=self._navigate_next,
                    on_card_click=self._on_card_click,
                    show_record_button=False
                )
                self.prompter_panel.create()
                if self.prompter_panel.container:
                    self.prompter_panel.container.classes(add='live-panel live-prompter-panel flex-1 min-h-0')

            # === PIPELINE (FLOATING CHIP) ===
            self._pipeline_overlay = ui.element('div').classes('live-overlay live-overlay--pipeline')
            with self._pipeline_overlay:
                with ui.element('div').classes('overlay-header'):
                    ui.label(OVERLAY_PIPELINE_TITLE).classes('overlay-title')
                    with ui.row().classes('items-center gap-1'):
                        ui.button(icon='close', on_click=lambda: self._set_pipeline_visible(False)).props('flat dense').classes('overlay-btn')
                self._create_model_info_bar()
                if self.pipeline_panel and self.pipeline_panel.container:
                    self.pipeline_panel.container.classes(add='live-panel live-pipeline-panel')

            # === DOCK ===
            with ui.element('div').classes('live-desk-dock') as self._dock:
                self._record_btn = ui.button(
                    'START',
                    icon='mic',
                    on_click=self._toggle_session
                ).props('unelevated').classes('live-desk-btn live-desk-btn--primary')
                self._status_badge = ui.badge(STATUS_READY).classes('live-desk-chip')
                self._progress_badge = ui.badge('0/10').classes('live-desk-chip')
                self._toggle_transcript_btn = ui.button(
                    DOCK_TRANSCRIPT,
                    icon='subject',
                    on_click=self._toggle_transcript
                ).props('flat').classes('live-desk-btn')
                self._toggle_prompter_btn = ui.button(
                    DOCK_PROMPTER,
                    icon='auto_awesome',
                    on_click=self._toggle_prompter
                ).props('flat').classes('live-desk-btn')
                self._toggle_pipeline_btn = ui.button(
                    DOCK_PIPELINE,
                    icon='tune',
                    on_click=self._toggle_pipeline
                ).props('flat').classes('live-desk-btn')
                self._focus_btn = ui.button(
                    DOCK_FOCUS,
                    icon='center_focus_strong',
                    on_click=self._toggle_focus_mode
                ).props('flat').classes('live-desk-btn')
                self._toggle_fx_btn = ui.button(
                    'FX',
                    icon='volume_up',
                    on_click=self._toggle_fx
                ).props('flat').classes('live-desk-btn')

            # Initial overlay states
            self._set_overlay_open(self._transcript_overlay, self._transcript_visible)
            self._set_overlay_open(self._prompter_overlay, self._prompter_visible)
            self._set_overlay_open(self._pipeline_overlay, self._pipeline_visible)
            self._set_overlay_size(self._transcript_overlay, self._transcript_size)
            self._set_overlay_size(self._prompter_overlay, self._prompter_size)
            self._sync_toggle_button(self._toggle_transcript_btn, self._transcript_visible)
            self._sync_toggle_button(self._toggle_prompter_btn, self._prompter_visible)
            self._sync_toggle_button(self._toggle_pipeline_btn, self._pipeline_visible)
            self._sync_toggle_button(self._toggle_fx_btn, self._fx_enabled)
            self._sync_fx_button()
            self._sync_size_button(self._transcript_size_btn, self._transcript_size)
            self._sync_size_button(self._prompter_size_btn, self._prompter_size)

        # Dock status refresh
        self._timers.append(ui.timer(0.6, self._update_desk_ui))

        # AI Controller callbacks
        self.ai_controller.on_regen_start(self._on_ai_start)
        self.ai_controller.on_regen_end(self._on_ai_end)
        
        # Cleanup on disconnect
        ui.context.client.on_disconnect(self._on_disconnect)

        # Capture client context for background updates
        self._client = ui.context.client

    def _set_overlay_size(self, overlay, size: str) -> None:
        if not overlay:
            return
        overlay.classes(remove='is-peek is-full')
        if size == 'full':
            overlay.classes(add='is-full')
        else:
            overlay.classes(add='is-peek')

    def _sync_size_button(self, button, size: str) -> None:
        if not button:
            return
        icon = 'open_in_full' if size != 'full' else 'close_fullscreen'
        try:
            button.props(f'icon={icon}')
        except Exception:
            pass

    def _schedule_mobile_overlay_policy(self, opened: str) -> None:
        """Na małych ekranach utrzymuje tylko jeden overlay naraz."""
        if opened not in ('transcript', 'prompter', 'pipeline'):
            return
        if not (self._client or ui.context.client):
            return
        asyncio.create_task(self._enforce_mobile_overlay_policy(opened))

    async def _enforce_mobile_overlay_policy(self, opened: str) -> None:
        client = ui.context.client or self._client
        if not client:
            return
        try:
            with client:
                width = await ui.run_javascript("window.innerWidth")
        except Exception:
            return
        try:
            width_val = float(width)
        except Exception:
            return
        if width_val >= 900:
            return

        # Na mobile: po otwarciu jednego overlayu zamknij pozostałe
        if opened != 'transcript' and self._transcript_visible:
            self._set_transcript_visible(False)
        if opened != 'prompter' and self._prompter_visible:
            self._set_prompter_visible(False)
        if opened != 'pipeline' and self._pipeline_visible:
            self._set_pipeline_visible(False)

    def _set_transcript_visible(self, visible: bool) -> None:
        self._transcript_visible = visible
        self._set_overlay_open(self._transcript_overlay, visible)
        self._sync_toggle_button(self._toggle_transcript_btn, visible)
        if visible:
            self._schedule_mobile_overlay_policy('transcript')

    def _set_prompter_visible(self, visible: bool) -> None:
        self._prompter_visible = visible
        self._set_overlay_open(self._prompter_overlay, visible)
        self._sync_toggle_button(self._toggle_prompter_btn, visible)
        if visible:
            self._schedule_mobile_overlay_policy('prompter')

    def _set_pipeline_visible(self, visible: bool) -> None:
        self._pipeline_visible = visible
        self._set_overlay_open(self._pipeline_overlay, visible)
        self._sync_toggle_button(self._toggle_pipeline_btn, visible)
        if visible:
            self._schedule_mobile_overlay_policy('pipeline')

    def _toggle_transcript_size(self):
        self._transcript_size = 'full' if self._transcript_size != 'full' else 'peek'
        self._set_overlay_size(self._transcript_overlay, self._transcript_size)
        self._sync_size_button(self._transcript_size_btn, self._transcript_size)

    def _toggle_prompter_size(self):
        self._prompter_size = 'full' if self._prompter_size != 'full' else 'peek'
        self._set_overlay_size(self._prompter_overlay, self._prompter_size)
        self._sync_size_button(self._prompter_size_btn, self._prompter_size)

    def _set_overlay_open(self, overlay, is_open: bool) -> None:
        if not overlay:
            return
        if is_open:
            overlay.classes(add='is-open')
        else:
            overlay.classes(remove='is-open')

    def _sync_toggle_button(self, button, is_open: bool) -> None:
        if not button:
            return
        if is_open:
            button.classes(add='is-active')
        else:
            button.classes(remove='is-active')

    def _set_engine_focus(self, enabled: bool) -> None:
        if not self._client:
            return
        try:
            with self._client:
                ui.run_javascript(
                    f'window.engine && window.engine.setFocus({1 if enabled else 0});'
                )
        except Exception:
            pass

    def _exit_focus_mode(self, restore: bool = True) -> None:
        if not self._focus_mode:
            return
        self._focus_mode = False
        if restore and self._focus_restore:
            self._transcript_visible = self._focus_restore.get('transcript', False)
            self._prompter_visible = self._focus_restore.get('prompter', True)
            self._pipeline_visible = self._focus_restore.get('pipeline', False)
            self._set_transcript_visible(self._transcript_visible)
            self._set_prompter_visible(self._prompter_visible)
            self._set_pipeline_visible(self._pipeline_visible)
        self._sync_toggle_button(self._focus_btn, False)
        self._set_engine_focus(False)

    def _toggle_transcript(self):
        if self._focus_mode:
            self._exit_focus_mode(restore=False)
        self._set_transcript_visible(not self._transcript_visible)

    def _toggle_prompter(self):
        if self._focus_mode:
            self._exit_focus_mode(restore=False)
        self._set_prompter_visible(not self._prompter_visible)

    def _toggle_pipeline(self):
        if self._focus_mode:
            self._exit_focus_mode(restore=False)
        self._set_pipeline_visible(not self._pipeline_visible)

    def _toggle_focus_mode(self):
        self._focus_mode = not self._focus_mode
        if self._focus_mode:
            self._focus_restore = {
                'transcript': self._transcript_visible,
                'prompter': self._prompter_visible,
                'pipeline': self._pipeline_visible,
            }
            self._set_transcript_visible(False)
            self._set_prompter_visible(False)
            self._set_pipeline_visible(False)
            self._sync_toggle_button(self._focus_btn, True)
            self._set_engine_focus(True)
        else:
            self._exit_focus_mode(restore=True)

    def _sync_fx_button(self):
        if not self._toggle_fx_btn:
            return
        icon = 'volume_up' if self._fx_enabled else 'volume_off'
        try:
            self._toggle_fx_btn.props(f'icon={icon}')
        except Exception:
            pass

    def _toggle_fx(self):
        self._fx_enabled = not self._fx_enabled
        self._sync_toggle_button(self._toggle_fx_btn, self._fx_enabled)
        self._sync_fx_button()
        if not self._client:
            return
        try:
            with self._client:
                ui.run_javascript(
                    f'window.liveFeedback && window.liveFeedback.setEnabled({str(self._fx_enabled).lower()});'
                )
        except Exception:
            pass

    def _update_desk_ui(self):
        if not self._record_btn or not self._status_badge or not self._progress_badge:
            return

        recording = self.state.status == SessionStatus.RECORDING
        if recording:
            self._record_btn.text = 'STOP'
            self._record_btn.props('icon=stop')
            self._record_btn.classes(add='live-desk-btn--recording', remove='live-desk-btn--primary')
            self._status_badge.text = STATUS_RECORDING
            self._status_badge.classes(add='live-status-live')
        else:
            self._record_btn.text = 'START'
            self._record_btn.props('icon=mic')
            self._record_btn.classes(add='live-desk-btn--primary', remove='live-desk-btn--recording')
            self._status_badge.text = STATUS_READY
            self._status_badge.classes(remove='live-status-live')

        current, target = self.state.qa_progress
        self._progress_badge.text = f'{current}/{target}'

    async def _on_disconnect(self):
        """Sprzątanie po zamknięciu karty."""
        print("[LIVE] Client disconnected, cleaning up...", flush=True)
        for timer in self._timers:
            try:
                timer.cancel()
            except Exception:
                pass
        self._timers = []

        if self.transcriber:
            self.transcriber.stop()
        if self.ai_controller:
            self.ai_controller.force_stop()
        if self.active_question_panel:
            try:
                self.active_question_panel.destroy()
            except Exception:
                pass
        if self.prompter_panel:
            try:
                self.prompter_panel.destroy()
            except Exception:
                pass
        if self.qa_panel:
            try:
                self.qa_panel.destroy()
            except Exception:
                pass

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

    def _on_card_click(self, suggestion):
        """
        Callback: klikniecie w karte sugestii.

        Typy kart:
        - question: uruchamia Q+A (aktywne pytanie + odpowiedzi)
        - script/check: wsparcie lekarza (kopiuj/odhacz)
        """
        # Unwrap
        if isinstance(suggestion, Suggestion):
            text = suggestion.question
            kind = suggestion.kind or "question"
        elif isinstance(suggestion, dict):
            text = (suggestion.get("text") or suggestion.get("question") or "").strip()
            kind = (suggestion.get("type") or suggestion.get("kind") or "question").strip().lower()
        else:
            text = str(suggestion)
            kind = "question"

        if not text:
            return

        print(f"[LIVE] Card clicked ({kind}): {text[:30]}...", flush=True)

        if kind == "question":
            # 1. Aktywuj pytanie
            self.state.start_question(text, [])

            # 2. Zaladuj odpowiedzi
            asyncio.create_task(self._load_patient_answers(text))

            # 3. Kopiuj pytanie
            import json
            client = ui.context.client or self._client
            if client:
                try:
                    client.run_javascript(f'navigator.clipboard.writeText({json.dumps(text)})')
                except Exception:
                    pass
                try:
                    with client:
                        ui.notify("Skopiowano pytanie!", type='positive', position='top')
                except Exception:
                    pass
        else:
            # Script / checklista: wsparcie lekarza
            import json
            client = ui.context.client or self._client
            if client:
                if kind == "script":
                    try:
                        client.run_javascript(f'navigator.clipboard.writeText({json.dumps(text)})')
                    except Exception:
                        pass
                    try:
                        with client:
                            ui.notify("Skopiowano skrypt!", type='positive', position='top')
                    except Exception:
                        pass
                elif kind == "check":
                    try:
                        with client:
                            ui.notify("Odhaczone.", type='positive', position='top')
                    except Exception:
                        pass
                else:
                    try:
                        client.run_javascript(f'navigator.clipboard.writeText({json.dumps(text)})')
                    except Exception:
                        pass
                    try:
                        with client:
                            ui.notify("Skopiowano.", type='positive', position='top')
                    except Exception:
                        pass

        # Trigger AI (regeneracja i oznaczenie uzycia)
        if self.ai_controller:
            self.ai_controller.on_card_clicked(suggestion)

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
                spec_ids = self.ai_controller.current_spec_ids if self.ai_controller else None
                answers = await self.app.llm_service.generate_patient_answers(
                    question,
                    self.app.config,
                    spec_ids=spec_ids
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

    def _on_qa_pair_created(self, pair):
        """Callback: utworzono parę Q+A (manual lub auto)."""
        try:
            if self.ai_controller:
                self.ai_controller.on_qa_pair_created(pair.question, pair.answer)
        except Exception as e:
            print(f"[LIVE] QA pair routing error: {e}", flush=True)

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


