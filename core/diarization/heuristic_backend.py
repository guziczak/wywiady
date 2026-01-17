"""
Heurystyczny backend diaryzacji.

Prosty backend oparty na analizie przerw w mowie i zmianach głośności.
Nie wymaga dodatkowych modeli - działa na podstawie reguł.
"""

import asyncio
import numpy as np
from typing import List, Tuple
from .base import DiarizationBackend, DiarizationResult, DiarizationSegment, SpeakerRole


class HeuristicDiarizationBackend(DiarizationBackend):
    """
    Heurystyczny backend diaryzacji.

    Założenia:
    - Długa pauza (>1.5s) = potencjalna zmiana mówcy
    - Naprzemienność: jeśli wykryto 2 mówców, zakładamy dialog L-P-L-P
    - Pytanie (?) = prawdopodobnie lekarz
    """

    def __init__(
        self,
        pause_threshold: float = 1.5,  # Sekundy przerwy = zmiana mówcy
        silence_threshold: float = 0.02,  # RMS poniżej tego = cisza
        min_segment_duration: float = 0.5  # Min długość segmentu
    ):
        self.pause_threshold = pause_threshold
        self.silence_threshold = silence_threshold
        self.min_segment_duration = min_segment_duration

    async def diarize(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000
    ) -> DiarizationResult:
        """
        Wykonuje heurystyczną diaryzację.

        1. Wykrywa segmenty mowy (VAD prosty)
        2. Grupuje segmenty oddzielone długimi przerwami
        3. Przypisuje naprzemiennie speaker_id
        """
        # Normalizuj audio
        audio = audio.flatten().astype(np.float32)
        if np.max(np.abs(audio)) > 0:
            audio = audio / np.max(np.abs(audio))

        total_duration = len(audio) / sample_rate

        # 1. Wykryj aktywność głosową (Voice Activity Detection)
        speech_segments = self._detect_speech_segments(audio, sample_rate)

        if not speech_segments:
            return DiarizationResult(total_duration=total_duration)

        # 2. Grupuj segmenty w "wypowiedzi" (rozdzielone pauzami)
        utterances = self._group_into_utterances(speech_segments)

        # 3. Przypisz mówców naprzemiennie
        segments = []
        current_speaker = 0
        num_speakers = min(2, len(utterances))  # Max 2 mówców w dialogu

        for i, (start, end) in enumerate(utterances):
            speaker_id = f"SPEAKER_{current_speaker:02d}"

            segment = DiarizationSegment(
                start_time=start,
                end_time=end,
                speaker_id=speaker_id,
                role=SpeakerRole.UNKNOWN,
                confidence=0.7  # Niska pewność dla heurystyki
            )
            segments.append(segment)

            # Zmień mówcę dla następnej wypowiedzi
            if num_speakers > 1:
                current_speaker = 1 - current_speaker  # Toggle 0/1

        # 4. Wstępne przypisanie ról
        # Założenie: pierwszy mówca = lekarz (zaczyna wizytę)
        speaker_mapping = {}
        speaker_ids = list(set(s.speaker_id for s in segments))

        if len(speaker_ids) >= 1:
            speaker_mapping[speaker_ids[0]] = SpeakerRole.DOCTOR
        if len(speaker_ids) >= 2:
            speaker_mapping[speaker_ids[1]] = SpeakerRole.PATIENT

        result = DiarizationResult(
            segments=segments,
            num_speakers=num_speakers,
            speaker_mapping=speaker_mapping,
            total_duration=total_duration
        )
        result.apply_role_mapping(speaker_mapping)

        return result

    def _detect_speech_segments(
        self,
        audio: np.ndarray,
        sample_rate: int
    ) -> List[Tuple[float, float]]:
        """
        Prosty VAD oparty na energii sygnału.

        Returns:
            Lista tupli (start_time, end_time) dla segmentów mowy
        """
        # Ramki po 30ms z krokiem 10ms
        frame_length = int(0.03 * sample_rate)
        hop_length = int(0.01 * sample_rate)

        segments = []
        in_speech = False
        speech_start = 0

        for i in range(0, len(audio) - frame_length, hop_length):
            frame = audio[i:i + frame_length]
            rms = np.sqrt(np.mean(frame ** 2))

            time = i / sample_rate

            if rms > self.silence_threshold:
                if not in_speech:
                    in_speech = True
                    speech_start = time
            else:
                if in_speech:
                    in_speech = False
                    duration = time - speech_start
                    if duration >= self.min_segment_duration:
                        segments.append((speech_start, time))

        # Zamknij ostatni segment
        if in_speech:
            end_time = len(audio) / sample_rate
            duration = end_time - speech_start
            if duration >= self.min_segment_duration:
                segments.append((speech_start, end_time))

        return segments

    def _group_into_utterances(
        self,
        speech_segments: List[Tuple[float, float]]
    ) -> List[Tuple[float, float]]:
        """
        Grupuje segmenty mowy w wypowiedzi.

        Segmenty rozdzielone pauzą > pause_threshold traktowane jako osobne wypowiedzi.
        """
        if not speech_segments:
            return []

        utterances = []
        current_start = speech_segments[0][0]
        current_end = speech_segments[0][1]

        for i in range(1, len(speech_segments)):
            segment_start, segment_end = speech_segments[i]
            gap = segment_start - current_end

            if gap > self.pause_threshold:
                # Długa pauza - zamknij bieżącą wypowiedź
                utterances.append((current_start, current_end))
                current_start = segment_start

            current_end = segment_end

        # Dodaj ostatnią wypowiedź
        utterances.append((current_start, current_end))

        return utterances

    def is_available(self) -> bool:
        """Heurystyczny backend jest zawsze dostępny."""
        return True

    @property
    def name(self) -> str:
        return "Heurystyczny (prosty)"
