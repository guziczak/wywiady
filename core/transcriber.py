"""
Moduł transkrypcji audio z obsługą wielu backendów.
Wspiera: Gemini Cloud, faster-whisper, openai-whisper
"""

import os
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

    @abstractmethod
    def set_model(self, model_name: str) -> bool:
        """Ustawia model do użycia."""
        pass


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
            from faster_whisper import WhisperModel

            if progress_callback:
                progress_callback(0.1)

            # Użyj lokalnego cache
            download_root = MODELS_DIR / "faster-whisper"
            download_root.mkdir(parents=True, exist_ok=True)

            # Pobierz model (cache'uje się automatycznie w download_root)
            _ = WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8",
                download_root=str(download_root)
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
                progress_callback(f"Instaluję {info.pip_package}...")

            # Uruchom pip install
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", info.pip_package, "--quiet"],
                capture_output=True,
                timeout=300,  # 5 minut timeout
                encoding="utf-8",
                errors="ignore"
            )

            if result.returncode == 0:
                if progress_callback:
                    progress_callback("Zainstalowano!")
                return True, f"Zainstalowano {info.pip_package}"
            else:
                error = result.stderr[:200] if result.stderr else "Nieznany błąd"
                return False, f"Błąd instalacji: {error}"

        except subprocess.TimeoutExpired:
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
