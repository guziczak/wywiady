"""
Bazowe klasy dla diaryzacji głosu.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional
from abc import ABC, abstractmethod
import numpy as np


class SpeakerRole(str, Enum):
    """Rola mówcy."""
    DOCTOR = "doctor"
    PATIENT = "patient"
    UNKNOWN = "unknown"

    @property
    def display_name(self) -> str:
        return {
            SpeakerRole.DOCTOR: "Lekarz",
            SpeakerRole.PATIENT: "Pacjent",
            SpeakerRole.UNKNOWN: "Nieznany"
        }.get(self, "Nieznany")

    @property
    def color(self) -> str:
        """Kolor tła dla segmentu."""
        return {
            SpeakerRole.DOCTOR: "#E3F2FD",  # Jasny niebieski
            SpeakerRole.PATIENT: "#E8F5E9",  # Jasny zielony
            SpeakerRole.UNKNOWN: "#F5F5F5"   # Jasny szary
        }.get(self, "#F5F5F5")


@dataclass
class DiarizationSegment:
    """Segment diaryzacji - fragment audio z przypisanym mówcą."""
    start_time: float  # Sekundy od początku nagrania
    end_time: float
    speaker_id: str = "SPEAKER_00"  # Identyfikator mówcy z modelu
    role: SpeakerRole = SpeakerRole.UNKNOWN  # Przypisana rola
    text: str = ""  # Tekst (po połączeniu z transkrypcją)
    confidence: float = 1.0

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def overlaps(self, other: 'DiarizationSegment') -> bool:
        """Sprawdza czy segmenty się nakładają."""
        return not (self.end_time <= other.start_time or self.start_time >= other.end_time)

    def overlap_ratio(self, other: 'DiarizationSegment') -> float:
        """Zwraca stosunek nakładania się segmentów."""
        if not self.overlaps(other):
            return 0.0

        overlap_start = max(self.start_time, other.start_time)
        overlap_end = min(self.end_time, other.end_time)
        overlap_duration = overlap_end - overlap_start

        return overlap_duration / min(self.duration, other.duration)

    def to_dict(self) -> dict:
        return {
            'start_time': self.start_time,
            'end_time': self.end_time,
            'speaker_id': self.speaker_id,
            'role': str(self.role),
            'text': self.text,
            'confidence': self.confidence
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DiarizationSegment':
        role = data.get('role', 'unknown')
        if isinstance(role, str):
            role = SpeakerRole(role)
        return cls(
            start_time=data['start_time'],
            end_time=data['end_time'],
            speaker_id=data.get('speaker_id', 'SPEAKER_00'),
            role=role,
            text=data.get('text', ''),
            confidence=data.get('confidence', 1.0)
        )


@dataclass
class DiarizationResult:
    """Wynik diaryzacji audio."""
    segments: List[DiarizationSegment] = field(default_factory=list)
    num_speakers: int = 0
    speaker_mapping: Dict[str, SpeakerRole] = field(default_factory=dict)
    total_duration: float = 0.0

    def get_segments_by_speaker(self, speaker_id: str) -> List[DiarizationSegment]:
        """Zwraca segmenty dla danego mówcy."""
        return [s for s in self.segments if s.speaker_id == speaker_id]

    def get_segments_by_role(self, role: SpeakerRole) -> List[DiarizationSegment]:
        """Zwraca segmenty dla danej roli."""
        return [s for s in self.segments if s.role == role]

    def get_speaker_ids(self) -> List[str]:
        """Zwraca listę unikalnych identyfikatorów mówców."""
        return list(set(s.speaker_id for s in self.segments))

    def apply_role_mapping(self, mapping: Dict[str, SpeakerRole]) -> None:
        """Stosuje mapowanie ról do segmentów."""
        self.speaker_mapping = mapping
        for segment in self.segments:
            if segment.speaker_id in mapping:
                segment.role = mapping[segment.speaker_id]

    def get_full_transcript(self, separator: str = "\n") -> str:
        """Zwraca pełną transkrypcję z oznaczeniami mówców."""
        lines = []
        for segment in self.segments:
            if segment.text:
                prefix = segment.role.display_name
                lines.append(f"{prefix}: {segment.text}")
        return separator.join(lines)

    def to_dict(self) -> dict:
        return {
            'segments': [s.to_dict() for s in self.segments],
            'num_speakers': self.num_speakers,
            'speaker_mapping': {k: str(v) for k, v in self.speaker_mapping.items()},
            'total_duration': self.total_duration
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DiarizationResult':
        segments = [DiarizationSegment.from_dict(s) for s in data.get('segments', [])]
        mapping = {
            k: SpeakerRole(v) for k, v in data.get('speaker_mapping', {}).items()
        }
        return cls(
            segments=segments,
            num_speakers=data.get('num_speakers', 0),
            speaker_mapping=mapping,
            total_duration=data.get('total_duration', 0.0)
        )


class DiarizationBackend(ABC):
    """Abstrakcyjna klasa bazowa dla backendów diaryzacji."""

    @abstractmethod
    async def diarize(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000
    ) -> DiarizationResult:
        """
        Wykonuje diaryzację audio.

        Args:
            audio: Dane audio jako numpy array (mono, float32)
            sample_rate: Częstotliwość próbkowania

        Returns:
            DiarizationResult z segmentami
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Sprawdza czy backend jest dostępny."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Nazwa backendu."""
        pass
