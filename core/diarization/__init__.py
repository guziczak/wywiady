"""
Moduł diaryzacji głosu.

Obsługuje rozpoznawanie mówców w nagraniach audio.
"""

from .base import DiarizationSegment, DiarizationResult, SpeakerRole
from .service import DiarizationService, get_diarization_service
from .merger import TranscriptMerger

__all__ = [
    'DiarizationSegment',
    'DiarizationResult',
    'SpeakerRole',
    'DiarizationService',
    'get_diarization_service',
    'TranscriptMerger',
]
