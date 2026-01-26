"""
Wizyta v2 - NiceGUI Edition
Nowoczesne GUI do generowania opisow stomatologicznych z wywiadu glosowego.
"""

import asyncio
import sys

# Windows: użyj SelectorEventLoop zamiast ProactorEventLoop
# ProactorEventLoop nie obsługuje prawidłowo Ctrl+C
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Callable
import multiprocessing

try:
    from core.log_utils import log
except Exception:
    def log(message: str):
        print(message, flush=True)


# === STATE MANAGEMENT ===

class ModelState(Enum):
    """Stan ładowania modelu."""
    IDLE = "idle"              # Nic nie załadowane
    LOADING = "loading"        # Ładowanie w toku (cancellable)
    READY = "ready"            # Model załadowany i gotowy
    ERROR = "error"            # Błąd ładowania


class TranscriptionState(Enum):
    """Stan transkrypcji."""
    IDLE = "idle"              # Gotowy do nagrywania
    RECORDING = "recording"    # Nagrywanie w toku
    PROCESSING = "processing"  # Transkrypcja w toku (cancellable)


@dataclass
class LoadedModelInfo:
    """Informacja o FAKTYCZNIE załadowanym modelu - Single Source of Truth."""
    backend: str              # np. "openvino_whisper"
    model_name: str           # np. "small", "large-v3"
    device: str               # np. "NPU", "GPU", "CPU"
    loaded_at: datetime = field(default_factory=datetime.now)

    def __str__(self):
        return f"{self.model_name} @ {self.device}"


class CancellableTask:
    """Wrapper dla operacji które można anulować."""

    def __init__(self, name: str):
        self.name = name
        self._cancel_event = threading.Event()
        self._process: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self.start_time = time.time()

    def set_process(self, process: subprocess.Popen):
        self._process = process

    def set_thread(self, thread: threading.Thread):
        self._thread = thread

    def cancel(self):
        """Anuluje zadanie - zabija subprocess jeśli istnieje."""
        print(f"[TASK] Cancelling: {self.name}", flush=True)
        self._cancel_event.set()
        if self._process:
            try:
                self._process.kill()
                self._process.wait(timeout=5)
                print(f"[TASK] Process killed", flush=True)
            except Exception as e:
                print(f"[TASK] Kill error: {e}", flush=True)

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def elapsed_seconds(self) -> int:
        return int(time.time() - self.start_time)

# Sciezki konfiguracji
CONFIG_FILE = Path(__file__).parent / "config.json"
ICD_FILE = Path(__file__).parent / "icd10.json"

# === IMPORTY OPCJONALNE ===

# Audio
try:
    import sounddevice as sd
    import numpy as np
    AUDIO_AVAILABLE = True
except ImportError:
    sd = None
    np = None
    AUDIO_AVAILABLE = False

# Google Gemini
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    types = None
    GENAI_AVAILABLE = False

# Transcriber
try:
    from core.transcriber import TranscriberManager, TranscriberType, ModelInfo
    TRANSCRIBER_AVAILABLE = True
except ImportError:
    TranscriberManager = None
    TranscriberType = None
    ModelInfo = None
    TRANSCRIBER_AVAILABLE = False

# Core services
# LLM Service
try:
    from core.llm_service import LLMService
except ImportError as e:
    print(f"[WARN] LLMService missing: {e}", flush=True)
    LLMService = None

try:
    from core.browser_service import BrowserService
except ImportError as e:
    print(f"[WARN] BrowserService missing: {e}", flush=True)
    BrowserService = None

try:
    from core.config_manager import ConfigManager
except ImportError as e:
    print(f"[WARN] ConfigManager missing: {e}", flush=True)
    ConfigManager = None

try:
    from core.model_loader import ModelLoader
except ImportError as e:
    print(f"[WARN] ModelLoader missing: {e}", flush=True)
    ModelLoader = None

try:
    from core.services.visit_service import VisitService
except ImportError as e:
    print(f"[WARN] VisitService missing: {e}", flush=True)
    VisitService = None

try:
    from core.specialization_manager import get_specialization_manager
except ImportError as e:
    print(f"[WARN] SpecializationManager missing: {e}", flush=True)
    get_specialization_manager = None

SERVICES_AVAILABLE = LLMService is not None

# UI Components
try:
    from app_ui.components.header import create_header
    from app_ui.components.settings import create_settings_section
    from app_ui.components.recording import create_recording_section
    from app_ui.components.results import create_results_section
    from app_ui.live import LiveInterviewView
except ImportError as e:
    print(f"[ERROR] Could not import UI components: {e}")

from nicegui import ui, app

# Global TranscriberManager instance (Singleton)
GLOBAL_TRANSCRIBER_MANAGER = None
# Transkrypt z live interview do przekazania do głównego widoku
GLOBAL_LIVE_TRANSCRIPT = None
# Windows Ctrl+C handler (musi być globalna żeby nie była garbage collectowana)
_WIN_CTRL_HANDLER = None

def get_transcriber_manager():
    global GLOBAL_TRANSCRIBER_MANAGER
    if not TRANSCRIBER_AVAILABLE:
        return None
    
    if GLOBAL_TRANSCRIBER_MANAGER is None:
        try:
            GLOBAL_TRANSCRIBER_MANAGER = TranscriberManager()
        except Exception as e:
            print(f"[ERROR] Could not initialize TranscriberManager: {e}", flush=True)
            return None
            
    return GLOBAL_TRANSCRIBER_MANAGER

# Claude Proxy
import sys
sys.path.insert(0, r"C:\Users\guzic\Documents\GitHub\tools\claude-code-py\src")
try:
    from proxy import start_proxy_server, get_proxy_base_url
    from anthropic import Anthropic
    PROXY_AVAILABLE = True
except ImportError:
    PROXY_AVAILABLE = False
    Anthropic = None


# === HELPERS ===




def load_icd10() -> dict:
    try:
        if ICD_FILE.exists():
            return json.loads(ICD_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def load_claude_token() -> Optional[str]:
    creds_path = Path.home() / ".claude" / ".credentials.json"
    if not creds_path.exists():
        return None
    try:
        creds = json.loads(creds_path.read_text())
        oauth_data = creds.get("claudeAiOauth", {})
        expires_at_ms = oauth_data.get("expiresAt", 0)
        if expires_at_ms:
            if datetime.now() >= datetime.fromtimestamp(expires_at_ms / 1000.0):
                return None
        return oauth_data.get("accessToken")
    except Exception:
        return None















# === DEVICE INFO ===

@dataclass
class DeviceInfo:
    id: str
    name: str
    full_name: str
    icon: str
    speed_multiplier: float
    available: bool
    is_intel: bool = False
    recommended: bool = False


def detect_devices() -> list[DeviceInfo]:
    """Wykrywa dostepne urzadzenia (NPU/GPU/CPU)."""
    devices = []

    # Sprawdz OpenVINO devices
    ov_devices = []
    try:
        from openvino import Core
        core = Core()
        ov_devices = core.available_devices
    except ImportError:
        pass
    except Exception:
        ov_devices = ["CPU"]

    # NPU
    has_npu = "NPU" in ov_devices
    devices.append(DeviceInfo(
        id="NPU",
        name="NPU",
        full_name="Intel AI Boost" if has_npu else "Intel NPU (niedostepny)",
        icon="memory",
        speed_multiplier=2.5 if has_npu else 0,
        available=has_npu,
        is_intel=True,
        recommended=has_npu
    ))

    # GPU
    has_gpu = "GPU" in ov_devices
    gpu_name = "Intel UHD Graphics"
    is_intel_gpu = True # Default assumption if OpenVINO detects it
    try:
        # Proba wykrycia nazwy GPU
        if has_gpu:
            from openvino import Core
            core = Core()
            gpu_name = core.get_property("GPU", "FULL_DEVICE_NAME")
            if "NVIDIA" in gpu_name:
                is_intel_gpu = False
    except Exception:
        pass

    devices.append(DeviceInfo(
        id="GPU",
        name="GPU",
        full_name=gpu_name if has_gpu else "GPU (niedostepny)",
        icon="videogame_asset",
        speed_multiplier=1.5 if has_gpu else 0,
        available=has_gpu,
        is_intel=is_intel_gpu,
        recommended=has_gpu and not has_npu
    ))

    # CPU - zawsze dostepny
    cpu_name = "Intel Core"
    try:
        import platform
        cpu_name = platform.processor() or "CPU"
        # Skroc nazwe
        if len(cpu_name) > 30:
            cpu_name = cpu_name[:30] + "..."
    except Exception:
        pass

    devices.append(DeviceInfo(
        id="CPU",
        name="CPU",
        full_name=cpu_name,
        icon="computer",
        speed_multiplier=1.0,
        available=True,
        recommended=not has_npu and not has_gpu
    ))

    return devices


# === MAIN APP ===

class WywiadApp:
    def __init__(self):
        # Config Manager
        if ConfigManager:
            self.config_manager = ConfigManager()
            self.config = self.config_manager # Kompatybilnosc wsteczna (self.config[...] dziala)
        else:
            self.config = {} # Fallback
            print("[ERROR] ConfigManager not loaded!", flush=True)

        self.icd10_codes = load_icd10()

        # Transcriber
        self.transcriber_manager = get_transcriber_manager()

        # Sync manager with config
        if self.transcriber_manager:
            try:
                # Set API Key
                api_key = self.config.get("api_key", "")
                self.transcriber_manager.set_gemini_api_key(api_key)

                # Set Backend
                backend_val = self.config.get("transcriber_backend", "gemini_cloud")
                if TRANSCRIBER_AVAILABLE:
                    self.transcriber_manager.set_current_backend(TranscriberType(backend_val))
                    print(f"[APP] Initialized TranscriberManager with backend: {backend_val}", flush=True)
            except Exception as e:
                print(f"[ERROR] Failed to sync TranscriberManager: {e}", flush=True)
        
        # Initialize Services
        self.llm_service = LLMService() if LLMService else None
        self.browser_service = BrowserService() if BrowserService else None
        self.visit_service = VisitService() if VisitService else None

        if not self.llm_service: print("[WARN] LLMService not available", flush=True)
        if not self.browser_service: print("[WARN] BrowserService not available", flush=True)

        # Last generation result (for saving visits)
        self.last_generation_result = None
        self.last_model_used = ""

        # State variables
        self.is_recording = False
        self.audio_data = []
        self.sample_rate = 16000
        self.stream = None

        # Proxy state
        self.proxy_started = False
        self.proxy_port = None

        # UI refs
        self.transcript_area = None
        self.recognition_field = None
        self.service_field = None
        self.procedure_field = None
        self.record_button = None
        self.record_status = None
        self.generate_button = None
        self.model_cards_container = None
        self.device_cards_container = None

        # Device detection
        self.devices = detect_devices()
        self.selected_device = self.config.get("selected_device", "auto")

        # Model download state
        self.downloading_model = None
        self.download_progress = 0.0

        # === NEW STATE MANAGEMENT ===
        # Model state - Single Source of Truth
        self.model_state = ModelState.IDLE
        self.loaded_model: Optional[LoadedModelInfo] = None
        self.model_error_message = ""

        # Transcription state
        self.transcription_state = TranscriptionState.IDLE

        # Current cancellable tasks
        self.current_task: Optional[CancellableTask] = None

        # UI refs for status indicator
        self.status_indicator = None
        self.status_label = None
        self.cancel_button = None

        # Initialize model status based on backend
        self._init_model_status()

    def _init_model_status(self):
        """Inicjalizuje status modelu - dla Gemini ustawiamy READY, dla innych IDLE."""
        backend_type = self.config.get("transcriber_backend", "gemini_cloud")

        if backend_type == "gemini_cloud":
            # Gemini Cloud nie wymaga lokalnego modelu
            self.model_state = ModelState.READY
            self.loaded_model = LoadedModelInfo(
                backend="gemini_cloud",
                model_name="gemini-2.0-flash",
                device="cloud"
            )
        else:
            # Lokalne backendy - sprawdź czy coś jest załadowane
            self.model_state = ModelState.IDLE
            self.loaded_model = None

    def _is_model_ready(self) -> bool:
        """Sprawdza czy model jest gotowy do użycia."""
        return self.model_state == ModelState.READY

    def _get_selected_model_name(self) -> str:
        """Zwraca nazwę wybranego modelu z konfiguracji."""
        return self.config.get("transcriber_model", "small")

    def _cancel_current_task(self):
        """Anuluje bieżące zadanie jeśli istnieje."""
        if self.current_task:
            self.current_task.cancel()
            self.current_task = None

    async def _load_model_async(self):
        """Ładuje model w SUBPROCESS - można zabić w każdej chwili."""
        backend_type = self.config.get("transcriber_backend", "gemini_cloud")

        # Gemini nie wymaga lokalnego modelu
        if backend_type == "gemini_cloud":
            self.model_state = ModelState.READY
            self.loaded_model = LoadedModelInfo(
                backend="gemini_cloud",
                model_name="gemini-2.0-flash",
                device="cloud"
            )
            self._update_status_ui()
            return

        # Dla backendów innych niż OpenVINO nie używamy subprocess loadera
        if backend_type != "openvino_whisper":
            # Sprawdź czy backend jest zainstalowany / dostępny
            if self.transcriber_manager:
                try:
                    backends = self.transcriber_manager.get_available_backends()
                    info = next((b for b in backends if b.type.value == backend_type), None)
                    if info and not info.is_installed:
                        self.model_state = ModelState.ERROR
                        self.model_error_message = f"Brak pakietu: {info.pip_package}"
                        self._update_status_ui()
                        return
                    if info and info.requires_ffmpeg and not info.ffmpeg_installed:
                        self.model_state = ModelState.ERROR
                        self.model_error_message = "Brak ffmpeg"
                        self._update_status_ui()
                        return
                except Exception:
                    pass

            model_name = self._get_selected_model_name()
            device = self.selected_device if self.selected_device != "auto" else self.get_best_device()
            self.model_state = ModelState.READY
            self.loaded_model = LoadedModelInfo(
                backend=backend_type,
                model_name=model_name,
                device=device
            )
            self._update_status_ui()
            return

        if not self.transcriber_manager:
            self.model_state = ModelState.ERROR
            self.model_error_message = "Brak transcriber manager"
            self._update_status_ui()
            return

        # Anuluj poprzednie zadanie (zabij subprocess)
        self._cancel_current_task()

        # Sprawdź czy OpenVINO jest zainstalowane
        try:
            backends = self.transcriber_manager.get_available_backends()
            info = next((b for b in backends if b.type.value == "openvino_whisper"), None)
            if info and not info.is_installed:
                self.model_state = ModelState.ERROR
                self.model_error_message = "Brak openvino-genai"
                self._update_status_ui()
                return
        except Exception:
            pass

        # Utwórz nowe zadanie
        model_name = self._get_selected_model_name()
        device = self.selected_device if self.selected_device != "auto" else self.get_best_device()

        # Sprawdź czy model OpenVINO jest pobrany (XML + BIN)
        try:
            from core.transcriber import MODELS_DIR
            suffix = "int8" if model_name in ["medium", "large-v3"] else "fp16"
            model_path = MODELS_DIR / "openvino-whisper" / f"whisper-{model_name}-{suffix}-ov"
            xml_path = model_path / "openvino_encoder_model.xml"
            bin_path = model_path / "openvino_encoder_model.bin"
            if not model_path.exists() or not xml_path.exists() or not bin_path.exists():
                # Spróbuj fallback do już pobranego modelu
                try:
                    backend = self.transcriber_manager.get_current_backend()
                    models = backend.get_models() if backend else []
                    downloaded = [m for m in models if getattr(m, 'is_downloaded', False)]
                    if downloaded:
                        # Preferuj 'small', potem pierwszy dostępny
                        fallback = next((m for m in downloaded if m.name == "small"), downloaded[0])
                        if fallback.name != model_name:
                            print(f"[LOAD] Model '{model_name}' missing, fallback to '{fallback.name}'", flush=True)
                            if backend and backend.set_model(fallback.name):
                                self.config["transcriber_model"] = fallback.name
                                try:
                                    self.config.save()
                                except Exception:
                                    pass
                                model_name = fallback.name
                                suffix = "int8" if model_name in ["medium", "large-v3"] else "fp16"
                                model_path = MODELS_DIR / "openvino-whisper" / f"whisper-{model_name}-{suffix}-ov"
                                xml_path = model_path / "openvino_encoder_model.xml"
                                bin_path = model_path / "openvino_encoder_model.bin"
                except Exception as e:
                    print(f"[LOAD] Fallback model check error: {e}", flush=True)

            if not model_path.exists() or not xml_path.exists() or not bin_path.exists():
                if model_path.exists():
                    try:
                        import shutil
                        shutil.rmtree(model_path)
                    except Exception:
                        pass
                self.model_state = ModelState.ERROR
                self.model_error_message = f"Model '{model_name}' nie jest pobrany. Kliknij 'Pobierz'."
                self._update_status_ui()
                return
        except Exception as e:
            print(f"[LOAD] Model check error: {e}", flush=True)
        task = CancellableTask(f"load_{model_name}_{device}")
        self.current_task = task

        # Ustaw stan ładowania
        self.model_state = ModelState.LOADING
        self.model_error_message = ""
        self._update_status_ui()

        print(f"[LOAD] Starting SUBPROCESS model load: {model_name} on {device}...", flush=True)

        try:
            # Ścieżka do loadera i modelu
            loader_script = Path(__file__).parent / "core" / "model_loader.py"
            from core.transcriber import MODELS_DIR
            suffix = "int8" if model_name in ["medium", "large-v3"] else "fp16"
            model_path = MODELS_DIR / "openvino-whisper" / f"whisper-{model_name}-{suffix}-ov"

            # Uruchom SUBPROCESS - można go zabić!
            process = subprocess.Popen(
                [sys.executable, str(loader_script), str(model_path), device],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            task.set_process(process)
            print(f"[LOAD] Subprocess started: PID {process.pid}", flush=True)

            # Czekaj na wynik w osobnym WĄTKU (nie blokuje event loop)
            loop = asyncio.get_event_loop()
            success, error = await loop.run_in_executor(None, lambda: self._wait_for_subprocess(process, task))

            # Sprawdź czy to NADAL aktualny task (nie został zastąpiony przez nowy)
            if self.current_task != task:
                print(f"[LOAD] Task replaced by newer one, ignoring result", flush=True)
                return

            if task.is_cancelled():
                print(f"[LOAD] Cancelled by user", flush=True)
                self.model_state = ModelState.IDLE
                self.loaded_model = None
            elif success:
                # Subprocess załadował model (w cache) - NIE ładujemy w main procesie
                # żeby nie blokować UI. Model załaduje się przy pierwszej transkrypcji.
                print(f"[LOAD] Subprocess done - model cached, skipping main process preload", flush=True)

                # Ustaw urządzenie w backendzie (to jest szybkie)
                if backend_type == "openvino_whisper":
                    try:
                        from core.transcriber import TranscriberType
                        ov_backend = self.transcriber_manager.get_backend(TranscriberType.OPENVINO_WHISPER)
                        if hasattr(ov_backend, 'set_device'):
                            ov_backend.set_device(device)
                    except Exception as e:
                        print(f"[LOAD] Could not set device on backend: {e}", flush=True)

                self.model_state = ModelState.READY
                self.loaded_model = LoadedModelInfo(
                    backend=backend_type,
                    model_name=model_name,
                    device=device
                )
                elapsed = task.elapsed_seconds()
                print(f"[LOAD] Model ready (cached) in {elapsed}s: {self.loaded_model}", flush=True)
                
                # AUTO-SWITCH: Jeśli brak klucza Gemini, a mamy model offline -> przełącz
                gemini_key = self.config.get("api_key", "")
                current_backend = self.config.get("transcriber_backend", "")
                
                if not gemini_key and current_backend == "gemini_cloud":
                    print("[AUTO-SWITCH] Gemini key missing, switching to offline backend...", flush=True)
                    # Preferuj openvino jeśli to on się załadował
                    new_backend = "openvino_whisper" 
                    
                    # Jeśli mamy managera, ustaw
                    if self.transcriber_manager:
                        try:
                            # Importuj typ enum dynamicznie
                            from core.transcriber import TranscriberType
                            self.transcriber_manager.set_current_backend(TranscriberType(new_backend))
                            self.config["transcriber_backend"] = new_backend
                            
                            # Odśwież UI w wątku głównym
                            # (chociaż jesteśmy w async, lepiej unikać problemów z NiceGUI)
                            self.refresh_backend_buttons()
                            ui.notify(f"Przełączono na {new_backend} (brak klucza Gemini)", type='positive')
                        except Exception as e:
                            print(f"[AUTO-SWITCH] Failed: {e}", flush=True)
            else:
                self.model_state = ModelState.ERROR
                self.model_error_message = error or "Subprocess failed"
                if error:
                    print(f"[LOAD] Subprocess failed: {error}", flush=True)
                else:
                    print(f"[LOAD] Subprocess failed", flush=True)

        except asyncio.CancelledError:
            print(f"[LOAD] Async cancelled", flush=True)
            task.cancel()  # Zabij subprocess
            self.model_state = ModelState.IDLE
            self.loaded_model = None
        except Exception as e:
            print(f"[LOAD] Error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self.model_state = ModelState.ERROR
            self.model_error_message = str(e)[:50]
        finally:
            if self.current_task == task:
                self.current_task = None
            self._update_status_ui()
            self.refresh_device_cards()

    def _wait_for_subprocess(self, process: subprocess.Popen, task: CancellableTask) -> tuple[bool, Optional[str]]:
        """Czeka na subprocess, sprawdzajac czy nie anulowano."""
        try:
            result_success = None
            result_error = None
            last_line = None
            while process.poll() is None:
                # Sprawdz czy anulowano
                if task.is_cancelled():
                    return False, None
                # Czytaj output
                line = process.stdout.readline()
                if line:
                    line = line.strip()
                    if line:
                        last_line = line
                        print(f"[SUBPROCESS] {line}", flush=True)
                    if line.startswith("RESULT:"):
                        import json
                        try:
                            result = json.loads(line[7:])
                            result_success = result.get("success", False)
                            result_error = result.get("error")
                        except Exception:
                            pass
                time.sleep(0.1)

            # Przeczytaj pozostaly output
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                last_line = line
                print(f"[SUBPROCESS] {line}", flush=True)
                if line.startswith("RESULT:"):
                    import json
                    try:
                        result = json.loads(line[7:])
                        result_success = result.get("success", False)
                        result_error = result.get("error")
                    except Exception:
                        pass

            if result_success is None:
                result_success = process.returncode == 0

            if not result_success and not result_error and last_line:
                result_error = last_line[:200]

            return bool(result_success), result_error
        except Exception as e:
            print(f"[SUBPROCESS] Wait error: {e}", flush=True)
            return False, str(e)

    def _set_device_sync(self, device_id: str):
        """Ustawia urządzenie w backendzie (synchronicznie)."""
        if self.transcriber_manager:
            ov_backend = self.transcriber_manager.get_backend(TranscriberType.OPENVINO_WHISPER)
            ov_backend.set_device(device_id)

    def _update_status_ui(self):
        """Aktualizuje UI statusu w headerze - pokazuje PRAWDZIWY stan."""
        if not self.status_indicator or not self.status_label:
            return

        # Pokaż/ukryj przycisk anuluj
        show_cancel = self.model_state == ModelState.LOADING or self.transcription_state == TranscriptionState.PROCESSING
        if self.cancel_button:
            self.cancel_button.set_visibility(show_cancel)

        # Status modelu
        if self.model_state == ModelState.IDLE:
            self.status_indicator.classes(replace='w-3 h-3 rounded-full bg-gray-400')
            self.status_label.text = "Model nie załadowany"

        elif self.model_state == ModelState.LOADING:
            self.status_indicator.classes(replace='w-3 h-3 rounded-full bg-yellow-500 animate-pulse')
            elapsed = self.current_task.elapsed_seconds() if self.current_task else 0
            model_name = self._get_selected_model_name()
            device = self.selected_device if self.selected_device != "auto" else self.get_best_device()
            self.status_label.text = f"Ładowanie {model_name} @ {device}... {elapsed}s"

        elif self.model_state == ModelState.READY:
            # Pokaż co FAKTYCZNIE jest załadowane
            if self.loaded_model:
                if self.loaded_model.backend == "gemini_cloud":
                    self.status_indicator.classes(replace='w-3 h-3 rounded-full bg-blue-500')
                    self.status_label.text = "Gemini Cloud"
                else:
                    self.status_indicator.classes(replace='w-3 h-3 rounded-full bg-green-500')
                    self.status_label.text = f"{self.loaded_model}"
            else:
                self.status_indicator.classes(replace='w-3 h-3 rounded-full bg-green-500')
                self.status_label.text = "Gotowy"

        elif self.model_state == ModelState.ERROR:
            self.status_indicator.classes(replace='w-3 h-3 rounded-full bg-red-500')
            self.status_label.text = self.model_error_message or "Błąd"

        # Aktualizuj przycisk nagrywania
        self._update_record_button()

    def _update_record_button(self):
        """Aktualizuje stan przycisku nagrywania i labela statusu."""
        if not self.record_button:
            return

        can_record = self._is_model_ready() and self.transcription_state == TranscriptionState.IDLE

        if can_record:
            self.record_button.enable()
            self.record_button.props(remove='disable')
            if hasattr(self, 'record_tooltip'):
                self.record_tooltip.text = "Kliknij aby nagrać"
            if hasattr(self, 'record_status'):
                self.record_status.text = "Gotowy do nagrywania"
                self.record_status.classes(remove='text-red-500 text-yellow-600', add='text-green-600')
        else:
            self.record_button.disable()
            self.record_button.props('disable')
            
            status_text = "Niedostępny"
            
            if self.model_state == ModelState.LOADING:
                status_text = "Ładowanie modelu..."
            elif self.transcription_state == TranscriptionState.PROCESSING:
                status_text = "Transkrypcja w toku..."
            elif self.model_state == ModelState.ERROR:
                status_text = "Błąd modelu"
            elif self.model_state == ModelState.IDLE:
                 status_text = "Model nie załadowany"

            if hasattr(self, 'record_tooltip'):
                self.record_tooltip.text = status_text
            
            if hasattr(self, 'record_status'):
                self.record_status.text = status_text
                self.record_status.classes(remove='text-green-600', add='text-gray-500')

    def _on_cancel_click(self):
        """Handler kliknięcia przycisku Anuluj."""
        if self.current_task:
            self._cancel_current_task()
            self.model_state = ModelState.IDLE
            self.loaded_model = None
            self._update_status_ui()
            self.refresh_device_cards()
            ui.notify("Anulowano", type='warning')

    def _retry_load_model(self):
        """Ponawia ładowanie modelu (tylko przy błędzie)."""
        if self.model_state == ModelState.ERROR:
            asyncio.create_task(self._load_model_async())

    def _refresh_status_timer(self):
        """Timer do odświeżania statusu podczas ładowania."""
        if self.model_state == ModelState.LOADING or self.transcription_state == TranscriptionState.PROCESSING:
            self._update_status_ui()

    def get_best_device(self) -> str:
        if self.selected_device != "auto":
            return self.selected_device
        for d in self.devices:
            if d.recommended and d.available:
                return d.id
        return "CPU"

    # === UI COMPONENTS ===

    def select_device(self, device_id: str):
        """Wybiera urządzenie i ładuje model."""
        # Znajdź device info
        device_info = next((d for d in self.devices if d.id == device_id), None)
        
        # SMART UX: Auto-switch to OpenVINO for Intel hardware
        current_backend = self.config.get("transcriber_backend", "")
        if device_info and (device_info.id == "NPU" or (device_info.id == "GPU" and device_info.is_intel)):
            if current_backend != "openvino_whisper":
                print(f"[UI] Smart UX: Auto-switching to OpenVINO for {device_id}", flush=True)
                
                # Zmień backend
                if self.transcriber_manager:
                    try:
                        from core.transcriber import TranscriberType
                        if self.transcriber_manager.set_current_backend(TranscriberType.OPENVINO_WHISPER):
                            self.config["transcriber_backend"] = "openvino_whisper"
                            self.refresh_backend_buttons()
                            ui.notify(f"Przełączono na OpenVINO (wymagane dla {device_id})", type='positive')
                    except Exception as e:
                        print(f"[UI] Auto-switch failed: {e}", flush=True)

        # Sprawdź czy już załadowane na tym urządzeniu (po ewentualnej zmianie backendu)
        # Musimy sprawdzić ponownie stan, bo mógł się zmienić backend
        if (device_id == self.selected_device and
            self.model_state == ModelState.READY and
            self.loaded_model and
            self.loaded_model.device == device_id):
            return

        print(f"[UI] Device selection: {device_id}", flush=True)

        # Zapisz wybór
        self.selected_device = device_id
        self.config["selected_device"] = device_id
        self.config.save()

        # Odśwież karty i rozpocznij ładowanie
        self.refresh_device_cards()
        asyncio.create_task(self._load_model_async())

    def refresh_device_cards(self):
        """Odświeża karty urządzeń."""
        if self.device_cards_container:
            self.device_cards_container.clear()
            current_backend = self.config.get("transcriber_backend", "")
            
            with self.device_cards_container:
                # Jeśli wybrano chmurę, ukryj wybór sprzętu
                if current_backend == "gemini_cloud":
                    with ui.card().classes('w-full h-48 bg-blue-50 items-center justify-center text-center p-4 shadow-none border-2 border-blue-100'):
                        with ui.row().classes('items-center gap-4'):
                            ui.icon('cloud_upload', size='4xl').classes('text-blue-400')
                            with ui.column().classes('items-start'):
                                ui.label('Przetwarzanie w chmurze').classes('text-xl font-bold text-blue-800')
                                ui.label('Obliczenia wykonywane są na serwerach Google.').classes('text-gray-600')
                                ui.label('Twoja karta graficzna i procesor odpoczywają.').classes('text-sm text-gray-500')
                    return

                # Dla offline - pokaż karty
                for device in self.devices:
                    self.create_device_card(device, current_backend)

    def create_device_card(self, device: DeviceInfo, current_backend: str) -> ui.card:
        """Tworzy kartę urządzenia."""
        is_selected = (self.selected_device == device.id) or (self.selected_device == "auto" and device.recommended)
        is_loading = is_selected and self.model_state == ModelState.LOADING
        is_ready = is_selected and self.model_state == ModelState.READY and self.loaded_model and self.loaded_model.device == device.id

        # Compatibility check
        is_compatible = True
        warning_msg = ""
        compatibility_reason = ""
        
        # NPU requires OpenVINO
        if device.id == "NPU":
            if current_backend != "openvino_whisper":
                is_compatible = False
                warning_msg = "Wymaga OpenVINO"
                compatibility_reason = "NPU jest obsługiwane tylko przez silnik OpenVINO. Kliknij, aby przełączyć."

        # Intel GPU compatibility
        elif device.id == "GPU" and device.is_intel:
            if current_backend in ["faster_whisper", "openai_whisper"]:
                is_compatible = False
                warning_msg = "Brak CUDA (NVIDIA)"
                compatibility_reason = "Ten silnik wymaga karty NVIDIA (CUDA). Dla Intel Arc użyj OpenVINO. Kliknij, aby przełączyć automatycznie."
            elif current_backend != "openvino_whisper" and current_backend != "gemini_cloud":
                 # Inne backendy (przyszłościowo)
                 is_compatible = False
                 warning_msg = "Wymaga OpenVINO"

        # Style
        base_classes = 'w-48 h-48 transition-all duration-200 cursor-pointer'
        if is_loading:
            style_classes = f'{base_classes} ring-2 ring-yellow-500 bg-yellow-50'
        elif is_ready:
            style_classes = f'{base_classes} ring-2 ring-green-500 bg-green-50'
        elif is_selected:
            style_classes = f'{base_classes} ring-2 ring-blue-500 bg-blue-50'
        elif not is_compatible:
            style_classes = f'{base_classes} opacity-70 bg-gray-50 border-dashed border-2 border-gray-300'
        else:
            style_classes = f'{base_classes} hover:shadow-lg'

        with ui.card().classes(style_classes) as card:
            # Clickable even if not compatible (to trigger auto-switch)
            if device.available:
                card.on('click', lambda d=device: self.select_device(d.id))
            
            # Tooltip explaining the limitation/switch
            if compatibility_reason:
                ui.tooltip(compatibility_reason)

            with ui.column().classes('items-center gap-2 p-3 w-full h-full justify-between'):
                # Icon + Name
                with ui.column().classes('items-center gap-1 w-full'):
                    if is_loading:
                        color = 'text-yellow-600'
                    elif is_ready:
                        color = 'text-green-600'
                    elif is_selected:
                        color = 'text-blue-600'
                    elif not device.available:
                        color = 'text-gray-400'
                    elif not is_compatible:
                        color = 'text-orange-400'
                    else:
                        color = 'text-gray-600'

                    ui.icon(device.icon, size='xl').classes(color)
                    ui.label(device.name).classes('text-lg font-bold')
                    ui.label(device.full_name).classes('text-xs text-gray-500 text-center leading-tight')

                # Status section
                with ui.column().classes('items-center justify-center w-full'):
                    if is_loading:
                        ui.spinner(size='sm', color='yellow')
                        elapsed = self.current_task.elapsed_seconds() if self.current_task else 0
                        ui.label(f"Ładowanie... {elapsed}s").classes('text-xs text-yellow-600')
                    elif is_ready:
                        ui.badge("GOTOWY", color='green')
                    elif is_selected:
                        ui.badge("WYBRANE", color='blue')
                    elif warning_msg:
                        ui.badge(warning_msg, color='orange')
                    elif device.recommended and device.available:
                        ui.badge("ZALECANE", color='gray')
                    elif device.available:
                        speed_text = f"~{device.speed_multiplier}x"
                        ui.label(speed_text).classes('text-sm text-gray-500')
                    else:
                        ui.label("Niedostępny").classes('text-sm text-red-400')

        return card

    def create_model_card(self, model: ModelInfo, backend_type) -> ui.card:
        """Tworzy karte modelu."""
        is_active = False
        if self.transcriber_manager:
            try:
                current = self.transcriber_manager.get_current_backend().get_current_model()
                is_active = (current == model.name)
            except Exception:
                pass

        is_downloading = (self.downloading_model == model.name)

        # Quality/speed mappings
        quality_map = {"tiny": 0.4, "base": 0.6, "small": 0.8, "medium": 0.9, "large-v3": 1.0, "large": 1.0}
        speed_map = {"tiny": 1.0, "base": 0.9, "small": 0.8, "medium": 0.6, "large-v3": 0.4, "large": 0.4}

        quality = quality_map.get(model.name, 0.5)
        speed = speed_map.get(model.name, 0.5)

        with ui.card().classes('w-full') as card:
            with ui.row().classes('w-full justify-between items-center'):
                with ui.row().classes('items-center gap-2'):
                    # Icon based on status
                    if is_active:
                        ui.icon('check_circle', color='green').classes('text-xl')
                    elif is_downloading:
                        ui.spinner(size='sm')
                    elif model.is_downloaded:
                        ui.icon('folder', color='blue').classes('text-xl')
                    else:
                        ui.icon('cloud_download', color='gray').classes('text-xl')

                    ui.label(model.name).classes('text-lg font-bold')

                # Status badge
                if is_active:
                    ui.badge("AKTYWNY", color='green')
                elif is_downloading:
                    ui.badge("POBIERANIE...", color='orange')
                elif model.is_downloaded:
                    ui.badge("POBRANY", color='blue')
                else:
                    ui.badge("DOSTEPNY", color='gray')

            # Progress bars for quality/speed
            with ui.row().classes('w-full gap-8 mt-4'):
                with ui.column().classes('flex-1'):
                    ui.label('Jakosc').classes('text-xs text-gray-500')
                    ui.linear_progress(value=quality, show_value=False).classes('h-2')

                with ui.column().classes('flex-1'):
                    ui.label('Szybkosc').classes('text-xs text-gray-500')
                    ui.linear_progress(value=speed, show_value=False, color='green').classes('h-2')

            # Size and description
            size_str = f"{model.size_mb} MB" if model.size_mb < 1000 else f"{model.size_mb/1000:.1f} GB"
            ui.label(f"{size_str} - {model.description}").classes('text-sm text-gray-500 mt-2')

            # Download progress (if downloading)
            if is_downloading:
                with ui.column().classes('w-full mt-2') as progress_col:
                    progress_bar = ui.linear_progress(value=0, show_value=False).classes('h-3')
                    progress_label = ui.label("0%").classes('text-sm text-center')

                    # Timer to update progress
                    def update_progress():
                        if self.downloading_model == model.name:
                            progress_bar.value = self.download_progress
                            progress_label.text = f"{int(self.download_progress * 100)}%"
                        else:
                            timer.deactivate()

                    timer = ui.timer(0.5, update_progress)

            # Action buttons
            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                if model.is_downloaded and not is_active:
                    ui.button('Usun', icon='delete', color='red').props('flat').on(
                        'click', lambda m=model: self.delete_model(m.name)
                    )
                    ui.button('Aktywuj', icon='play_arrow', color='primary').on(
                        'click', lambda m=model: self.activate_model(m.name)
                    )
                elif not model.is_downloaded and not is_downloading:
                    ui.button('Pobierz', icon='download', color='primary').on(
                        'click', lambda m=model: asyncio.create_task(self.download_model(m.name))
                    )
                elif is_active:
                    ui.label('W uzyciu').classes('text-green-600 font-medium')

        return card

    def refresh_model_cards(self):
        """Odswieza karty modeli."""
        if not self.model_cards_container or not self.transcriber_manager:
            return

        self.model_cards_container.clear()

        try:
            backend = self.transcriber_manager.get_current_backend()
            models = backend.get_models()

            # Get current backend type
            backend_type = self.transcriber_manager.get_current_type()

            with self.model_cards_container:
                for model in models:
                    self.create_model_card(model, backend_type)
        except Exception as e:
            with self.model_cards_container:
                ui.label(f"Blad ladowania modeli: {e}").classes('text-red-500')

    def download_model_sync(self, model_name: str):
        """Pobiera model (synchronicznie, w uzyciu z asyncio)."""
        if not self.transcriber_manager:
            return False

        try:
            backend = self.transcriber_manager.get_current_backend()

            def progress_cb(p):
                self.download_progress = p

            success = backend.download_model(model_name, progress_cb)
            return success
        except Exception as e:
            print(f"Download error: {e}")
            return False

    async def download_model(self, model_name: str):
        """Pobiera model."""
        if not self.transcriber_manager:
            return

        self.downloading_model = model_name
        self.download_progress = 0.0
        self.refresh_model_cards()

        # Run in thread
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, lambda: self.download_model_sync(model_name))

        self.downloading_model = None

        if success:
            self.download_progress = 1.0
        else:
            self.download_progress = 0.0

        self.refresh_model_cards()

    def activate_model(self, model_name: str):
        """Aktywuje model i przeładowuje."""
        if not self.transcriber_manager:
            return

        try:
            backend = self.transcriber_manager.get_current_backend()
            if backend.set_model(model_name):
                self.config["transcriber_model"] = model_name
                self.config.save()
                ui.notify(f"Model {model_name} aktywowany!", type='positive')

                # Reset state immediately
                self.model_state = ModelState.LOADING
                self.loaded_model = None
                self._update_status_ui()

                # Przeładuj model na aktualnym urządzeniu
                self.refresh_model_cards()
                asyncio.create_task(self._load_model_async())
            else:
                ui.notify("Nie udalo sie aktywowac modelu", type='negative')
                self.refresh_model_cards()
        except Exception as e:
            ui.notify(f"Blad: {e}", type='negative')
            self.refresh_model_cards()

    def delete_model(self, model_name: str):
        """Usuwa pobrany model."""
        if not self.transcriber_manager:
            return

        try:
            backend = self.transcriber_manager.get_current_backend()

            # Sprawdź czy to nie jest aktywny model
            if backend.get_current_model() == model_name:
                ui.notify(f"Nie można usunąć aktywnego modelu!", type='negative')
                return

            success = backend.delete_model(model_name)
            if success:
                ui.notify(f"Model {model_name} usunięty", type='positive')
            else:
                ui.notify(f"Nie udało się usunąć modelu {model_name}", type='negative')

            self.refresh_model_cards()
        except Exception as e:
            ui.notify(f"Błąd: {e}", type='negative')

    def select_backend(self, backend_value: str):
        """Wybiera backend transkrypcji."""
        if not self.transcriber_manager:
            return

        try:
            backend_type = TranscriberType(backend_value)

            # Check if installed
            backends = self.transcriber_manager.get_available_backends()
            info = next((b for b in backends if b.type == backend_type), None)

            if info and not info.is_installed:
                # Pokaz dialog instalacji
                self.show_install_dialog(info)
                return

            if self.transcriber_manager.set_current_backend(backend_type):
                self.config["transcriber_backend"] = backend_value
                self.config.save()
                ui.notify(f"Wybrano: {info.name if info else backend_value}", type='positive')
                
                # SMART UX: Fallback to CPU if current device is not supported
                # e.g. switching from OpenVINO (NPU) to Faster Whisper (CPU-only on Intel)
                if backend_value != "openvino_whisper":
                    current_device = next((d for d in self.devices if d.id == self.selected_device), None)
                    if current_device and (current_device.id == "NPU" or (current_device.id == "GPU" and current_device.is_intel)):
                        print(f"[UI] Smart UX: Reverting to CPU (backend {backend_value} does not support Intel NPU/GPU)", flush=True)
                        self.selected_device = "CPU"
                        self.config["selected_device"] = "CPU"
                        self.config.save()
                        ui.notify("Przełączono na CPU (backend nie wspiera NPU/GPU)", type='warning')

                # Reset state immediately
                self.model_state = ModelState.LOADING
                self.loaded_model = None
                self._update_status_ui()

                self.refresh_device_cards() # Refresh to show compatibility badges
                self.refresh_model_cards()
                self.refresh_backend_buttons()

                # Załaduj model dla nowego backendu
                asyncio.create_task(self._load_model_async())
            else:
                ui.notify("Nie udalo sie zmienic backendu", type='negative')
        except Exception as e:
            ui.notify(f"Blad: {e}", type='negative')

    def show_install_dialog(self, info):
        """Pokazuje dialog instalacji backendu."""
        client = ui.context.client
        with ui.dialog() as dialog, ui.card().classes('w-[450px]'):
            ui.label(f'Instalacja: {info.name}').classes('text-xl font-bold')
            ui.separator()

            ui.label(f'Pakiet: {info.pip_package}').classes('text-gray-600 font-mono text-sm')

            # Szacowany rozmiar
            size_estimates = {
                'faster-whisper': '~150 MB',
                'openai-whisper': '~1 GB (zawiera PyTorch)',
                'openvino openvino-genai librosa': '~500 MB',
            }
            size = size_estimates.get(info.pip_package, 'nieznany')
            ui.label(f'Szacowany rozmiar: {size}').classes('text-gray-500 text-sm')

            ui.label('Instalacja moze potrwac 1-5 minut w zaleznosci od polaczenia.').classes('text-sm text-orange-600 mt-2')

            ui.separator().classes('my-3')

            # Progress section
            progress_container = ui.column().classes('w-full gap-2')
            progress_container.visible = False

            with progress_container:
                progress_label = ui.label('Przygotowywanie...').classes('text-sm text-blue-600')
                progress_bar = ui.linear_progress(value=0, show_value=False).props('indeterminate').classes('h-2')

                # Etapy instalacji
                with ui.column().classes('w-full gap-1 mt-2'):
                    stages = [
                        ('stage_download', 'Pobieranie pakietow...'),
                        ('stage_install', 'Instalowanie...'),
                        ('stage_verify', 'Weryfikacja...'),
                    ]
                    stage_labels = {}
                    for stage_id, stage_text in stages:
                        with ui.row().classes('items-center gap-2'):
                            stage_icon = ui.icon('radio_button_unchecked', size='xs').classes('text-gray-400')
                            stage_label = ui.label(stage_text).classes('text-xs text-gray-400')
                            stage_labels[stage_id] = (stage_icon, stage_label)

            # Success card - hidden by default
            success_card = ui.card().classes('w-full bg-green-100 border-2 border-green-500 mt-4')
            success_card.visible = False
            with success_card:
                with ui.column().classes('items-center gap-2 p-4'):
                    ui.icon('check_circle', size='xl', color='green')
                    ui.label('ZAINSTALOWANO!').classes('text-xl font-bold text-green-700')
                    ui.label(f'Pakiet {info.pip_package} zostal zainstalowany.').classes('text-green-600')
                    ui.label('Uruchom ponownie aplikacje aby uzyc tego silnika.').classes('text-sm text-gray-600')

            # Error card - hidden by default
            error_card = ui.card().classes('w-full bg-red-100 border-2 border-red-500 mt-4')
            error_card.visible = False
            with error_card:
                with ui.column().classes('items-center gap-2 p-4'):
                    ui.icon('error', size='xl', color='red')
                    ui.label('BLAD INSTALACJI').classes('text-xl font-bold text-red-700')
                    error_message_label = ui.label('').classes('text-red-600 text-sm')

            # Buttons
            button_row = ui.row().classes('w-full justify-end gap-2 mt-4')
            with button_row:
                cancel_btn = ui.button('Anuluj', on_click=dialog.close).props('flat')
                install_btn = ui.button('Zainstaluj', icon='download', color='primary')

            async def do_install():
                # Show progress, hide buttons
                progress_container.visible = True
                install_btn.visible = False
                cancel_btn.text = "Czekaj..."
                cancel_btn.props('disable')

                def update_stage(stage_idx, status='active'):
                    stage_keys = ['stage_download', 'stage_install', 'stage_verify']
                    for i, key in enumerate(stage_keys):
                        icon, label = stage_labels[key]
                        if i < stage_idx:
                            icon.props('name=check_circle')
                            icon.classes(replace='text-green-600')
                            label.classes(replace='text-xs text-green-600')
                        elif i == stage_idx:
                            icon.props('name=pending')
                            icon.classes(replace='text-blue-600')
                            label.classes(replace='text-xs text-blue-600 font-medium')
                        else:
                            icon.props('name=radio_button_unchecked')
                            icon.classes(replace='text-gray-400')
                            label.classes(replace='text-xs text-gray-400')

                def progress_cb(msg):
                    progress_label.text = msg
                    msg_lower = msg.lower()
                    if 'pobier' in msg_lower or 'download' in msg_lower or 'collect' in msg_lower:
                        update_stage(0)
                    elif 'instal' in msg_lower or 'rozpak' in msg_lower:
                        update_stage(1)
                    elif 'weryfik' in msg_lower or 'gotowe' in msg_lower or 'zainstal' in msg_lower:
                        update_stage(2)

                update_stage(0)

                loop = asyncio.get_event_loop()
                success, message = await loop.run_in_executor(
                    None,
                    lambda: self.transcriber_manager.install_backend(info.type, progress_cb)
                )

                # Hide progress elements
                progress_bar.visible = False
                progress_label.visible = False

                # Enable close button
                cancel_btn.props(remove='disable')

                if success:
                    update_stage(3)  # All done
                    success_card.visible = True
                    cancel_btn.text = "Zamknij"
                    cancel_btn.props('color=green')
                    self._notify_client(client, f"Zainstalowano {info.name}!", type='positive', timeout=5000)
                    # Odśwież stan backendów i modeli po instalacji
                    self.refresh_backend_buttons()
                    self.refresh_model_cards()
                    self.refresh_device_cards()
                else:
                    error_message_label.text = message[:100]
                    error_card.visible = True
                    cancel_btn.text = "Zamknij"
                    self._notify_client(client, f"Blad: {message}", type='negative', timeout=5000)

            install_btn.on('click', lambda: asyncio.create_task(do_install()))

        dialog.open()

    def refresh_backend_buttons(self):
        """Odswieza przyciski backendow - wywolywane po zmianie."""
        if not hasattr(self, 'backend_buttons_container') or not self.backend_buttons_container:
            return

        # Pobierz info o backendach
        backends_info = {}
        if self.transcriber_manager:
            for b in self.transcriber_manager.get_available_backends():
                backends_info[b.type.value] = b

        backend_options = [
            ('gemini_cloud', 'Gemini Cloud', 'cloud', 'Online API'),
            ('faster_whisper', 'Faster Whisper', 'speed', 'Najszybszy offline'),
            ('openai_whisper', 'OpenAI Whisper', 'psychology', 'Oryginalny'),
            ('openvino_whisper', 'OpenVINO', 'memory', 'Intel NPU/GPU'),
        ]

        current_backend = self.config.get("transcriber_backend", "gemini_cloud")

        self.backend_buttons_container.clear()
        with self.backend_buttons_container:
            for key, name, icon, desc in backend_options:
                is_current = (key == current_backend)
                info = backends_info.get(key)
                is_installed = info.is_installed if info else True

                with ui.card().classes(
                    f'w-44 cursor-pointer transition-all {"ring-2 ring-blue-500 bg-blue-50" if is_current else "hover:shadow-md"} {"opacity-60" if not is_installed else ""}'
                ).on('click', lambda k=key: self.select_backend(k)):
                    with ui.column().classes('items-center gap-1 p-3'):
                        ui.icon(icon, size='md').classes('text-blue-600' if is_current else 'text-gray-500')
                        ui.label(name).classes('font-bold text-sm')
                        ui.label(desc).classes('text-xs text-gray-500')

                        if not is_installed:
                            ui.badge('Wymaga instalacji', color='orange').classes('mt-1')
                        elif is_current:
                            ui.badge('Aktywny', color='green').classes('mt-1')

    # === RECORDING ===

    def toggle_recording(self):
        """Przelacza nagrywanie."""
        if not AUDIO_AVAILABLE:
            ui.notify("Brak biblioteki audio (sounddevice)", type='negative')
            return

        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        """Rozpoczyna nagrywanie."""
        # Sprawdź czy model jest gotowy
        if not self._is_model_ready():
            if self.model_state == ModelState.LOADING:
                ui.notify("Model się ładuje... Poczekaj.", type='warning')
            else:
                ui.notify("Model nie jest gotowy. Sprawdź status w headerze.", type='warning')
            return

        self.is_recording = True
        self.transcription_state = TranscriptionState.RECORDING
        self.audio_data = []

        if self.record_button:
            self.record_button.props('color=red icon=stop')
            self.record_button.text = "Zatrzymaj"
        if self.record_status:
            self.record_status.text = "Nagrywanie..."
            self.record_status.classes(replace='text-red-600')

        def audio_callback(indata, frames, time_info, status):
            if self.is_recording:
                self.audio_data.append(indata.copy())

        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype=np.int16,
            callback=audio_callback
        )
        self.stream.start()

    def stop_recording(self):
        """Zatrzymuje nagrywanie i rozpoczyna transkrypcję."""
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        if self.record_button:
            self.record_button.props('color=primary icon=mic')
            self.record_button.text = "Nagrywaj"

        if self.audio_data:
            # Ustaw stan na PROCESSING
            self.transcription_state = TranscriptionState.PROCESSING
            self._update_status_ui()

            # Pokaż status z info o załadowanym modelu
            if self.record_status:
                if self.loaded_model:
                    self.record_status.text = f"Transkrypcja ({self.loaded_model})..."
                else:
                    self.record_status.text = "Transkrypcja..."
                self.record_status.classes(replace='text-orange-600')

            # Save to temp file
            audio_array = np.concatenate(self.audio_data, axis=0)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = f.name
                with wave.open(f.name, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(audio_array.tobytes())

            # Transcribe in background thread (nie blokuje event loop)
            threading.Thread(target=self.transcribe_audio, args=(temp_path,), daemon=True).start()
        else:
            self.transcription_state = TranscriptionState.IDLE
            if self.record_status:
                self.record_status.text = "Brak nagrania"
                self.record_status.classes(replace='text-gray-500')

    def transcribe_audio(self, audio_path: str):
        """Transkrybuje audio."""
        print(f"[DEBUG] transcribe_audio started: {audio_path}", flush=True)
        transcript = None
        error = None

        try:
            print(f"[DEBUG] transcriber_manager: {self.transcriber_manager}", flush=True)
            print(f"[DEBUG] current backend: {self.transcriber_manager.get_current_type() if self.transcriber_manager else 'None'}", flush=True)

            if self.transcriber_manager:
                print("[DEBUG] Calling transcriber_manager.transcribe...", flush=True)
                transcript = self.transcriber_manager.transcribe(audio_path, language="pl")
                print(f"[DEBUG] Transcription result: {transcript[:100] if transcript else 'None'}...", flush=True)
            else:
                # Fallback to Gemini
                api_key = self.config.get("api_key", "")
                if not api_key or not GENAI_AVAILABLE:
                    raise ValueError("Brak API key lub biblioteki Gemini")

                print("[DEBUG] Using Gemini fallback...")
                client = genai.Client(api_key=api_key)
                with open(audio_path, "rb") as f:
                    audio_bytes = f.read()

                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[
                        "Przetranscybuj poniższe nagranie audio na tekst. Zwróć tylko transkrypcję.",
                        types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")
                    ]
                )
                transcript = response.text.strip()

        except Exception as e:
            error = str(e)[:100]
            print(f"[DEBUG] Transcription error: {error}", flush=True)
            import traceback
            traceback.print_exc()

        finally:
            try:
                os.unlink(audio_path)
            except Exception:
                pass

        # Store result for UI update
        print(f"[DEBUG] Setting _transcription_result: transcript={bool(transcript)}, error={error}", flush=True)
        self._transcription_result = {'transcript': transcript, 'error': error}

    def check_transcription_result(self):
        """Sprawdza wynik transkrypcji i aktualizuje UI."""
        if not hasattr(self, '_transcription_result') or self._transcription_result is None:
            return

        result = self._transcription_result
        self._transcription_result = None

        # Reset transcription state
        self.transcription_state = TranscriptionState.IDLE
        self._update_status_ui()
        
        # Auto-suggest questions
        if result['transcript']:
            asyncio.create_task(self.generate_suggestions())

        if result['error']:
            if self.record_status:
                self.record_status.text = f"Błąd: {result['error'][:50]}"
                self.record_status.classes(replace='text-red-600')
            ui.notify(f"Błąd transkrypcji: {result['error']}", type='negative')
        elif result['transcript']:
            if self.transcript_area:
                current = self.transcript_area.value or ""
                if current.strip():
                    self.transcript_area.value = current + "\n" + result['transcript']
                else:
                    self.transcript_area.value = result['transcript']

            if self.record_status:
                self.record_status.text = "Gotowy"
                self.record_status.classes(replace='text-green-600')

            ui.notify("Transkrypcja zakończona!", type='positive')

    # === GENERATION ===

    async def generate_suggestions(self):
        """Generuje sugestie pytań."""
        transcript = self.transcript_area.value if self.transcript_area else ""
        # if not transcript.strip():
        #     ui.notify("Brak treści wywiadu", type='warning')
        #     return

        if not self.llm_service:
            return

        if hasattr(self, 'suggestion_btn'):
            self.suggestion_btn.props('loading')

        try:
            suggestions = await self.llm_service.generate_suggestions(transcript, self.config)
            
            if hasattr(self, 'suggestions_container'):
                self.suggestions_container.clear()
                with self.suggestions_container:
                    for question in suggestions:
                        ui.chip(question, icon='help_outline', on_click=lambda q=question: self.copy_to_clipboard(q, "Pytanie")).props('clickable color=blue-100 text-color=blue-800')
            
        except Exception as e:
            print(f"[UI] Suggestion error: {e}", flush=True)
        finally:
            if hasattr(self, 'suggestion_btn'):
                self.suggestion_btn.props(remove='loading')

    async def generate_description(self):
        """Generuje opis stomatologiczny używając LLMService (Struktura JSON)."""
        transcript = self.transcript_area.value if self.transcript_area else ""
        if not transcript.strip():
            if self.record_status:
                self.record_status.text = "Brak transkrypcji!"
                self.record_status.classes(replace='text-red-600')
            return

        if not self.llm_service:
            ui.notify("Serwis AI nie jest dostępny", type='negative')
            return

        # UI loading state
        if self.generate_button:
            self.generate_button.props('loading')

        try:
            # Pobierz aktywną specjalizację
            spec_id = 1
            if get_specialization_manager:
                spec_manager = get_specialization_manager()
                spec_id = spec_manager.get_active().id

            # Wywołanie serwisu (z nowym formatem JSON)
            result_json, used_model = await self.llm_service.generate_description(
                transcript,
                self.icd10_codes, # Deprecated, ale musi być przekazane
                self.config,
                spec_id=spec_id
            )

            # Pobierz aktywną specjalizację
            spec_manager = None
            spec_name = "Stomatologia"
            if get_specialization_manager:
                spec_manager = get_specialization_manager()
                spec = spec_manager.get_active()
                spec_name = spec.name
                
            # Dostosuj nagłówek i pole kolumny lokalizacji
            loc_header = "Ząb" if spec_name == "Stomatologia" else "Lokalizacja"
            loc_field = "zab"  # Używamy jednego pola w gridzie dla uproszczenia, mapujemy dane
            
            # Aktualizacja definicji kolumn gridu (Dynamiczne nagłówki)
            new_column_defs = [
                {
                    'headerName': '',
                    'field': 'selected',
                    'checkboxSelection': True,
                    'headerCheckboxSelection': True,
                    'width': 50,
                    'maxWidth': 50,
                    'pinned': 'left'
                },
                {'headerName': 'Kod', 'field': 'kod', 'width': 100},
                {'headerName': 'Nazwa', 'field': 'nazwa', 'flex': 1},
                {'headerName': loc_header, 'field': loc_field, 'width': 140},
                {'headerName': 'Opis', 'field': 'opis_tekstowy', 'flex': 1}
            ]

            # Helper do czyszczenia i normalizacji danych
            def clean_data(rows):
                cleaned = []
                for row in rows:
                    new_row = {}
                    
                    # 1. Kod
                    new_row['kod'] = row.get('kod') or row.get('icd10_code') or row.get('code') or ""
                    
                    # 2. Nazwa
                    new_row['nazwa'] = row.get('nazwa') or row.get('name') or row.get('desc') or ""
                    
                    # 3. Lokalizacja (mapowanie na 'zab')
                    # Szukamy różnych wariantów jakie AI może zwrócić
                    loc_val = (
                        row.get('zab') or 
                        row.get('numer zęba') or 
                        row.get('lokalizacja') or 
                        row.get('location') or 
                        row.get('lokalizacja anatomiczna') or 
                        ""
                    )
                    # Jeśli to lista (AI czasem zwraca listę), zamień na string
                    if isinstance(loc_val, list):
                        loc_val = ", ".join(map(str, loc_val))
                    new_row[loc_field] = str(loc_val)

                    # 4. Opis
                    new_row['opis_tekstowy'] = (
                        row.get('opis_tekstowy') or 
                        row.get('opis') or 
                        row.get('description') or 
                        row.get('opis wykonania/zalecenia') or
                        ""
                    )
                    
                    # Zachowaj ID jeśli jest (dla checkboxów)
                    if 'id' in row:
                        new_row['id'] = row['id']
                        
                    cleaned.append(new_row)
                return cleaned

            # Wypełnij gridy
            diagnozy = clean_data(result_json.get('diagnozy', []))
            procedury = clean_data(result_json.get('procedury', []))
            
            print(f"[UI] Loading {len(diagnozy)} diagnoses into grid (Spec: {spec_name})...", flush=True)

            # Aktualizuj dane i kolumny JEDNYM rzutem (unika race condition)
            if self.diagnosis_grid:
                self.diagnosis_grid.options['columnDefs'] = new_column_defs
                self.diagnosis_grid.options['rowData'] = diagnozy
                self.diagnosis_grid.update()
                # Wymuś załadowanie danych przez API (fix dla "No Rows To Show")
                self.diagnosis_grid.run_grid_method('setRowData', diagnozy)
                # Opóźnij selectAll, aby grid zdążył się przerysować
                ui.timer(0.1, lambda: self.diagnosis_grid.run_grid_method('selectAll'), once=True)

            if self.procedure_grid:
                self.procedure_grid.options['columnDefs'] = new_column_defs
                self.procedure_grid.options['rowData'] = procedury
                self.procedure_grid.update()
                # Wymuś załadowanie danych przez API
                self.procedure_grid.run_grid_method('setRowData', procedury)
                # Opóźnij selectAll
                ui.timer(0.1, lambda: self.procedure_grid.run_grid_method('selectAll'), once=True)

            # Status Update
            if self.record_status:
                self.record_status.text = "Opis wygenerowany!"
                self.record_status.classes(replace='text-green-600')

            # Store last result for saving
            self.last_generation_result = result_json
            self.last_model_used = used_model

            # Show save button
            if hasattr(self, 'save_visit_button') and self.save_visit_button:
                self.save_visit_button.set_visibility(True)

            # Info o fallbacku
            if "Fallback" in used_model:
                ui.notify(f"Użyto modelu zapasowego: {used_model}", type='warning', timeout=5000)

            print(f"[UI] Description generated successfully using {used_model}", flush=True)

        except ValueError as e:
            # Błędy logiczne (brak klucza, zły JSON)
            ui.notify(str(e), type='warning')
            if self.record_status:
                self.record_status.text = "Błąd danych"
                self.record_status.classes(replace='text-red-600')

        except Exception as e:
            # Błędy sieciowe / API
            error_msg = str(e)
            print(f"[UI] Generation error: {e}", flush=True)
            
            # Obsługa Rate Limit (429 / RESOURCE_EXHAUSTED)
            if "429" in error_msg or "rate_limit" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                # Sprawdzamy co mamy w configu zeby dac dobra rade
                gen_model = self.config.get("generation_model", "Auto")
                if gen_model == "Gemini":
                     msg = "Limit Gemini wyczerpany."
                elif gen_model == "Claude":
                     msg = "Limit Claude wyczerpany."
                else:
                     msg = "Wyczerpano limity obu modeli (Claude i Gemini)."

                ui.notify(msg, type='negative', close_button=True, timeout=0)
                
                if self.record_status:
                    self.record_status.text = "Błąd: Limit (429)"
                    self.record_status.classes(replace='text-red-600')
            else:
                ui.notify(f"Błąd generowania: {error_msg[:100]}", type='negative')
                if self.record_status:
                    self.record_status.text = "Błąd generowania"
                    self.record_status.classes(replace='text-red-600')

        finally:
            if self.generate_button:
                self.generate_button.props(remove='loading')

    async def _copy_results_json(self):
        """Kopiuje zaznaczone wyniki jako JSON do schowka."""
        if not hasattr(self, 'diagnosis_grid') or not hasattr(self, 'procedure_grid'):
            return

        # Pobierz tylko zaznaczone wiersze
        selected_diagnoses = await self.diagnosis_grid.get_selected_rows()
        selected_procedures = await self.procedure_grid.get_selected_rows()

        data = {
            "diagnozy": selected_diagnoses,
            "procedury": selected_procedures
        }

        self.copy_to_clipboard(json.dumps(data, indent=2, ensure_ascii=False), "Wybrane diagnozy i procedury")

    async def _open_save_visit_dialog(self):
        """Otwiera dialog zapisywania wizyty z zaznaczonymi elementami."""
        if not self.last_generation_result:
            ui.notify("Najpierw wygeneruj opis", type='warning')
            return

        transcript = self.transcript_area.value if self.transcript_area else ""

        # Pobierz tylko zaznaczone wiersze
        diagnoses = await self.diagnosis_grid.get_selected_rows() if self.diagnosis_grid else []
        procedures = await self.procedure_grid.get_selected_rows() if self.procedure_grid else []

        if not diagnoses and not procedures:
            ui.notify("Zaznacz przynajmniej jedną diagnozę lub procedurę", type='warning')
            return

        try:
            from app_ui.components.visit_save_dialog import open_save_visit_dialog
            open_save_visit_dialog(
                transcript=transcript,
                diagnoses=diagnoses,
                procedures=procedures,
                model_used=self.last_model_used
            )
        except ImportError as e:
            ui.notify(f"Moduł zapisywania niedostępny: {e}", type='negative')


    def _update_claude_status(self):
        """Aktualizuje status Claude w UI."""
        if not hasattr(self, 'claude_status_label'):
            return
            
        claude_token = load_claude_token()
        session_key = self.config.get("session_key")
        gemini_key = self.config.get("api_key")
        gen_model = self.config.get("generation_model", "Auto")

        # 1. Wymuszone Gemini
        if gen_model == "Gemini":
            self.claude_status_label.text = 'Claude: Wyłączony (wybrano Gemini)'
            self.claude_status_label.classes('text-gray-400 text-sm', remove='text-green-600 text-orange-600')
            return

        # 2. Session Key (Najwyższy priorytet)
        if session_key:
            self.claude_status_label.text = 'Claude: Session Key aktywny'
            self.claude_status_label.classes('text-green-600 text-sm', remove='text-orange-600 text-gray-400')
        
        # 3. OAuth Token
        elif claude_token:
            # W Auto: jeśli mamy Gemini Key i brak Session Key -> Ignorujemy OAuth
            if gen_model == "Auto" and gemini_key:
                self.claude_status_label.text = 'Claude: OAuth (nieużywany - woli Gemini)'
                self.claude_status_label.classes('text-gray-500 text-sm', remove='text-green-600 text-orange-600')
            else:
                self.claude_status_label.text = 'Claude: OAuth token dostępny'
                self.claude_status_label.classes('text-orange-600 text-sm', remove='text-green-600 text-gray-400')
        
        # 4. Brak dostępu
        else:
            self.claude_status_label.text = 'Claude: Niedostępny'
            self.claude_status_label.classes('text-gray-400 text-sm', remove='text-green-600 text-orange-600')

    def _save_session_from_dialog(self, session_key: str, dialog):
        """Zapisuje session key z dialogu."""
        if session_key and session_key.strip():
            self.config.set("session_key", session_key.strip())
            
            if hasattr(self, 'session_input'):
                self.session_input.value = session_key.strip()
            self._update_claude_status()
            ui.notify("Session key zapisany!", type='positive')
            dialog.close()
        else:
            ui.notify("Wpisz session key", type='warning')

    def _auto_get_key(self):
        """Uruchamia Edge z załadowanym rozszerzeniem (metoda --load-extension)."""
        with ui.dialog() as dialog, ui.card():
            ui.label('UWAGA: Ta operacja musi zamknąć przeglądarkę Edge!')
            ui.label('Zapisz swoją pracę w innych oknach Edge przed kontynuowaniem.')
            ui.label('Po kliknięciu "OK", Edge otworzy się na chwilę, pobierze klucz i prześle go do aplikacji.')
            
            def start_process():
                dialog.close()
                self._run_edge_with_extension()
            
            with ui.row().classes('w-full justify-end'):
                ui.button('Anuluj', on_click=dialog.close).props('flat')
                ui.button('OK, Zamknij Edge i Pobierz', on_click=start_process).props('color=red')
        
        dialog.open()

    def _run_edge_with_extension(self):
        """Uruchamia Edge z załadowanym rozszerzeniem używając BrowserService."""
        if not self.browser_service:
            ui.notify("Browser Service niedostępny", type='negative')
            return

        ui.notify("Restartuję Edge...", type='warning')
        
        extension_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "extension"))
        
        try:
            self.browser_service.launch_edge_with_extension(
                extension_path=extension_path,
                target_url="https://claude.ai",
                app_url="http://localhost:8089"
            )
            ui.notify("Otwarto Edge. Zaloguj się na Claude.ai.", type='info')
        except Exception as e:
            ui.notify(f"Błąd uruchamiania Edge: {e}", type='negative')

    def _open_gemini_studio(self):
        """Otwiera Google AI Studio w przeglądarce."""
        ui.notify("Otwieram Google AI Studio... Skopiuj API key i wklej tutaj.", type='info')
        import webbrowser
        webbrowser.open("https://aistudio.google.com/app/apikey")

    def save_settings(self):
        """Zapisuje ustawienia."""
        self.config.save()

        if self.transcriber_manager:
            self.transcriber_manager.set_gemini_api_key(self.config.get("api_key", ""))

        self._update_claude_status()
        ui.notify("Ustawienia zapisane!", type='positive')

    def copy_to_clipboard(self, text: str, label: str):
        """Kopiuje do schowka."""
        if text:
            ui.run_javascript(f'navigator.clipboard.writeText({json.dumps(text)})')
            ui.notify(f"Skopiowano: {label}", type='positive')
        else:
            ui.notify("Brak tekstu do skopiowania", type='warning')

    def _notify_client(self, client, message: str, type: Optional[str] = None, timeout: Optional[int] = None):
        """Bezpieczne notify w tle (bez slot context)."""
        try:
            options = {"message": str(message)}
            if type:
                options["type"] = type
            if timeout:
                options["timeout"] = timeout
            client.outbox.enqueue_message("notify", options, client.id)
        except Exception:
            pass

    def _check_session_key_update(self):
        """Sprawdza czy session key zmienił się w pliku config (np. przez rozszerzenie)."""
        try:
            # Wczytaj config z dysku bez zapisywania stanu obiektu
            disk_config = ConfigManager()
            disk_key = disk_config.get("session_key", "")
            
            # Pobierz aktualną wartość z pamięci (config obiektu)
            memory_key = self.config.get("session_key", "")
            
            # Synchronizuj tylko jeśli:
            # 1. Dysk ma nowy klucz (nie pusty)
            # 2. Klucz na dysku jest INNY niż w pamięci
            # To ignoruje przypadek gdy user celowo wyczyścił klucz w UI
            if disk_key and disk_key != memory_key:
                print("[UI] Wykryto nowy session key z pliku! Aktualizuję UI.", flush=True)
                
                # Aktualizuj config w pamięci
                self.config["session_key"] = disk_key
                
                # Aktualizuj UI
                if hasattr(self, 'session_input'):
                    self.session_input.value = disk_key
                    self.session_input.update() # Wymuś odświeżenie elementu
                
                # Aktualizuj status
                self._update_claude_status()
                
                # Powiadomienie
                ui.notify("Pobrano nowy klucz Claude!", type='positive')
                
        except Exception:
            pass

    # === MAIN UI ===

    def build_ui(self):
        """Buduje glowny interfejs używając komponentów."""
        print("[UI] build_ui() started", flush=True)

        # Dark mode state
        self.dark_mode = ui.dark_mode()

        # Timer to check transcription result from background thread
        self._transcription_result = None
        ui.timer(0.5, self.check_transcription_result)

        # Timer to refresh status during loading
        ui.timer(1.0, self._refresh_status_timer)
        
        # Timer to check for session key updates (auto-refresh from extension)
        ui.timer(2.0, self._check_session_key_update)

        # Header
        create_header(self)

        # Main content
        with ui.column().classes('w-full max-w-5xl mx-auto p-4 gap-4'):
            
            # Settings Section (Devices, Backend, Keys)
            create_settings_section(self)
            
            # Recording Section
            create_recording_section(self)

            # Sprawdź czy jest transkrypt z Live Interview (w storage użytkownika)
            live_transcript = app.storage.user.get('live_transcript', None)
            if live_transcript and self.transcript_area:
                self.transcript_area.value = live_transcript
                del app.storage.user['live_transcript']  # Wyczyść po użyciu
                ui.notify("Załadowano transkrypt z Live Interview!", type='positive')
                print(f"[UI] Loaded live transcript into main view", flush=True)

            # Results Section
            create_results_section(self)

        # Initial Refresh
        self.refresh_device_cards()
        self.refresh_model_cards()
        
        # === AUTO-LOAD MODEL ===
        self._update_status_ui()
        self._update_record_button()
        print("[UI] build_ui() DONE", flush=True)

        # Auto-load modelu dla backendów offline
        backend_type = self.config.get("transcriber_backend", "gemini_cloud")
        if backend_type != "gemini_cloud":
            # Delay auto-load slightly to let UI render
            ui.timer(0.1, lambda: asyncio.create_task(self._load_model_async()), once=True)


# === RUN ===

def main():
    # Setup safe exit
    def handle_sigint(signum, frame):
        print("\n[APP] Otrzymano sygnał przerwania. Zamykanie...", flush=True)
        import os
        import sys

        # Na Windows - natychmiastowe zamknięcie (Ctrl+C często nie działa z asyncio)
        if sys.platform == 'win32':
            print("[APP] Windows force exit.", flush=True)
            os._exit(0)

        # Próbujemy zamknąć ładnie
        try:
            if GLOBAL_TRANSCRIBER_MANAGER:
                pass
        except:
            pass
        finally:
            print("[APP] Force exit.", flush=True)
            os._exit(0)

    import signal
    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    # Windows: dodatkowy handler dla CTRL+C/CTRL+BREAK (czasem SIGINT nie dochodzi)
    def install_windows_ctrl_handler():
        if sys.platform != 'win32':
            return
        try:
            import os
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.windll.kernel32

            # Ensure we are attached to a console (needed when launched from shortcuts)
            if not kernel32.GetConsoleWindow():
                try:
                    kernel32.AttachConsole(-1)  # ATTACH_PARENT_PROCESS
                except Exception:
                    pass

            # Make sure Ctrl+C is processed by console input
            try:
                STD_INPUT_HANDLE = -10
                h = kernel32.GetStdHandle(STD_INPUT_HANDLE)
                mode = wintypes.DWORD()
                if h and kernel32.GetConsoleMode(h, ctypes.byref(mode)):
                    ENABLE_PROCESSED_INPUT = 0x0001
                    kernel32.SetConsoleMode(h, mode.value | ENABLE_PROCESSED_INPUT)
            except Exception:
                pass

            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
            def _handler(ctrl_type):
                print("\n[APP] Console event received. Exiting...", flush=True)
                os._exit(0)
                return True

            # Keep reference to avoid GC
            global _WIN_CTRL_HANDLER
            _WIN_CTRL_HANDLER = _handler
            ok = kernel32.SetConsoleCtrlHandler(_handler, True)
            print(f"[APP] Windows console handler installed (ok={bool(ok)})", flush=True)
        except Exception as e:
            print(f"[APP] Windows console handler install failed: {e}", flush=True)

    install_windows_ctrl_handler()

    # Fallback: allow quitting with 'Q' or Ctrl+C from console (when Ctrl+C event is not delivered)
    def start_console_quit_listener():
        if sys.platform != 'win32':
            return
        try:
            import msvcrt
            import ctypes
            from ctypes import wintypes
        except Exception:
            return

        def _listener():
            # Disable processed input so Ctrl+C is captured as '\x03'
            try:
                kernel32 = ctypes.windll.kernel32
                STD_INPUT_HANDLE = -10
                h = kernel32.GetStdHandle(STD_INPUT_HANDLE)
                mode = wintypes.DWORD()
                if h and kernel32.GetConsoleMode(h, ctypes.byref(mode)):
                    ENABLE_PROCESSED_INPUT = 0x0001
                    if mode.value & ENABLE_PROCESSED_INPUT:
                        kernel32.SetConsoleMode(h, mode.value & ~ENABLE_PROCESSED_INPUT)
                        print("[APP] Console raw mode enabled for Ctrl+C", flush=True)
            except Exception:
                pass

            print("[APP] Press Q or Ctrl+C to quit (fallback)", flush=True)
            while True:
                try:
                    if msvcrt.kbhit():
                        ch = msvcrt.getwch()
                        if ch in ('q', 'Q', '\x03'):
                            print("[APP] Quit requested", flush=True)
                            os._exit(0)
                    time.sleep(0.1)
                except Exception:
                    time.sleep(0.5)

        threading.Thread(target=_listener, daemon=True).start()

    start_console_quit_listener()

    def _setup_stdout_log():
        log_path = os.environ.get("WYWIAD_STDOUT_LOG")
        if not log_path:
            return
        try:
            if not os.path.isabs(log_path):
                log_path = os.path.join(os.path.dirname(__file__), log_path)
            log_dir = os.path.dirname(log_path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            log_file = open(log_path, "a", encoding="utf-8", buffering=1)

            class Tee:
                def __init__(self, *streams):
                    self._streams = [s for s in streams if s and hasattr(s, "write")]
                    self.encoding = getattr(log_file, "encoding", "utf-8")

                def write(self, data):
                    for s in self._streams:
                        try:
                            s.write(data)
                        except Exception:
                            pass
                    return len(data)

                def flush(self):
                    for s in self._streams:
                        try:
                            s.flush()
                        except Exception:
                            pass

                def isatty(self):
                    return False

                def reconfigure(self, **kwargs):
                    for s in self._streams:
                        if hasattr(s, "reconfigure"):
                            try:
                                s.reconfigure(**kwargs)
                            except Exception:
                                pass

            sys.stdout = Tee(sys.stdout, log_file)
            sys.stderr = Tee(sys.stderr, log_file)
        except Exception:
            pass

    _setup_stdout_log()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(line_buffering=True)

    def _setup_favicon():
        icon_tag = "v3"
        icon_data_uri = ""
        try:
            from branding import BRAND_ICON_TAG, BRAND_ICON_DATA_URI
            if BRAND_ICON_TAG:
                icon_tag = BRAND_ICON_TAG
            icon_data_uri = BRAND_ICON_DATA_URI or ""
        except Exception:
            pass
        if icon_data_uri:
            return icon_data_uri
        ext_dir = Path(__file__).parent / "extension"
        if not ext_dir.is_dir():
            return None
        icon_ico = ext_dir / f"icon_{icon_tag}.ico"
        icon_png = ext_dir / f"icon_{icon_tag}_32.png"
        if icon_ico.is_file():
            return icon_ico
        if icon_png.is_file():
            return icon_png
        return None

    favicon_value = _setup_favicon()

    log("[STARTUP] Starting app...")

    try:
        build_info_path = Path(__file__).parent / "build_info.json"
        if build_info_path.exists():
            build_info = json.loads(build_info_path.read_text(encoding="utf-8"))
            commit = build_info.get("commit", "unknown")
            downloaded_at = build_info.get("downloaded_at", "")
            source = build_info.get("source", "")
            log(f"[VERSION] commit={commit} downloaded_at={downloaded_at} source={source}")
        else:
            log("[VERSION] build_info.json not found")
    except Exception as e:
        log(f"[VERSION] Error reading build info: {e}")

    # === DATABASE MIGRATIONS ===
    try:
        from core.migrations import run_migrations
        applied = run_migrations()
        if applied:
            print(f"[STARTUP] Applied {len(applied)} migration(s)", flush=True)
    except Exception as e:
        print(f"[STARTUP] Migration error (non-fatal): {e}", flush=True)

    # === GLOBAL INITIALIZATION ===
    def init_global_state():
        """Inicjalizuje globalny stan (np. wczytuje modele)."""
        # ... (kod init_global_state) ...

    # Force signal handler on startup
    def register_signal_handlers():
        import signal
        import os
        def force_exit(signum, frame):
            print("\n[APP] Forced Exit via Signal", flush=True)
            os._exit(0)
        
        signal.signal(signal.SIGINT, force_exit)
        signal.signal(signal.SIGTERM, force_exit)
        print("[APP] Signal handlers registered", flush=True)

    app.on_startup(register_signal_handlers)

    # Run initialization in background to not block startup
    threading.Thread(target=init_global_state, daemon=True).start()

    @ui.page('/')
    def index():
        """Strona główna."""
        app_instance = WywiadApp()
        app_instance.build_ui()

    @ui.page('/live')
    def live_page():
        """Strona trybu Live Interview."""
        app_instance = WywiadApp()
        # W przyszłości można tu przekazać istniejący stan, jeśli chcemy
        view = LiveInterviewView(app_instance)
        view.create_ui()

    @ui.page('/history')
    def history_page():
        """Strona historii wizyt."""
        from app_ui.views.history_view import create_history_view
        from app_ui.components.header import create_header
        from app_ui.components.visit_save_dialog import open_save_visit_dialog

        # Minimalny app context dla headera
        class MinimalApp:
            def __init__(self):
                self.dark_mode = ui.dark_mode()
                self.status_indicator = None
                self.status_label = None
                self.cancel_button = None

            def _on_cancel_click(self):
                pass

        mini_app = MinimalApp()
        create_header(mini_app)

        with ui.column().classes('w-full max-w-6xl mx-auto p-4'):
            view = None

            def _edit_visit(visit):
                diagnoses = [d.to_dict() for d in visit.diagnoses]
                procedures = [p.to_dict() for p in visit.procedures]
                open_save_visit_dialog(
                    transcript=visit.transcript,
                    diagnoses=diagnoses,
                    procedures=procedures,
                    model_used=visit.model_used,
                    existing_visit=visit,
                    on_save=lambda v: (
                        ui.notify(f"Wizyta zaktualizowana: {v.id[:8]}...", type='positive'),
                        view.refresh_data() if view else None
                    )
                )

            view = create_history_view(on_edit_visit=_edit_visit)

    # API endpoint dla rozszerzenia przeglądarki
    from fastapi import Request
    from fastapi.responses import JSONResponse
    from fastapi.middleware.cors import CORSMiddleware

    # Dodaj CORS dla rozszerzenia
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["POST"],
        allow_headers=["*"],
    )

    @app.post('/api/session-key')
    async def receive_session_key(request: Request):
        """Odbiera session key z rozszerzenia przeglądarki."""
        try:
            data = await request.json()
            session_key = data.get('sessionKey')
            if session_key:
                config_mgr = ConfigManager()
                config_mgr.set('session_key', session_key)
                print(f"[API] Session key otrzymany z rozszerzenia!", flush=True)
                return JSONResponse({'success': True, 'message': 'Session key zapisany'})
            return JSONResponse({'success': False, 'error': 'Brak sessionKey'}, status_code=400)
        except Exception as e:
            return JSONResponse({'success': False, 'error': str(e)}, status_code=500)

    @app.get('/api/download-installer')
    async def download_installer(request: Request):
        """Generuje i zwraca instalator rozszerzenia dla danej przeglądarki."""
        from fastapi.responses import Response

        browser = request.query_params.get('browser', 'edge')

        # Ścieżka do folderu rozszerzenia
        extension_path = os.path.join(os.path.dirname(__file__), "extension")

        # Konfiguracja dla różnych przeglądarek
        browser_config = {
            'edge': {
                'exe': 'msedge',
                'extensions_url': 'edge://extensions/',
                'name': 'Microsoft Edge'
            },
            'chrome': {
                'exe': 'chrome',
                'extensions_url': 'chrome://extensions/',
                'name': 'Google Chrome'
            },
            'firefox': {
                'exe': 'firefox',
                'extensions_url': 'about:addons',
                'name': 'Firefox'
            }
        }

        config = browser_config.get(browser, browser_config['edge'])

        # Generuj .bat (bez polskich znakow i Unicode - cmd.exe ich nie obsluguje)
        bat_content = f'''@echo off
title Wizyta Extension Installer

echo.
echo ============================================================
echo   WIZYTA EXTENSION INSTALLER for {config['name']}
echo ============================================================
echo.
echo   Opening:
echo   1. Browser extensions page
echo   2. Extension folder
echo.
echo   Your task:
echo   [1] Enable "Developer mode" (toggle switch)
echo   [2] Click "Load unpacked"
echo   [3] Select the folder that opens
echo.
echo ============================================================
echo.
pause

start "" "{config['exe']}" "{config['extensions_url']}"
timeout /t 2 /nobreak >nul
explorer "{extension_path}"

echo.
echo ============================================================
echo   DONE! Now in browser:
echo   [1] Enable "Developer mode"
echo   [2] Click "Load unpacked"
echo   [3] Select the open folder
echo ============================================================
echo.
echo   After installing, click extension icon (puzzle piece)
echo   and click "Send key to app"
echo.
pause
'''

        return Response(
            content=bat_content.encode('utf-8'),
            media_type='application/x-bat',
            headers={
                'Content-Disposition': f'attachment; filename="Instaluj_Wywiad_Plus_{browser}.bat"'
            }
        )

    def cleanup():
        print("[APP] Shutting down...", flush=True)
        # Force kill any child processes if needed
        try:
            import psutil
        except ImportError:
            print("[APP] psutil missing; skipping child process cleanup.", flush=True)
            return
        try:
            parent = psutil.Process(os.getpid())
            children = parent.children(recursive=True)
            for child in children:
                child.kill()
        except:
            pass
        print("[APP] Cleanup done.", flush=True)

    app.on_shutdown(cleanup)

    def _find_available_port(start=8089, end=8100):
        import socket
        for port in range(start, end + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(("0.0.0.0", port))
                    return port
                except OSError:
                    continue
        return start

    def _is_port_open(port: int) -> bool:
        import socket
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            return False

    auto_open = os.environ.get("WYWIAD_AUTO_OPEN") == "1"
    scheme = "http"

    preferred_port = 8089
    allow_multi = os.environ.get("WYWIAD_ALLOW_MULTI") == "1"

    if _is_port_open(preferred_port) and not allow_multi:
        print(f"[APP] Port {preferred_port} already in use - using existing instance.", flush=True)

        if os.environ.get("WYWIAD_OPEN_LANDING") == "1" or auto_open:
            def _open_pages_existing():
                try:
                    import webbrowser
                    time.sleep(0.5)
                    if os.environ.get("WYWIAD_OPEN_LANDING") == "1":
                        webbrowser.open("https://guziczak.github.io/wywiady/", new=1, autoraise=True)
                        time.sleep(0.5)
                    if auto_open:
                        webbrowser.open(f"{scheme}://127.0.0.1:{preferred_port}", new=1, autoraise=True)
                except Exception:
                    pass
            threading.Thread(target=_open_pages_existing, daemon=True).start()
        return

    port = _find_available_port(preferred_port, 8100)
    if port != preferred_port:
        print(f"[APP] Port {preferred_port} in use, switching to {port}.", flush=True)

    if os.environ.get("WYWIAD_OPEN_LANDING") == "1" or auto_open:
        def _open_pages():
            try:
                import webbrowser
                time.sleep(1.0)
                if os.environ.get("WYWIAD_OPEN_LANDING") == "1":
                    webbrowser.open("https://guziczak.github.io/wywiady/", new=1, autoraise=True)
                    time.sleep(0.5)
                if auto_open:
                    webbrowser.open(f"{scheme}://127.0.0.1:{port}", new=1, autoraise=True)
            except Exception:
                pass
        threading.Thread(target=_open_pages, daemon=True).start()

    # Wycisz sporadyczne WinError 10054 z asyncio na Windowsie
    def _silent_exception_handler(loop, context):
        exc = context.get("exception")
        if isinstance(exc, ConnectionResetError) and getattr(exc, "winerror", None) == 10054:
            return
        loop.default_exception_handler(context)

    try:
        loop = asyncio.get_event_loop()
        loop.set_exception_handler(_silent_exception_handler)
    except Exception:
        pass

    # Serve static assets (JS/CSS)
    app.add_static_files('/assets', 'assets')

    ui.run(
        title='Wizyta v2',
        port=port,
        reload=False,
        show=False,
        native=False,
        binding_refresh_interval=0.1,
        reconnect_timeout=120.0,  # Dlugi timeout dla ladowania modeli
        storage_secret='wywiad_plus_secret_key',  # Wymagane dla reconnect
        favicon=favicon_value,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
