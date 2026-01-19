"""
Moduł transkrypcji audio z obsługą wielu backendów.
Wspiera: Gemini Cloud, faster-whisper, openai-whisper
"""

import os

# Wyłącz telemetrię OpenVINO (może powodować konflikty z huggingface_hub)
os.environ['OPENVINO_TELEMETRY_ENABLE'] = '0'
import shutil
import subprocess
import sys
import threading
import zipfile
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional, Tuple, List, Dict
from dataclasses import dataclass
from enum import Enum

# Ścieżka do modeli i narzędzi
MODELS_DIR = Path(__file__).parent.parent / "models"
TOOLS_DIR = Path(__file__).parent.parent / "tools"


# ========== FFMPEG MANAGER ==========

class FFmpegManager:
    """Zarządza instalacją i dostępnością ffmpeg."""

    FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

    @staticmethod
    def is_installed() -> bool:
        """Sprawdza czy ffmpeg jest dostępny."""
        # Sprawdź w PATH
        if shutil.which("ffmpeg"):
            return True
        # Sprawdź w lokalnym folderze tools
        local_ffmpeg = TOOLS_DIR / "ffmpeg" / "bin" / "ffmpeg.exe"
        if local_ffmpeg.exists():
            # Dodaj do PATH dla tego procesu
            FFmpegManager._add_to_path()
            return True
        return False

    @staticmethod
    def _add_to_path():
        """Dodaje lokalny ffmpeg do PATH."""
        ffmpeg_bin = TOOLS_DIR / "ffmpeg" / "bin"
        if ffmpeg_bin.exists():
            current_path = os.environ.get("PATH", "")
            if str(ffmpeg_bin) not in current_path:
                os.environ["PATH"] = str(ffmpeg_bin) + os.pathsep + current_path

    @staticmethod
    def get_install_status() -> Tuple[bool, str]:
        """Zwraca status instalacji ffmpeg."""
        if shutil.which("ffmpeg"):
            return True, "ffmpeg zainstalowany (systemowy)"
        local_ffmpeg = TOOLS_DIR / "ffmpeg" / "bin" / "ffmpeg.exe"
        if local_ffmpeg.exists():
            return True, "ffmpeg zainstalowany (lokalny)"
        return False, "ffmpeg nie zainstalowany"

    @staticmethod
    def install(progress_callback: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """Instaluje ffmpeg. Najpierw próbuje winget, potem pobiera binaria."""

        # Metoda 1: Spróbuj winget (Windows 10/11)
        if progress_callback:
            progress_callback("Sprawdzam winget...")

        try:
            result = subprocess.run(
                ["winget", "--version"],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            if result.returncode == 0:
                if progress_callback:
                    progress_callback("Instaluję ffmpeg przez winget...")

                subprocess.run(
                    ["winget", "install", "ffmpeg", "--accept-package-agreements", "--accept-source-agreements", "-h"],
                    capture_output=True,
                    timeout=600,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    encoding="utf-8",
                    errors="ignore"
                )

                # Sprawdź czy ffmpeg jest teraz dostępny w PATH
                if shutil.which("ffmpeg"):
                    return True, "ffmpeg zainstalowany przez winget"
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        # Metoda 2: Pobierz binaria
        if progress_callback:
            progress_callback("Pobieram ffmpeg (~100MB)...")

        try:
            TOOLS_DIR.mkdir(parents=True, exist_ok=True)
            zip_path = TOOLS_DIR / "ffmpeg.zip"

            # Pobierz z progress
            def download_progress(block_num, block_size, total_size):
                if progress_callback and total_size > 0:
                    percent = int(block_num * block_size * 100 / total_size)
                    progress_callback(f"Pobieranie ffmpeg: {min(percent, 100)}%")

            urllib.request.urlretrieve(FFmpegManager.FFMPEG_URL, zip_path, download_progress)

            if progress_callback:
                progress_callback("Rozpakowuję ffmpeg...")

            # Rozpakuj
            with zipfile.ZipFile(zip_path, 'r') as zf:
                namelist = zf.namelist()
                for member in namelist:
                    if '/bin/' in member and not member.endswith('/'):
                        filename = Path(member).name
                        if filename:
                            target_path = TOOLS_DIR / "ffmpeg" / "bin" / filename
                            target_path.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(member) as src, open(target_path, 'wb') as dst:
                                dst.write(src.read())

            # Usuń zip
            zip_path.unlink()

            # Sprawdź czy ffmpeg istnieje
            ffmpeg_exe = TOOLS_DIR / "ffmpeg" / "bin" / "ffmpeg.exe"
            if ffmpeg_exe.exists():
                FFmpegManager._add_to_path()
                if progress_callback:
                    progress_callback("ffmpeg zainstalowany!")
                return True, "ffmpeg pobrany i zainstalowany lokalnie"
            else:
                return False, "Błąd: ffmpeg.exe nie został wypakowany"

        except Exception as e:
            return False, f"Błąd instalacji ffmpeg: {str(e)}"

    @staticmethod
    def ensure_available(progress_callback: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """Upewnia się że ffmpeg jest dostępny. Instaluje jeśli brakuje."""
        if FFmpegManager.is_installed():
            return True, "ffmpeg gotowy"
        return FFmpegManager.install(progress_callback)


class TranscriberType(Enum):
    GEMINI_CLOUD = "gemini_cloud"
    FASTER_WHISPER = "faster_whisper"
    OPENAI_WHISPER = "openai_whisper"
    OPENVINO_WHISPER = "openvino_whisper"


@dataclass
class TranscriberInfo:
    """Informacje o backendzie transkrypcji."""
    type: TranscriberType
    name: str
    description: str
    requires_download: bool
    model_sizes: List[str]
    is_available: bool
    is_installed: bool  # Czy biblioteka jest zainstalowana
    pip_package: Optional[str] = None  # Nazwa pakietu pip do instalacji
    unavailable_reason: Optional[str] = None
    requires_ffmpeg: bool = False  # Czy wymaga ffmpeg
    ffmpeg_installed: bool = True  # Czy ffmpeg jest zainstalowany


@dataclass
class ModelInfo:
    """Informacje o modelu."""
    name: str
    size_mb: int
    description: str
    is_downloaded: bool


class TranscriberBackend(ABC):
    """Abstrakcyjna klasa bazowa dla backendów transkrypcji."""

    @abstractmethod
    def transcribe(self, audio_path: str, language: str = "pl") -> str:
        """Transkrybuje plik audio na tekst."""
        pass

    @abstractmethod
    def is_available(self) -> Tuple[bool, Optional[str]]:
        """Sprawdza czy backend jest dostępny. Zwraca (dostępny, powód_niedostępności)."""
        pass

    @abstractmethod
    def get_models(self) -> List[ModelInfo]:
        """Zwraca listę dostępnych modeli."""
        pass

    @abstractmethod
    def download_model(self, model_name: str, progress_callback: Optional[Callable[[float], None]] = None) -> bool:
        """Pobiera model. Callback otrzymuje postęp 0.0-1.0."""
        pass

    @abstractmethod
    def get_current_model(self) -> Optional[str]:
        """Zwraca nazwę aktualnie używanego modelu."""
        pass

    def preload(self) -> bool:
        """Preloaduje model w tle. Zwraca True jeśli sukces."""
        return True  # Domyślnie nic nie robi

    def is_model_loaded(self) -> bool:
        """Sprawdza czy model jest załadowany."""
        return True  # Domyślnie zawsze True

    @abstractmethod
    def set_model(self, model_name: str) -> bool:
        """Ustawia model do użycia."""
        pass

    def delete_model(self, model_name: str) -> bool:
        """Usuwa pobrany model. Zwraca True jeśli sukces."""
        return False  # Domyślnie nie obsługuje usuwania


# ========== GEMINI CLOUD ==========

class GeminiCloudTranscriber(TranscriberBackend):
    """Transkrypcja przez Google Gemini API (cloud)."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._client = None
        self._genai = None
        self._types = None

    def _ensure_client(self):
        if self._client is None:
            try:
                from google import genai
                from google.genai import types
                self._genai = genai
                self._types = types
                self._client = genai.Client(api_key=self.api_key)
            except ImportError:
                raise RuntimeError("Brak biblioteki google-genai. Zainstaluj: pip install google-genai")

    def set_api_key(self, api_key: str):
        self.api_key = api_key
        self._client = None  # Reset client

    def transcribe(self, audio_path: str, language: str = "pl") -> str:
        if not self.api_key:
            raise ValueError("Brak API key dla Gemini!")

        self._ensure_client()

        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        response = self._client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                f"Przetranscybuj poniższe nagranie audio na tekst (język: {language}). "
                "Zwróć tylko transkrypcję, bez żadnych dodatkowych komentarzy.",
                self._types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")
            ]
        )
        return response.text.strip()

    def is_available(self) -> Tuple[bool, Optional[str]]:
        try:
            from google import genai
            if not self.api_key:
                return False, "Brak API key"
            return True, None
        except ImportError:
            return False, "Brak biblioteki google-genai"

    def get_models(self) -> List[ModelInfo]:
        return [ModelInfo("gemini-2.0-flash", 0, "Cloud API - nie wymaga pobierania", True)]

    def download_model(self, model_name: str, progress_callback: Optional[Callable[[float], None]] = None) -> bool:
        # Cloud - nic do pobierania
        if progress_callback:
            progress_callback(1.0)
        return True

    def get_current_model(self) -> Optional[str]:
        return "gemini-2.0-flash"

    def set_model(self, model_name: str) -> bool:
        return True  # Tylko jeden model


# ========== FASTER-WHISPER ==========

class FasterWhisperTranscriber(TranscriberBackend):
    """Transkrypcja przez faster-whisper (offline, CTranslate2)."""

    MODELS = {
        "tiny": {"size_mb": 75, "desc": "Najszybszy, najmniej dokładny"},
        "base": {"size_mb": 145, "desc": "Szybki, podstawowa jakość"},
        "small": {"size_mb": 465, "desc": "Dobry balans jakość/szybkość"},
        "medium": {"size_mb": 1460, "desc": "Wysoka jakość, wolniejszy"},
        "large-v3": {"size_mb": 2950, "desc": "Najlepsza jakość, wymaga GPU"},
    }

    def __init__(self):
        self._model = None
        self._model_name = "small"
        self._whisper_module = None
        self._ffmpeg_checked = False

    def _get_model_path(self, model_name: str) -> Path:
        """Zwraca ścieżkę do modelu (folder HuggingFace cache)."""
        # faster-whisper używa nazw HuggingFace: models--Systran--faster-whisper-{name}
        return MODELS_DIR / "faster-whisper" / f"models--Systran--faster-whisper-{model_name}"

    def _ensure_ffmpeg(self):
        """Sprawdza i instaluje ffmpeg jeśli potrzeba."""
        if self._ffmpeg_checked:
            return
        if not FFmpegManager.is_installed():
            success, msg = FFmpegManager.install()
            if not success:
                raise RuntimeError(f"Wymagany ffmpeg nie jest zainstalowany i nie udało się go pobrać: {msg}")
        self._ffmpeg_checked = True

    def _ensure_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
                self._whisper_module = WhisperModel

                # Użyj lokalnego cache jeśli istnieje
                download_root = MODELS_DIR / "faster-whisper"
                download_root.mkdir(parents=True, exist_ok=True)

                self._model = WhisperModel(
                    self._model_name,
                    device="cpu",
                    compute_type="int8",
                    download_root=str(download_root)
                )
            except ImportError:
                raise RuntimeError("Brak biblioteki faster-whisper. Zainstaluj: pip install faster-whisper")

    def transcribe(self, audio_path: str, language: str = "pl") -> str:
        # Upewnij się że ffmpeg jest dostępny
        self._ensure_ffmpeg()
        self._ensure_model()

        segments, info = self._model.transcribe(audio_path, language=language, beam_size=5)

        text_parts = []
        for segment in segments:
            text_parts.append(segment.text)

        return " ".join(text_parts).strip()

    def is_available(self) -> Tuple[bool, Optional[str]]:
        try:
            from faster_whisper import WhisperModel
            return True, None
        except ImportError:
            return False, "Zainstaluj: pip install faster-whisper"

    def get_models(self) -> List[ModelInfo]:
        models = []
        for name, info in self.MODELS.items():
            model_path = self._get_model_path(name)
            is_downloaded = model_path.exists()
            models.append(ModelInfo(name, info["size_mb"], info["desc"], is_downloaded))
        return models

    def download_model(self, model_name: str, progress_callback: Optional[Callable[[float], None]] = None) -> bool:
        if model_name not in self.MODELS:
            return False

        try:
            from huggingface_hub import snapshot_download
            from tqdm import tqdm as base_tqdm

            download_root = MODELS_DIR / "faster-whisper"
            download_root.mkdir(parents=True, exist_ok=True)

            # Track progress - śledź sumę wszystkich bajtów
            progress_state = {
                'bytes_bars': {},  # id(bar) -> {'current': n, 'total': t}
                'last_pct': 0,
                'last_update': 0
            }

            class ProgressTqdm(base_tqdm):
                def __init__(self, *args, **kwargs):
                    # Filtruj nieznane argumenty (np. 'name' z nowych wersji huggingface_hub)
                    kwargs.pop('name', None)
                    super().__init__(*args, **kwargs)
                    # Zarejestruj każdy pasek (total może być None na początku)
                    progress_state['bytes_bars'][id(self)] = {
                        'current': 0,
                        'total': self.total or 0
                    }

                def update(self, n=1):
                    super().update(n)
                    bar_id = id(self)
                    if bar_id in progress_state['bytes_bars']:
                        # Aktualizuj current i total (total może się zmienić)
                        progress_state['bytes_bars'][bar_id]['current'] = self.n or 0
                        if self.total:
                            progress_state['bytes_bars'][bar_id]['total'] = self.total

                        # Oblicz łączny progress (tylko paski z known total > 1KB)
                        bars_with_total = [
                            b for b in progress_state['bytes_bars'].values()
                            if b['total'] > 1000
                        ]

                        if bars_with_total:
                            total_bytes = sum(b['total'] for b in bars_with_total)
                            current_bytes = sum(b['current'] for b in bars_with_total)

                            if total_bytes > 0 and progress_callback:
                                pct = min(1.0, current_bytes / total_bytes)
                                # Aktualizuj co 1%
                                if pct - progress_state['last_pct'] >= 0.01 or pct >= 0.99:
                                    progress_state['last_pct'] = pct
                                    progress_callback(pct)

                def close(self):
                    bar_id = id(self)
                    if bar_id in progress_state['bytes_bars']:
                        del progress_state['bytes_bars'][bar_id]
                    super().close()

            if progress_callback:
                progress_callback(0.0)

            # Download model directly from HuggingFace with progress
            repo_id = f"Systran/faster-whisper-{model_name}"
            snapshot_download(
                repo_id=repo_id,
                local_dir=str(download_root / f"models--Systran--faster-whisper-{model_name}" / "snapshots" / "main"),
                tqdm_class=ProgressTqdm if progress_callback else None,
            )

            if progress_callback:
                progress_callback(1.0)

            return True
        except Exception as e:
            print(f"Błąd pobierania modelu: {e}")
            return False

    def get_current_model(self) -> Optional[str]:
        return self._model_name

    def set_model(self, model_name: str) -> bool:
        if model_name not in self.MODELS:
            return False
        self._model_name = model_name
        self._model = None  # Reset - załaduj przy następnym użyciu
        return True

    def delete_model(self, model_name: str) -> bool:
        """Usuwa pobrany model faster-whisper."""
        if model_name not in self.MODELS:
            return False

        # Nie można usunąć aktywnego modelu
        if model_name == self._model_name:
            return False

        model_path = self._get_model_path(model_name)
        if not model_path.exists():
            return False

        try:
            shutil.rmtree(model_path)
            print(f"[FasterWhisper] Model {model_name} usunięty", flush=True)
            return True
        except Exception as e:
            print(f"[FasterWhisper] Błąd usuwania modelu: {e}", flush=True)
            return False


# ========== OPENAI-WHISPER ==========

class OpenAIWhisperTranscriber(TranscriberBackend):
    """Transkrypcja przez openai-whisper (offline, oryginalna implementacja)."""

    MODELS = {
        "tiny": {"size_mb": 75, "desc": "Najszybszy, najmniej dokładny"},
        "base": {"size_mb": 145, "desc": "Szybki, podstawowa jakość"},
        "small": {"size_mb": 465, "desc": "Dobry balans jakość/szybkość"},
        "medium": {"size_mb": 1460, "desc": "Wysoka jakość, wolniejszy"},
        "large": {"size_mb": 2950, "desc": "Najlepsza jakość, wymaga GPU"},
    }

    def __init__(self):
        self._model = None
        self._model_name = "small"
        self._ffmpeg_checked = False

    def _ensure_ffmpeg(self):
        """Sprawdza i instaluje ffmpeg jeśli potrzeba."""
        if self._ffmpeg_checked:
            return
        if not FFmpegManager.is_installed():
            success, msg = FFmpegManager.install()
            if not success:
                raise RuntimeError(f"Wymagany ffmpeg nie jest zainstalowany i nie udało się go pobrać: {msg}")
        self._ffmpeg_checked = True

    def _ensure_model(self):
        if self._model is None:
            try:
                import whisper
                self._model = whisper.load_model(self._model_name)
            except ImportError:
                raise RuntimeError("Brak biblioteki openai-whisper. Zainstaluj: pip install openai-whisper")

    def transcribe(self, audio_path: str, language: str = "pl") -> str:
        # Upewnij się że ffmpeg jest dostępny
        self._ensure_ffmpeg()
        self._ensure_model()

        result = self._model.transcribe(audio_path, language=language)
        return result["text"].strip()

    def is_available(self) -> Tuple[bool, Optional[str]]:
        try:
            import whisper
            return True, None
        except ImportError:
            return False, "Zainstaluj: pip install openai-whisper"

    def get_models(self) -> List[ModelInfo]:
        models = []
        cache_dir = Path.home() / ".cache" / "whisper"
        for name, info in self.MODELS.items():
            # openai-whisper przechowuje modele w ~/.cache/whisper
            # Model "large" może być zapisany jako large.pt lub large-v3.pt
            cache_path = cache_dir / f"{name}.pt"
            alt_cache_path = cache_dir / f"{name}-v3.pt"  # dla large-v3
            is_downloaded = cache_path.exists() or alt_cache_path.exists()
            models.append(ModelInfo(name, info["size_mb"], info["desc"], is_downloaded))
        return models

    def download_model(self, model_name: str, progress_callback: Optional[Callable[[float], None]] = None) -> bool:
        if model_name not in self.MODELS:
            return False

        try:
            import whisper

            if progress_callback:
                progress_callback(0.1)

            # whisper.load_model pobiera automatycznie
            _ = whisper.load_model(model_name)

            if progress_callback:
                progress_callback(1.0)

            return True
        except Exception as e:
            print(f"Błąd pobierania modelu: {e}")
            return False

    def get_current_model(self) -> Optional[str]:
        return self._model_name

    def set_model(self, model_name: str) -> bool:
        if model_name not in self.MODELS:
            return False
        self._model_name = model_name
        self._model = None
        return True


# ========== OPENVINO-WHISPER ==========

class OpenVINOWhisperTranscriber(TranscriberBackend):
    """Transkrypcja przez OpenVINO z obsługą Intel NPU/GPU."""

    MODELS = {
        "tiny": {"size_mb": 150, "desc": "Najszybszy, najmniej dokładny"},
        "base": {"size_mb": 290, "desc": "Szybki, podstawowa jakość"},
        "small": {"size_mb": 970, "desc": "Dobry balans jakość/szybkość"},
        "medium": {"size_mb": 1500, "desc": "Wysoka jakość, INT8"},
        "large-v3": {"size_mb": 3100, "desc": "Najlepsza jakość, INT8"},
    }

    # Mapowanie nazw modeli na HuggingFace
    HF_MODELS = {
        "tiny": "OpenVINO/whisper-tiny-fp16-ov",
        "base": "OpenVINO/whisper-base-fp16-ov",
        "small": "OpenVINO/whisper-small-fp16-ov",
        "medium": "OpenVINO/whisper-medium-int8-ov",
        "large-v3": "OpenVINO/whisper-large-v3-int8-ov",
    }

    def __init__(self):
        self._model = None
        self._model_name = "small"
        self._device = None
        self._available_devices = []
        self._ffmpeg_checked = False
        self._lock = threading.Lock()

    def _get_model_path(self, model_name: str) -> Path:
        """Zwraca ścieżkę do modelu OpenVINO."""
        # Użyj innego folderu dla int8 aby uniknąć konfliktów z fp16
        suffix = "int8" if model_name in ["medium", "large-v3"] else "fp16"
        return MODELS_DIR / "openvino-whisper" / f"whisper-{model_name}-{suffix}-ov"

    def _detect_devices(self) -> List[str]:
        """Wykrywa dostępne urządzenia OpenVINO."""
        if self._available_devices:
            return self._available_devices

        try:
            from openvino import Core
            core = Core()
            self._available_devices = core.available_devices
            return self._available_devices
        except ImportError:
            return []
        except Exception:
            return ["CPU"]

    def _get_best_device(self) -> str:
        """Zwraca najlepsze dostępne urządzenie (NPU > GPU > CPU)."""
        # Sprawdź czy jest wymuszone urządzenie w ustawieniach
        if hasattr(self, '_forced_device') and self._forced_device:
            return self._forced_device
        devices = self._detect_devices()
        if "NPU" in devices:
            return "NPU"
        elif "GPU" in devices:
            return "GPU"
        return "CPU"

    def set_device(self, device: str):
        """Wymusza użycie konkretnego urządzenia."""
        with self._lock:
            # Jeśli urządzenie jest to samo, nie resetuj modelu
            if hasattr(self, '_forced_device') and self._forced_device == device:
                return
            
            self._forced_device = device
            self._model = None  # Reset modelu
            self._device = None # Reset urządzenia

    def get_detected_device(self) -> str:
        """Zwraca wykryte urządzenie do wyświetlenia w UI."""
        return self._get_best_device()

    def _ensure_ffmpeg(self):
        """Sprawdza i instaluje ffmpeg jeśli potrzeba."""
        if self._ffmpeg_checked:
            return
        if not FFmpegManager.is_installed():
            success, msg = FFmpegManager.install()
            if not success:
                raise RuntimeError(f"Wymagany ffmpeg nie jest zainstalowany: {msg}")
        self._ffmpeg_checked = True

    def _ensure_model(self):
        """Ładuje model OpenVINO."""
        with self._lock:
            if self._model is not None:
                print("[OpenVINO] Model already loaded", flush=True)
                return

            print("[OpenVINO] Loading model...", flush=True)

            try:
                import openvino_genai as ov_genai
            except ImportError:
                raise RuntimeError("Brak biblioteki openvino-genai. Zainstaluj: pip install openvino openvino-genai")

            model_path = self._get_model_path(self._model_name)
            print(f"[OpenVINO] Model path: {model_path}", flush=True)

            if not model_path.exists():
                raise RuntimeError(f"Model '{self._model_name}' nie jest pobrany. Kliknij 'Pobierz model'.")

            device = self._get_best_device()
            self._device = device
            print(f"[OpenVINO] Using device: {device}", flush=True)
            print(f"[OpenVINO] Creating WhisperPipeline... (this may take 1-2 minutes for large models)", flush=True)

            try:
                self._model = ov_genai.WhisperPipeline(str(model_path), device)
                print("[OpenVINO] Model loaded successfully!", flush=True)
            except Exception as e:
                error_msg = str(e)
                print(f"[OpenVINO] Error loading model: {error_msg}", flush=True)
                if "weights" in error_msg.lower() or "xml" in error_msg.lower():
                    print(f"[OpenVINO] Detected corrupt model. Removing {model_path}...", flush=True)
                    try:
                        shutil.rmtree(model_path)
                    except Exception as del_e:
                        print(f"[OpenVINO] Could not delete corrupt model: {del_e}", flush=True)
                    self._model = None
                    raise RuntimeError(f"Model uszkodzony i został usunięty. Kliknij 'Pobierz' ponownie. (Błąd: {error_msg})")
                raise

    def transcribe(self, audio_path: str, language: str = "pl") -> str:
        print(f"[OpenVINO] transcribe() called: {audio_path}", flush=True)
        self._ensure_ffmpeg()
        print("[OpenVINO] ffmpeg OK", flush=True)
        self._ensure_model()
        print("[OpenVINO] model OK", flush=True)

        try:
            import librosa
        except ImportError:
            raise RuntimeError("Brak biblioteki librosa. Zainstaluj: pip install librosa")

        # Wczytaj audio
        print("[OpenVINO] Loading audio with librosa...", flush=True)
        raw_speech, _ = librosa.load(audio_path, sr=16000)
        return self.transcribe_raw(raw_speech, language)

    def transcribe_raw(self, raw_speech, language: str = "pl") -> str:
        """Transkrybuje surowe audio (numpy array)."""
        self._ensure_model()
        
        print(f"[OpenVINO] transcribe_raw: {len(raw_speech)} samples", flush=True)

        # Mapowanie języka
        lang_token = f"<|{language}|>"

        # Transkrypcja
        result = self._model.generate(
            raw_speech,
            max_new_tokens=448,
            language=lang_token,
            task="transcribe",
        )
        text = str(result).strip()
        print(f"[OpenVINO] Raw transcription done: {text[:50]}...", flush=True)
        return text

    def is_available(self) -> Tuple[bool, Optional[str]]:
        try:
            import openvino_genai
            return True, None
        except ImportError:
            return False, "Zainstaluj: pip install openvino openvino-genai"

    def preload(self) -> bool:
        """Preloaduje model OpenVINO."""
        try:
            self._ensure_ffmpeg()
            self._ensure_model()
            return True
        except Exception as e:
            print(f"[OpenVINO] Preload failed: {e}", flush=True)
            return False

    def is_model_loaded(self) -> bool:
        """Sprawdza czy model jest załadowany."""
        return self._model is not None

    def get_current_device(self) -> str:
        """Zwraca aktualnie używane urządzenie."""
        return self._device or self._get_best_device()

    def get_models(self) -> List[ModelInfo]:
        models = []
        for name, info in self.MODELS.items():
            model_path = self._get_model_path(name)
            # Sprawdź XML i BIN
            xml_exists = (model_path / "openvino_encoder_model.xml").exists()
            bin_exists = (model_path / "openvino_encoder_model.bin").exists()
            is_downloaded = model_path.exists() and xml_exists and bin_exists
            models.append(ModelInfo(name, info["size_mb"], info["desc"], is_downloaded))
        return models

    def download_model(self, model_name: str, progress_callback: Optional[Callable[[float], None]] = None) -> bool:
        if model_name not in self.MODELS:
            return False

        try:
            from huggingface_hub import snapshot_download
            from tqdm import tqdm as base_tqdm

            model_path = self._get_model_path(model_name)
            model_path.parent.mkdir(parents=True, exist_ok=True)

            hf_model = self.HF_MODELS.get(model_name)
            if not hf_model:
                return False

            # Track progress - śledź sumę wszystkich bajtów
            progress_state = {
                'bytes_bars': {},  # id(bar) -> {'current': n, 'total': t}
                'last_pct': 0,
                'last_update': 0
            }

            class ProgressTqdm(base_tqdm):
                def __init__(self, *args, **kwargs):
                    # Filtruj nieznane argumenty (np. 'name' z nowych wersji huggingface_hub)
                    kwargs.pop('name', None)
                    super().__init__(*args, **kwargs)
                    # Zarejestruj każdy pasek (total może być None na początku)
                    progress_state['bytes_bars'][id(self)] = {
                        'current': 0,
                        'total': self.total or 0
                    }

                def update(self, n=1):
                    super().update(n)
                    bar_id = id(self)
                    if bar_id in progress_state['bytes_bars']:
                        # Aktualizuj current i total (total może się zmienić)
                        progress_state['bytes_bars'][bar_id]['current'] = self.n or 0
                        if self.total:
                            progress_state['bytes_bars'][bar_id]['total'] = self.total

                        # Oblicz łączny progress (tylko paski z known total > 1KB)
                        bars_with_total = [
                            b for b in progress_state['bytes_bars'].values()
                            if b['total'] > 1000
                        ]

                        if bars_with_total:
                            total_bytes = sum(b['total'] for b in bars_with_total)
                            current_bytes = sum(b['current'] for b in bars_with_total)

                            if total_bytes > 0 and progress_callback:
                                pct = min(1.0, current_bytes / total_bytes)
                                # Aktualizuj co 1%
                                if pct - progress_state['last_pct'] >= 0.01 or pct >= 0.99:
                                    progress_state['last_pct'] = pct
                                    progress_callback(pct)

                def close(self):
                    bar_id = id(self)
                    if bar_id in progress_state['bytes_bars']:
                        del progress_state['bytes_bars'][bar_id]
                    super().close()

            if progress_callback:
                progress_callback(0.0)

            # Pobierz model z HuggingFace
            # Uwaga: tqdm_class może powodować problemy w niektórych wersjach huggingface_hub
            try:
                snapshot_download(
                    repo_id=hf_model,
                    local_dir=str(model_path),
                    tqdm_class=ProgressTqdm if progress_callback else None,
                )
            except TypeError:
                # Fallback bez custom tqdm
                snapshot_download(
                    repo_id=hf_model,
                    local_dir=str(model_path),
                )

            if progress_callback:
                progress_callback(1.0)

            return True
        except Exception as e:
            import traceback
            print(f"Błąd pobierania modelu OpenVINO: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            return False

    def get_current_model(self) -> Optional[str]:
        return self._model_name

    def set_model(self, model_name: str) -> bool:
        with self._lock:
            if model_name not in self.MODELS:
                return False
            self._model_name = model_name
            self._model = None  # Reset - załaduj przy następnym użyciu
            return True

    def delete_model(self, model_name: str) -> bool:
        """Usuwa pobrany model OpenVINO."""
        if model_name not in self.MODELS:
            return False

        # Nie można usunąć aktywnego modelu
        if model_name == self._model_name:
            return False

        model_path = self._get_model_path(model_name)
        if not model_path.exists():
            return False

        try:
            shutil.rmtree(model_path)
            print(f"[OpenVINO] Model {model_name} usunięty", flush=True)
            return True
        except Exception as e:
            print(f"[OpenVINO] Błąd usuwania modelu: {e}", flush=True)
            return False


# ========== MANAGER ==========

class TranscriberManager:
    """Zarządza backendami transkrypcji."""

    def __init__(self):
        self._backends: Dict[TranscriberType, TranscriberBackend] = {}
        self._current_type: TranscriberType = TranscriberType.GEMINI_CLOUD

        # Inicjalizuj backendy
        self._backends[TranscriberType.GEMINI_CLOUD] = GeminiCloudTranscriber()
        self._backends[TranscriberType.FASTER_WHISPER] = FasterWhisperTranscriber()
        self._backends[TranscriberType.OPENAI_WHISPER] = OpenAIWhisperTranscriber()
        self._backends[TranscriberType.OPENVINO_WHISPER] = OpenVINOWhisperTranscriber()

    def get_available_backends(self) -> List[TranscriberInfo]:
        """Zwraca listę wszystkich backendów z informacją o dostępności."""
        infos = []
        ffmpeg_ok = FFmpegManager.is_installed()

        for t, backend in self._backends.items():
            available, reason = backend.is_available()

            if t == TranscriberType.GEMINI_CLOUD:
                info = TranscriberInfo(
                    type=t,
                    name="Gemini Cloud",
                    description="Google Gemini API (wymaga internetu i API key)",
                    requires_download=False,
                    model_sizes=["cloud"],
                    is_available=available,
                    is_installed=True,  # Zawsze "zainstalowany" - to cloud
                    pip_package=None,
                    unavailable_reason=reason,
                    requires_ffmpeg=False,
                    ffmpeg_installed=True
                )
            elif t == TranscriberType.FASTER_WHISPER:
                is_installed = self._check_package_installed("faster_whisper")
                info = TranscriberInfo(
                    type=t,
                    name="Faster Whisper",
                    description="Najszybsza transkrypcja offline",
                    requires_download=True,
                    model_sizes=list(FasterWhisperTranscriber.MODELS.keys()),
                    is_available=available and ffmpeg_ok,
                    is_installed=is_installed,
                    pip_package="faster-whisper",
                    unavailable_reason=reason if not is_installed else ("Brak ffmpeg" if not ffmpeg_ok else None),
                    requires_ffmpeg=True,
                    ffmpeg_installed=ffmpeg_ok
                )
            elif t == TranscriberType.OPENAI_WHISPER:
                is_installed = self._check_package_installed("whisper")
                info = TranscriberInfo(
                    type=t,
                    name="OpenAI Whisper",
                    description="Oryginalna implementacja Whisper (offline)",
                    requires_download=True,
                    model_sizes=list(OpenAIWhisperTranscriber.MODELS.keys()),
                    is_available=available and ffmpeg_ok,
                    is_installed=is_installed,
                    pip_package="openai-whisper",
                    unavailable_reason=reason if not is_installed else ("Brak ffmpeg" if not ffmpeg_ok else None),
                    requires_ffmpeg=True,
                    ffmpeg_installed=ffmpeg_ok
                )
            elif t == TranscriberType.OPENVINO_WHISPER:
                is_installed = self._check_package_installed("openvino_genai")
                # Wykryj urządzenie tylko jeśli zainstalowane
                if is_installed:
                    ov_backend = self._backends[TranscriberType.OPENVINO_WHISPER]
                    device = ov_backend.get_detected_device()
                    name = f"OpenVINO ({device})"
                    description = f"Intel NPU/GPU - wykryto: {device}"
                else:
                    name = "OpenVINO Whisper"
                    description = "Intel NPU/GPU - wymaga instalacji"
                info = TranscriberInfo(
                    type=t,
                    name=name,
                    description=description,
                    requires_download=True,
                    model_sizes=list(OpenVINOWhisperTranscriber.MODELS.keys()),
                    is_available=available and ffmpeg_ok,
                    is_installed=is_installed,
                    pip_package="openvino openvino-genai librosa huggingface_hub tqdm",
                    unavailable_reason=reason if not is_installed else ("Brak ffmpeg" if not ffmpeg_ok else None),
                    requires_ffmpeg=True,
                    ffmpeg_installed=ffmpeg_ok
                )

            infos.append(info)

        return infos

    def _check_package_installed(self, package_name: str) -> bool:
        """Sprawdza czy pakiet Python jest zainstalowany."""
        try:
            __import__(package_name)
            return True
        except ImportError:
            return False

    def install_backend(self, backend_type: TranscriberType, progress_callback: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """Instaluje pakiet dla backendu przez pip. Zwraca (sukces, komunikat)."""
        import subprocess
        import sys
        import re
        import importlib

        backends = {b.type: b for b in self.get_available_backends()}
        if backend_type not in backends:
            return False, "Nieznany backend"

        info = backends[backend_type]
        if not info.pip_package:
            return False, "Ten backend nie wymaga instalacji"

        if info.is_installed:
            return True, "Już zainstalowano"

        try:
            if progress_callback:
                progress_callback(f"Pobieranie {info.pip_package}...")

            # Uruchom pip install z progress - nie quiet żeby mieć output
            packages = info.pip_package.split()

            process = subprocess.Popen(
                [sys.executable, "-m", "pip", "install"] + packages + ["--progress-bar", "on"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="ignore",
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )

            # Czytaj output linia po linii
            packages_downloaded = 0
            packages_installed = 0

            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break

                line = line.strip()
                if not line:
                    continue

                # Parsuj różne etapy
                if progress_callback:
                    if "Downloading" in line or "downloading" in line.lower():
                        # Wyciągnij nazwę pakietu i progress
                        match = re.search(r'Downloading\s+(\S+)', line)
                        pkg_name = match.group(1) if match else "pakiet"
                        # Sprawdź czy jest procent
                        pct_match = re.search(r'(\d+)%', line)
                        if pct_match:
                            progress_callback(f"Pobieranie: {pct_match.group(1)}%")
                        else:
                            packages_downloaded += 1
                            progress_callback(f"Pobieranie pakietów... ({packages_downloaded})")
                    elif "Installing" in line or "installing" in line.lower():
                        packages_installed += 1
                        progress_callback(f"Instalowanie pakietów... ({packages_installed})")
                    elif "Successfully installed" in line:
                        progress_callback("Weryfikacja instalacji...")
                    elif "Collecting" in line:
                        match = re.search(r'Collecting\s+(\S+)', line)
                        pkg = match.group(1) if match else ""
                        progress_callback(f"Pobieranie zależności: {pkg[:30]}")

            returncode = process.wait(timeout=300)

            if returncode == 0:
                if progress_callback:
                    progress_callback("Zainstalowano!")
                # Odśwież cache importów po instalacji
                importlib.invalidate_caches()
                return True, f"Zainstalowano {info.pip_package}"
            else:
                return False, f"Błąd instalacji (kod {returncode})"

        except subprocess.TimeoutExpired:
            process.kill()
            return False, "Timeout - instalacja trwała zbyt długo"
        except Exception as e:
            return False, f"Błąd: {str(e)}"

    def get_backend(self, backend_type: TranscriberType) -> TranscriberBackend:
        """Zwraca konkretny backend."""
        return self._backends[backend_type]

    def get_current_backend(self) -> TranscriberBackend:
        """Zwraca aktualnie wybrany backend."""
        return self._backends[self._current_type]

    def set_current_backend(self, backend_type: TranscriberType) -> bool:
        """Ustawia aktualny backend."""
        if backend_type in self._backends:
            available, _ = self._backends[backend_type].is_available()
            if available:
                self._current_type = backend_type
                return True
        return False

    def get_current_type(self) -> TranscriberType:
        """Zwraca typ aktualnego backendu."""
        return self._current_type

    def transcribe(self, audio_path: str, language: str = "pl") -> str:
        """Transkrybuje używając aktualnego backendu."""
        return self.get_current_backend().transcribe(audio_path, language)

    def set_gemini_api_key(self, api_key: str):
        """Ustawia API key dla Gemini."""
        gemini = self._backends[TranscriberType.GEMINI_CLOUD]
        if isinstance(gemini, GeminiCloudTranscriber):
            gemini.set_api_key(api_key)

    def install_ffmpeg(self, progress_callback: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """Instaluje ffmpeg."""
        return FFmpegManager.install(progress_callback)

    def is_ffmpeg_installed(self) -> bool:
        """Sprawdza czy ffmpeg jest zainstalowany."""
        return FFmpegManager.is_installed()

    def get_ffmpeg_status(self) -> Tuple[bool, str]:
        """Zwraca status ffmpeg."""
        return FFmpegManager.get_install_status()
