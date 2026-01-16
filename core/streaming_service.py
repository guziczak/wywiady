import threading
import queue
import time
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

class StreamingTranscriber:
    """
    Kaskadowy transkryber z trzema warstwami:
    - Warstwa 1 (provisional): Small model, 2s chunki, real-time
    - Warstwa 2 (improved): Small model, większy kontekst, co 5-7s
    - Warstwa 3 (final): Large model, kompletne fragmenty
    """

    def __init__(self, model_size="small", device="auto", compute_type="int8"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model_small = None
        self.model_large = None
        self.is_running = False
        self.audio_queue = queue.Queue()

        # Callbacks dla różnych warstw
        self.callback_provisional = None  # Szary jasny (real-time)
        self.callback_improved = None     # Szary ciemny (kontekstowy)
        self.callback_final = None        # Czarny (finalizacja)

        # Audio params
        self.sample_rate = 16000
        self.block_size = 4096  # ~250ms

        # PEŁNY BUFOR AUDIO - nie czyścimy!
        self.full_audio_buffer = []
        self.full_audio_samples = 0

        # Śledzenie segmentów
        self.finalized_samples = 0  # Do którego sample'a mamy finalizację
        self.last_improved_samples = 0  # Do którego sample'a zrobiliśmy improved

        # Timing dla warstw
        self.last_improved_time = 0
        self.improved_interval = 5.0  # Co 5 sekund robimy improved

        # Detekcja ciszy
        self.silence_start = None
        self.silence_threshold = 2.0  # 2s ciszy = finalizacja

    def load_model(self):
        """Ładuje model small."""
        if self.model_small:
            return
        print(f"[STREAM] Loading faster-whisper {self.model_size} on {self.device}...", flush=True)
        try:
            self.model_small = WhisperModel(
                self.model_size,
                device=self.device if self.device != "auto" else "cpu",
                compute_type=self.compute_type
            )
            print("[STREAM] Small model loaded!", flush=True)
        except Exception as e:
            print(f"[STREAM] Model load error: {e}", flush=True)
            if self.device == "cuda":
                print("[STREAM] Fallback to CPU...", flush=True)
                self.model_small = WhisperModel(self.model_size, device="cpu", compute_type="int8")

    def load_large_model(self, model_path=None):
        """Ładuje model large (opcjonalnie)."""
        if self.model_large:
            return
        # Na razie używamy medium jako "large" dla faster-whisper
        # Można też użyć zewnętrznego modelu
        print("[STREAM] Loading large model (medium)...", flush=True)
        try:
            self.model_large = WhisperModel(
                "medium",
                device=self.device if self.device != "auto" else "cpu",
                compute_type=self.compute_type
            )
            print("[STREAM] Large model loaded!", flush=True)
        except Exception as e:
            print(f"[STREAM] Large model error: {e}", flush=True)
            self.model_large = None

    def start(self, callback_provisional, callback_improved=None, callback_final=None):
        """
        Uruchamia streaming z wieloma callbackami.

        Args:
            callback_provisional: fn(text, start_sample, end_sample) - real-time, szary jasny
            callback_improved: fn(text, start_sample, end_sample) - kontekstowy, szary ciemny
            callback_final: fn(text, start_sample, end_sample) - finalizacja, czarny
        """
        self.callback_provisional = callback_provisional
        self.callback_improved = callback_improved or callback_provisional
        self.callback_final = callback_final or callback_improved or callback_provisional

        if not self.model_small:
            self.load_model()

        self.is_running = True
        self.audio_queue = queue.Queue()

        # Reset buforów
        self.full_audio_buffer = []
        self.full_audio_samples = 0
        self.finalized_samples = 0
        self.last_improved_samples = 0
        self.last_improved_time = time.time()
        self.silence_start = None

        # Start audio stream
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            channels=1,
            dtype="float32",
            callback=self._audio_callback
        )
        self.stream.start()

        # Start worker thread
        self.worker_thread = threading.Thread(target=self._process_audio, daemon=True)
        self.worker_thread.start()

        # Start improved/final thread
        self.cascade_thread = threading.Thread(target=self._cascade_loop, daemon=True)
        self.cascade_thread.start()

        print("[STREAM] Started with cascading.", flush=True)

    def stop(self):
        """Zatrzymuje streaming."""
        self.is_running = False
        if hasattr(self, 'stream'):
            try:
                self.stream.stop()
                self.stream.close()
            except:
                pass
        print("[STREAM] Stopped.", flush=True)

    def get_full_audio(self):
        """Zwraca pełny bufor audio jako numpy array."""
        if not self.full_audio_buffer:
            return np.array([], dtype=np.float32)
        return np.concatenate(self.full_audio_buffer, axis=0).flatten()

    def _audio_callback(self, indata, frames, time_info, status):
        """Callback od sounddevice - wrzuca audio do kolejki."""
        if status:
            print(f"[STREAM] Audio status: {status}", flush=True)
        self.audio_queue.put(indata.copy())

    def _process_audio(self):
        """Główna pętla real-time (warstwa 1 - provisional)."""
        chunk_buffer = []
        chunk_samples = 0
        min_samples = int(2.0 * self.sample_rate)  # 2 sekundy

        while self.is_running:
            try:
                chunk = self.audio_queue.get(timeout=0.5)

                # Dodaj do pełnego bufora
                self.full_audio_buffer.append(chunk)
                chunk_len = len(chunk)
                self.full_audio_samples += chunk_len

                # Dodaj do tymczasowego bufora dla real-time
                chunk_buffer.append(chunk)
                chunk_samples += chunk_len

                # Jeśli mamy 2s, transkrybuj (provisional)
                if chunk_samples >= min_samples:
                    start_sample = self.full_audio_samples - chunk_samples
                    self._transcribe_provisional(chunk_buffer, start_sample)
                    chunk_buffer = []
                    chunk_samples = 0

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[STREAM] Worker error: {e}", flush=True)

    def _transcribe_provisional(self, buffer_list, start_sample):
        """Warstwa 1: Real-time transkrypcja małych chunków."""
        audio_data = np.concatenate(buffer_list, axis=0).flatten()
        end_sample = start_sample + len(audio_data)

        # Detekcja ciszy
        rms = np.sqrt(np.mean(audio_data**2))
        if rms < 0.01:
            # Cisza - aktualizuj timer
            if self.silence_start is None:
                self.silence_start = time.time()
            return
        else:
            self.silence_start = None  # Reset jeśli jest dźwięk

        try:
            segments, info = self.model_small.transcribe(
                audio_data,
                beam_size=1,
                language="pl",
                vad_filter=True
            )

            text = " ".join([s.text for s in segments]).strip()

            if text and self.callback_provisional:
                self.callback_provisional(text, start_sample, end_sample)

        except Exception as e:
            print(f"[STREAM] Provisional error: {e}", flush=True)

    def _cascade_loop(self):
        """Pętla dla warstw 2 i 3 (improved/final)."""
        while self.is_running:
            try:
                time.sleep(1.0)  # Sprawdzaj co sekundę

                now = time.time()

                # === WARSTWA 2: Improved (co 5s) ===
                if now - self.last_improved_time >= self.improved_interval:
                    self._do_improved_transcription()
                    self.last_improved_time = now

                # === WARSTWA 3: Final (po ciszy) ===
                if self.silence_start and (now - self.silence_start) >= self.silence_threshold:
                    self._do_final_transcription()
                    self.silence_start = None  # Reset

            except Exception as e:
                print(f"[STREAM] Cascade error: {e}", flush=True)

    def _do_improved_transcription(self):
        """Warstwa 2: Re-transkrypcja z większym kontekstem (small model)."""
        # Bierzemy audio od ostatniego improved do teraz
        if self.full_audio_samples <= self.last_improved_samples:
            return

        # Bierzemy ostatnie 10-15 sekund (nie więcej, żeby było szybko)
        max_samples = int(15.0 * self.sample_rate)
        start_sample = max(self.finalized_samples, self.full_audio_samples - max_samples)

        audio = self.get_full_audio()
        if len(audio) == 0:
            return

        segment_audio = audio[start_sample:]
        if len(segment_audio) < self.sample_rate:  # Min 1s
            return

        # Sprawdź czy nie cisza
        rms = np.sqrt(np.mean(segment_audio**2))
        if rms < 0.01:
            return

        try:
            print(f"[STREAM] Improved: {len(segment_audio)/self.sample_rate:.1f}s audio", flush=True)

            segments, info = self.model_small.transcribe(
                segment_audio,
                beam_size=3,  # Lepszy beam dla jakości
                language="pl",
                vad_filter=True
            )

            text = " ".join([s.text for s in segments]).strip()

            if text and self.callback_improved:
                self.callback_improved(text, start_sample, self.full_audio_samples)

            self.last_improved_samples = self.full_audio_samples

        except Exception as e:
            print(f"[STREAM] Improved error: {e}", flush=True)

    def _do_final_transcription(self):
        """Warstwa 3: Finalizacja z dużym modelem (lub lepszymi ustawieniami small)."""
        # Bierzemy audio od ostatniej finalizacji do teraz
        if self.full_audio_samples <= self.finalized_samples:
            return

        audio = self.get_full_audio()
        if len(audio) == 0:
            return

        segment_audio = audio[self.finalized_samples:]
        if len(segment_audio) < self.sample_rate:  # Min 1s
            return

        # Sprawdź czy nie cisza (cały segment)
        rms = np.sqrt(np.mean(segment_audio**2))
        if rms < 0.01:
            self.finalized_samples = self.full_audio_samples
            return

        try:
            duration = len(segment_audio) / self.sample_rate
            print(f"[STREAM] Final: {duration:.1f}s audio", flush=True)

            # Użyj large model jeśli dostępny, inaczej small z lepszymi parametrami
            model = self.model_large if self.model_large else self.model_small
            beam = 5 if self.model_large else 3

            segments, info = model.transcribe(
                segment_audio,
                beam_size=beam,
                language="pl",
                vad_filter=True,
                word_timestamps=False
            )

            text = " ".join([s.text for s in segments]).strip()

            if text and self.callback_final:
                self.callback_final(text, self.finalized_samples, self.full_audio_samples)

            # Oznacz jako sfinalizowane
            self.finalized_samples = self.full_audio_samples

        except Exception as e:
            print(f"[STREAM] Final error: {e}", flush=True)

    def force_finalize(self):
        """Wymusza finalizację (np. przy kliknięciu STOP)."""
        self._do_final_transcription()
