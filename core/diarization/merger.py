"""
Merger transkrypcji z diaryzacją.

Łączy wyniki transkrypcji (z timestampami słów) z diaryzacją (segmenty mówców).
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from .base import DiarizationSegment, DiarizationResult, SpeakerRole


@dataclass
class WordTimestamp:
    """Słowo z timestampem z transkrypcji."""
    word: str
    start_time: float
    end_time: float


class TranscriptMerger:
    """
    Łączy transkrypcję z diaryzacją.

    Dla każdego słowa z transkrypcji znajduje odpowiedni segment diaryzacji
    i przypisuje mówcę.
    """

    def __init__(self, overlap_threshold: float = 0.5):
        """
        Args:
            overlap_threshold: Min overlap ratio żeby przypisać słowo do segmentu
        """
        self.overlap_threshold = overlap_threshold

    def merge(
        self,
        words: List[WordTimestamp],
        diarization: DiarizationResult
    ) -> List[DiarizationSegment]:
        """
        Łączy słowa z timestampami z segmentami diaryzacji.

        Args:
            words: Lista słów z timestampami
            diarization: Wynik diaryzacji

        Returns:
            Lista segmentów z przypisanym tekstem
        """
        if not words or not diarization.segments:
            return diarization.segments

        # Dla każdego słowa znajdź najlepszy segment
        word_assignments: Dict[int, List[str]] = {
            i: [] for i in range(len(diarization.segments))
        }

        for word in words:
            best_segment_idx = self._find_best_segment(word, diarization.segments)
            if best_segment_idx is not None:
                word_assignments[best_segment_idx].append(word.word)

        # Przypisz tekst do segmentów
        result_segments = []
        for i, segment in enumerate(diarization.segments):
            new_segment = DiarizationSegment(
                start_time=segment.start_time,
                end_time=segment.end_time,
                speaker_id=segment.speaker_id,
                role=segment.role,
                text=" ".join(word_assignments[i]),
                confidence=segment.confidence
            )
            result_segments.append(new_segment)

        return result_segments

    def _find_best_segment(
        self,
        word: WordTimestamp,
        segments: List[DiarizationSegment]
    ) -> Optional[int]:
        """Znajduje indeks najlepiej pasującego segmentu dla słowa."""
        word_mid = (word.start_time + word.end_time) / 2

        best_idx = None
        best_overlap = 0

        for i, segment in enumerate(segments):
            # Sprawdź czy środek słowa jest w segmencie
            if segment.start_time <= word_mid <= segment.end_time:
                return i

            # Sprawdź overlap
            overlap_start = max(word.start_time, segment.start_time)
            overlap_end = min(word.end_time, segment.end_time)

            if overlap_start < overlap_end:
                overlap = overlap_end - overlap_start
                word_duration = word.end_time - word.start_time
                overlap_ratio = overlap / word_duration if word_duration > 0 else 0

                if overlap_ratio > best_overlap and overlap_ratio >= self.overlap_threshold:
                    best_overlap = overlap_ratio
                    best_idx = i

        return best_idx

    def merge_simple(
        self,
        transcript: str,
        diarization: DiarizationResult
    ) -> List[DiarizationSegment]:
        """
        Uproszczone łączenie gdy brak timestampów słów.

        Dzieli transkrypcję proporcjonalnie do długości segmentów.
        """
        if not transcript or not diarization.segments:
            return diarization.segments

        words = transcript.split()
        total_words = len(words)

        if total_words == 0:
            return diarization.segments

        # Oblicz proporcje czasowe
        total_duration = sum(s.duration for s in diarization.segments)
        if total_duration == 0:
            return diarization.segments

        result_segments = []
        word_index = 0

        for segment in diarization.segments:
            # Proporcja słów dla tego segmentu
            proportion = segment.duration / total_duration
            num_words = max(1, int(total_words * proportion))

            # Przydziel słowa
            segment_words = words[word_index:word_index + num_words]
            word_index += num_words

            new_segment = DiarizationSegment(
                start_time=segment.start_time,
                end_time=segment.end_time,
                speaker_id=segment.speaker_id,
                role=segment.role,
                text=" ".join(segment_words),
                confidence=segment.confidence * 0.7  # Niższa pewność dla prostego podziału
            )
            result_segments.append(new_segment)

        # Dodaj pozostałe słowa do ostatniego segmentu
        if word_index < total_words and result_segments:
            remaining = words[word_index:]
            result_segments[-1].text += " " + " ".join(remaining)

        return result_segments

    def assign_roles_by_content(
        self,
        segments: List[DiarizationSegment]
    ) -> Dict[str, SpeakerRole]:
        """
        Przypisuje role na podstawie treści wypowiedzi.

        Heurystyki:
        - Pytania (?) = prawdopodobnie lekarz
        - Krótkie odpowiedzi = prawdopodobnie pacjent
        - Terminologia medyczna = prawdopodobnie lekarz
        """
        speaker_scores: Dict[str, Dict[str, float]] = {}

        medical_terms = [
            'diagnoz', 'badani', 'leczeni', 'zalec', 'przepisz',
            'przyjmuj', 'dawkow', 'lek', 'tabletk', 'recepta'
        ]

        for segment in segments:
            speaker = segment.speaker_id
            if speaker not in speaker_scores:
                speaker_scores[speaker] = {'doctor': 0, 'patient': 0}

            text = segment.text.lower()

            # Pytania sugerują lekarza
            if '?' in segment.text:
                speaker_scores[speaker]['doctor'] += 2

            # Terminologia medyczna sugeruje lekarza
            for term in medical_terms:
                if term in text:
                    speaker_scores[speaker]['doctor'] += 1

            # Krótkie odpowiedzi sugerują pacjenta
            word_count = len(text.split())
            if word_count <= 5:
                speaker_scores[speaker]['patient'] += 1

            # Długie wypowiedzi mogą być objaśnieniami lekarza
            if word_count > 20:
                speaker_scores[speaker]['doctor'] += 1

        # Przypisz role na podstawie wyników
        speaker_mapping = {}
        speakers = list(speaker_scores.keys())

        if len(speakers) == 1:
            # Jeden mówca - nie możemy określić
            speaker_mapping[speakers[0]] = SpeakerRole.UNKNOWN
        elif len(speakers) >= 2:
            # Porównaj wyniki
            s1, s2 = speakers[0], speakers[1]
            score1 = speaker_scores[s1]['doctor'] - speaker_scores[s1]['patient']
            score2 = speaker_scores[s2]['doctor'] - speaker_scores[s2]['patient']

            if score1 > score2:
                speaker_mapping[s1] = SpeakerRole.DOCTOR
                speaker_mapping[s2] = SpeakerRole.PATIENT
            else:
                speaker_mapping[s1] = SpeakerRole.PATIENT
                speaker_mapping[s2] = SpeakerRole.DOCTOR

            # Pozostali mówcy
            for speaker in speakers[2:]:
                speaker_mapping[speaker] = SpeakerRole.UNKNOWN

        return speaker_mapping
