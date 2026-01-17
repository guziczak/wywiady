"""
Pyannote backend diaryzacji.

Używa pyannote-audio dla dokładnej diaryzacji mówców.
Wymaga tokenu HuggingFace i instalacji pyannote.audio.
"""

import asyncio
import tempfile
import os
import numpy as np
from pathlib import Path
from typing import Optional
import warnings

from .base import DiarizationBackend, DiarizationResult, DiarizationSegment, SpeakerRole

# Sprawdź dostępność pyannote
try:
    from pyannote.audio import Pipeline
    import torch
    PYANNOTE_AVAILABLE = True
except ImportError:
    PYANNOTE_AVAILABLE = False
    Pipeline = None
    torch = None

# Sprawdź dostępność soundfile dla zapisu WAV
try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except ImportError:
    SOUNDFILE_AVAILABLE = False
    sf = None


class PyAnnoteDiarizationBackend(DiarizationBackend):
    """
    Backend diaryzacji oparty na pyannote-audio.

    Wymaga:
    - pip install pyannote.audio
    - Token HuggingFace z akceptowaną licencją modelu
    - GPU rekomendowane (ale działa na CPU)
    """

    def __init__(
        self,
        hf_token: Optional[str] = None,
        device: str = "auto",
        num_speakers: Optional[int] = 2  # Wymuszenie liczby mówców (None = auto)
    ):
        self.hf_token = hf_token or os.environ.get("HUGGINGFACE_TOKEN", "")
        self.num_speakers = num_speakers
        self._pipeline: Optional[Pipeline] = None
        self._device = self._detect_device(device)

    def _detect_device(self, device: str) -> str:
        """Wykrywa dostępne urządzenie."""
        if device != "auto":
            return device

        if not PYANNOTE_AVAILABLE:
            return "cpu"

        if torch.cuda.is_available():
            return "cuda"
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return "mps"
        else:
            return "cpu"

    def _load_pipeline(self) -> None:
        """Lazy loading pipeline."""
        if self._pipeline is not None:
            return

        if not PYANNOTE_AVAILABLE:
            raise RuntimeError("pyannote.audio nie jest zainstalowane")

        if not self.hf_token:
            raise RuntimeError(
                "Brak tokenu HuggingFace. Ustaw HUGGINGFACE_TOKEN lub podaj hf_token."
            )

        print(f"[DIARIZATION] Loading pyannote pipeline on {self._device}...", flush=True)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=self.hf_token
            )

        if self._device != "cpu":
            self._pipeline.to(torch.device(self._device))

        print("[DIARIZATION] Pipeline loaded!", flush=True)

    async def diarize(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000
    ) -> DiarizationResult:
        """
        Wykonuje diaryzację używając pyannote.

        Args:
            audio: Mono audio jako numpy array (float32)
            sample_rate: Częstotliwość próbkowania

        Returns:
            DiarizationResult
        """
        if not self.is_available():
            raise RuntimeError("Pyannote backend niedostępny")

        # Lazy load
        self._load_pipeline()

        # Zapisz audio do tymczasowego pliku (pyannote wymaga ścieżki)
        audio = audio.flatten().astype(np.float32)
        total_duration = len(audio) / sample_rate

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Zapisz WAV
            if SOUNDFILE_AVAILABLE:
                sf.write(tmp_path, audio, sample_rate)
            else:
                # Fallback - prosty zapis WAV
                self._write_wav_simple(tmp_path, audio, sample_rate)

            # Uruchom diaryzację (w executor bo jest sync)
            loop = asyncio.get_event_loop()
            diarization = await loop.run_in_executor(
                None,
                lambda: self._run_pipeline(tmp_path)
            )

            # Parsuj wyniki
            segments = []
            speaker_ids = set()

            for turn, _, speaker in diarization.itertracks(yield_label=True):
                speaker_ids.add(speaker)
                segment = DiarizationSegment(
                    start_time=turn.start,
                    end_time=turn.end,
                    speaker_id=speaker,
                    role=SpeakerRole.UNKNOWN,
                    confidence=0.9
                )
                segments.append(segment)

            # Domyślne mapowanie ról
            speaker_list = sorted(list(speaker_ids))
            speaker_mapping = {}

            if len(speaker_list) >= 1:
                speaker_mapping[speaker_list[0]] = SpeakerRole.DOCTOR
            if len(speaker_list) >= 2:
                speaker_mapping[speaker_list[1]] = SpeakerRole.PATIENT

            result = DiarizationResult(
                segments=segments,
                num_speakers=len(speaker_ids),
                speaker_mapping=speaker_mapping,
                total_duration=total_duration
            )
            result.apply_role_mapping(speaker_mapping)

            return result

        finally:
            # Usuń plik tymczasowy
            try:
                os.unlink(tmp_path)
            except:
                pass

    def _run_pipeline(self, audio_path: str):
        """Uruchamia pipeline (synchronicznie)."""
        params = {}
        if self.num_speakers is not None:
            params["num_speakers"] = self.num_speakers

        return self._pipeline(audio_path, **params)

    def _write_wav_simple(self, path: str, audio: np.ndarray, sample_rate: int) -> None:
        """Prosty zapis WAV bez zewnętrznych bibliotek."""
        import struct
        import wave

        # Konwertuj float32 do int16
        audio_int16 = (audio * 32767).astype(np.int16)

        with wave.open(path, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(sample_rate)
            wav.writeframes(audio_int16.tobytes())

    def is_available(self) -> bool:
        """Sprawdza czy backend jest dostępny."""
        return PYANNOTE_AVAILABLE and bool(self.hf_token)

    @property
    def name(self) -> str:
        return "Pyannote (dokładny)"
