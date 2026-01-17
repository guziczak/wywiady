"""
Serwis diaryzacji głosu.

Fasada łącząca różne backendy diaryzacji i merger transkrypcji.
"""

import asyncio
import numpy as np
from typing import Optional, List, Dict
from pathlib import Path

from .base import DiarizationBackend, DiarizationResult, DiarizationSegment, SpeakerRole
from .heuristic_backend import HeuristicDiarizationBackend
from .merger import TranscriptMerger, WordTimestamp

# Opcjonalny import pyannote
try:
    from .pyannote_backend import PyAnnoteDiarizationBackend, PYANNOTE_AVAILABLE
except ImportError:
    PyAnnoteDiarizationBackend = None
    PYANNOTE_AVAILABLE = False


class DiarizationService:
    """
    Główny serwis diaryzacji.

    Zarządza backendami i zapewnia spójne API do diaryzacji audio.
    """

    def __init__(
        self,
        backend: str = "auto",  # auto, heuristic, pyannote
        hf_token: Optional[str] = None,
        device: str = "auto"
    ):
        self.backend_name = backend
        self.hf_token = hf_token
        self.device = device

        self._backend: Optional[DiarizationBackend] = None
        self._merger = TranscriptMerger()

        self._init_backend()

    def _init_backend(self) -> None:
        """Inicjalizuje backend diaryzacji."""
        if self.backend_name == "pyannote":
            if PYANNOTE_AVAILABLE and self.hf_token:
                self._backend = PyAnnoteDiarizationBackend(
                    hf_token=self.hf_token,
                    device=self.device
                )
            else:
                print("[DIARIZATION] Pyannote niedostępny, fallback to heuristic", flush=True)
                self._backend = HeuristicDiarizationBackend()

        elif self.backend_name == "heuristic":
            self._backend = HeuristicDiarizationBackend()

        else:  # auto
            # Preferuj pyannote jeśli dostępny
            if PYANNOTE_AVAILABLE and self.hf_token:
                self._backend = PyAnnoteDiarizationBackend(
                    hf_token=self.hf_token,
                    device=self.device
                )
            else:
                self._backend = HeuristicDiarizationBackend()

        print(f"[DIARIZATION] Using backend: {self._backend.name}", flush=True)

    async def diarize(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000
    ) -> DiarizationResult:
        """
        Wykonuje diaryzację audio.

        Args:
            audio: Mono audio jako numpy array
            sample_rate: Częstotliwość próbkowania

        Returns:
            DiarizationResult z segmentami i mówcami
        """
        if self._backend is None:
            raise RuntimeError("Backend diaryzacji nie zainicjalizowany")

        return await self._backend.diarize(audio, sample_rate)

    async def diarize_with_transcript(
        self,
        audio: np.ndarray,
        transcript: str,
        sample_rate: int = 16000,
        word_timestamps: Optional[List[WordTimestamp]] = None
    ) -> DiarizationResult:
        """
        Wykonuje diaryzację i łączy z transkrypcją.

        Args:
            audio: Audio jako numpy array
            transcript: Pełna transkrypcja tekstu
            sample_rate: Częstotliwość próbkowania
            word_timestamps: Opcjonalne timestampy słów

        Returns:
            DiarizationResult z segmentami zawierającymi tekst
        """
        # 1. Wykonaj diaryzację
        result = await self.diarize(audio, sample_rate)

        # 2. Połącz z transkrypcją
        if word_timestamps:
            result.segments = self._merger.merge(word_timestamps, result)
        else:
            result.segments = self._merger.merge_simple(transcript, result)

        # 3. Spróbuj lepiej przypisać role na podstawie treści
        if len(result.segments) > 0:
            content_mapping = self._merger.assign_roles_by_content(result.segments)
            # Połącz z istniejącym mapowaniem (content ma niższy priorytet)
            for speaker, role in content_mapping.items():
                if speaker not in result.speaker_mapping or result.speaker_mapping[speaker] == SpeakerRole.UNKNOWN:
                    result.speaker_mapping[speaker] = role

            result.apply_role_mapping(result.speaker_mapping)

        return result

    def assign_roles_manually(
        self,
        result: DiarizationResult,
        mapping: Dict[str, SpeakerRole]
    ) -> DiarizationResult:
        """
        Ręcznie przypisuje role mówcom.

        Args:
            result: Wynik diaryzacji
            mapping: Mapowanie speaker_id -> SpeakerRole

        Returns:
            Zaktualizowany DiarizationResult
        """
        result.apply_role_mapping(mapping)
        return result

    def swap_roles(self, result: DiarizationResult) -> DiarizationResult:
        """
        Zamienia role między dwoma głównymi mówcami.

        Przydatne gdy automatyczne przypisanie jest odwrócone.
        """
        speakers = result.get_speaker_ids()
        if len(speakers) < 2:
            return result

        # Zamień role dwóch pierwszych mówców
        new_mapping = dict(result.speaker_mapping)
        s1, s2 = speakers[0], speakers[1]

        role1 = new_mapping.get(s1, SpeakerRole.UNKNOWN)
        role2 = new_mapping.get(s2, SpeakerRole.UNKNOWN)

        new_mapping[s1] = role2
        new_mapping[s2] = role1

        result.apply_role_mapping(new_mapping)
        return result

    @property
    def backend(self) -> Optional[DiarizationBackend]:
        """Zwraca aktywny backend."""
        return self._backend

    @property
    def is_available(self) -> bool:
        """Sprawdza czy serwis jest dostępny."""
        return self._backend is not None and self._backend.is_available()

    def get_available_backends(self) -> List[Dict[str, str]]:
        """Zwraca listę dostępnych backendów."""
        backends = [
            {
                "id": "heuristic",
                "name": "Heurystyczny (prosty)",
                "available": True,
                "description": "Prosty backend oparty na przerwach w mowie. Nie wymaga GPU."
            }
        ]

        if PYANNOTE_AVAILABLE:
            backends.append({
                "id": "pyannote",
                "name": "Pyannote (dokładny)",
                "available": bool(self.hf_token),
                "description": "Dokładna diaryzacja AI. Wymaga tokenu HuggingFace i GPU."
            })

        return backends


# Singleton
_service: Optional[DiarizationService] = None


def get_diarization_service(
    backend: str = "auto",
    hf_token: Optional[str] = None,
    device: str = "auto"
) -> DiarizationService:
    """
    Zwraca singleton DiarizationService.

    Args:
        backend: Typ backendu (auto, heuristic, pyannote)
        hf_token: Token HuggingFace dla pyannote
        device: Urządzenie (auto, cpu, cuda)
    """
    global _service
    if _service is None:
        _service = DiarizationService(
            backend=backend,
            hf_token=hf_token,
            device=device
        )
    return _service
