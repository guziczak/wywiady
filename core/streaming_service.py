import threading
import queue
import time
from pathlib import Path
import numpy as np
import sounddevice as sd
try:
    from faster_whisper import WhisperModel
    _FASTER_WHISPER_IMPORT_ERROR = None
except Exception as e:
    WhisperModel = None
    _FASTER_WHISPER_IMPORT_ERROR = str(e)

# Define models path
MODELS_DIR = Path(__file__).parent.parent / "models" / "faster-whisper"

# Cache for OpenVINO backends to prevent re-loading on NPU
_OPENVINO_CACHE = {}
_CACHE_LOCK = threading.Lock()

class OpenVINOShim:
    """Nakładka na OpenVINOWhisperTranscriber udająca interface faster-whisper. Implements Singleton per model."""
    def __new__(cls, model_name, device):
        key = f"{model_name}_{device}"
        with _CACHE_LOCK:
            if key not in _OPENVINO_CACHE:
                instance = super(OpenVINOShim, cls).__new__(cls)
                instance._initialized = False
                instance._exec_lock = threading.Lock() # Lock na wykonanie
                _OPENVINO_CACHE[key] = instance
            return _OPENVINO_CACHE[key]

    def __init__(self, model_name, device):
        if getattr(self, '_initialized', False):
            return
            
        print(f"[OpenVINOShim] Initializing {model_name} with requested device: '{device}'", flush=True)
        from core.transcriber import OpenVINOWhisperTranscriber
        self.backend = OpenVINOWhisperTranscriber()
        # Wymuś nazwę
        self.backend._model_name = model_name
        
        # Ustaw urządzenie (jeśli nie auto)
        if device and device.lower() != "auto":
            self.backend.set_device(device)
            
        # Załaduj model synchronicznie
        self.backend._ensure_model()
        self._initialized = True

    def transcribe(self, audio, beam_size=5, language="pl", vad_filter=True, word_timestamps=False):
        # OpenVINO backend oczekuje numpy array (float32) lub ścieżki
        # Zwracamy obiekt udający segmenty faster-whisper
        class Segment:
            def __init__(self, text):
                self.text = text
        
        # Transkrypcja - GUARDED BY LOCK
        with self._exec_lock:
            text = self.backend.transcribe_raw(audio, language=language)
        
        # Zwracamy listę segmentów (jeden duży segment) i info (dummy)
        return [Segment(text)], None

class StreamingTranscriber:
    """
    Kaskadowy transkryber z trzema warstwami.
    Wspiera backendy: faster-whisper (domyślny) oraz OpenVINO.
    """

    def __init__(
        self,
        model_size="small",
        device="auto",
        compute_type="int8",
        use_openvino=False,
        enable_medium: bool = True,
        enable_large: bool = True,
        improved_interval: float = 5.0,
        silence_threshold: float = 2.0
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.use_openvino = use_openvino
        self.enable_medium = enable_medium
        self.enable_large = enable_large
        
        self.model_tiny = None
        self.model_medium = None
        self.model_large = None
        self.model_tiny_error = None
        self.model_medium_error = None
        self.model_large_error = None
        self.is_running = False
        self.audio_queue = queue.Queue()

        # Ensure models dir exists (tylko dla faster-whisper)
        if not use_openvino:
            if WhisperModel is None:
                raise RuntimeError(f"Brak faster-whisper: {_FASTER_WHISPER_IMPORT_ERROR}")
            MODELS_DIR.mkdir(parents=True, exist_ok=True)

        # Callbacks dla różnych warstw
        self.callback_provisional = None
        self.callback_improved = None
        self.callback_final = None
        self.external_backend = None # Deprecated logic, but kept for compatibility

        # Audio params
        self.sample_rate = 16000
        self.block_size = 4096  # ~250ms

        # PEŁNY BUFOR AUDIO
        self.full_audio_buffer = []
        self.full_audio_samples = 0

        # Śledzenie segmentów
        self.finalized_samples = 0
        self.last_improved_samples = 0

        # Timing
        self.last_improved_time = 0
        self.improved_interval = improved_interval

        # Detekcja ciszy
        self.silence_timer = None
        self.silence_threshold = silence_threshold
        self._silence_lock = threading.Lock()

    def update_pipeline_config(
        self,
        enable_medium: bool | None = None,
        enable_large: bool | None = None,
        improved_interval: float | None = None,
        silence_threshold: float | None = None
    ):
        """Aktualizuje ustawienia pipeline (bez restartu)."""
        if enable_medium is not None:
            self.enable_medium = bool(enable_medium)
        if enable_large is not None:
            self.enable_large = bool(enable_large)
        if improved_interval is not None:
            try:
                self.improved_interval = max(1.0, float(improved_interval))
            except Exception:
                pass
        if silence_threshold is not None:
            try:
                self.silence_threshold = max(0.5, float(silence_threshold))
            except Exception:
                pass

    def load_model(self):
        """Ładuje model tiny (warstwa 1 - provisional)."""
        if self.model_tiny:
            return
            
        print(f"[STREAM] Loading tiny model (OpenVINO={self.use_openvino})...", flush=True)
        try:
            if self.use_openvino:
                self.model_tiny = OpenVINOShim("tiny", self.device)
            else:
                if WhisperModel is None:
                    raise RuntimeError(f"Brak faster-whisper: {_FASTER_WHISPER_IMPORT_ERROR}")
                self.model_tiny = WhisperModel(
                    "tiny",
                    device=self.device if self.device != "auto" else "cpu",
                    compute_type=self.compute_type,
                    download_root=str(MODELS_DIR)
                )
            print("[STREAM] Tiny model loaded!", flush=True)
            self.model_tiny_error = None
        except Exception as e:
            print(f"[STREAM] Tiny model load error: {e}", flush=True)
            self.model_tiny_error = str(e)
            # Fallback dla faster-whisper na CPU, dla OpenVINO rzucamy błąd
            if not self.use_openvino and self.device == "cuda":
                print("[STREAM] Fallback to CPU...", flush=True)
                self.model_tiny = WhisperModel("tiny", device="cpu", compute_type="int8", download_root=str(MODELS_DIR))
                self.model_tiny_error = None

    def load_cascade_models(self, model_path=None):
        """Ładuje modele medium i large dla warstw 2 i 3."""
        # Medium
        if self.enable_medium and not self.model_medium:
            print(f"[STREAM] Loading medium model (OpenVINO={self.use_openvino})...", flush=True)
            try:
                if self.use_openvino:
                    self.model_medium = OpenVINOShim("medium", self.device)
                else:
                    if WhisperModel is None:
                        raise RuntimeError(f"Brak faster-whisper: {_FASTER_WHISPER_IMPORT_ERROR}")
                    self.model_medium = WhisperModel(
                        "medium",
                        device=self.device if self.device != "auto" else "cpu",
                        compute_type=self.compute_type,
                        download_root=str(MODELS_DIR)
                    )
                print("[STREAM] Medium model loaded!", flush=True)
                self.model_medium_error = None
            except Exception as e:
                print(f"[STREAM] Medium model error: {e}", flush=True)
                self.model_medium = None
                self.model_medium_error = str(e)

        # Large
        if self.enable_large and not self.model_large:
            print(f"[STREAM] Loading large model (OpenVINO={self.use_openvino})...", flush=True)
            try:
                if self.use_openvino:
                    self.model_large = OpenVINOShim("large-v3", self.device)
                else:
                    if WhisperModel is None:
                        raise RuntimeError(f"Brak faster-whisper: {_FASTER_WHISPER_IMPORT_ERROR}")
                    self.model_large = WhisperModel(
                        "large-v3",
                        device=self.device if self.device != "auto" else "cpu",
                        compute_type=self.compute_type,
                        download_root=str(MODELS_DIR)
                    )
                print("[STREAM] Large model loaded!", flush=True)
                self.model_large_error = None
            except Exception as e:
                print(f"[STREAM] Large model error: {e}", flush=True)
                self.model_large = None
                self.model_large_error = str(e)

    def start(self, callback_provisional, callback_improved=None, callback_final=None, external_backend=None):
        """
        Uruchamia streaming z wieloma callbackami.

        Args:
            callback_provisional: fn(text, start_sample, end_sample)
            callback_improved: fn(text, start_sample, end_sample)
            callback_final: fn(text, start_sample, end_sample)
            external_backend: Opcjonalny backend OpenVINO do finalizacji
        """
        self.callback_provisional = callback_provisional
        self.callback_improved = callback_improved or callback_provisional
        self.callback_final = callback_final or callback_improved or callback_provisional
        self.external_backend = external_backend

        if not self.model_tiny:
            self.load_model()

        self.is_running = True
        self.audio_queue = queue.Queue()

        # Reset buforów
        self.full_audio_buffer = []
        self.full_audio_samples = 0
        self.finalized_samples = 0
        self.last_improved_samples = 0
        self.last_improved_time = time.time()
        self._cancel_silence_timer()

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
        self._cancel_silence_timer()  # Anuluj timer ciszy
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

        # Detekcja ciszy - ASYNC TIMER
        rms = np.sqrt(np.mean(audio_data**2))
        if rms < 0.01:
            # Cisza - uruchom timer jeśli nie działa
            self._start_silence_timer()
            return
        else:
            # Dźwięk - anuluj timer
            self._cancel_silence_timer()

        try:
            segments, info = self.model_tiny.transcribe(
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
    
    def _start_silence_timer(self):
        """Uruchamia async timer dla ciszy (bulletproof - odpala się niezależnie)."""
        with self._silence_lock:
            if self.silence_timer is None:
                self.silence_timer = threading.Timer(
                    self.silence_threshold, 
                    self._on_silence_timeout
                )
                self.silence_timer.daemon = True
                self.silence_timer.start()
    
    def _cancel_silence_timer(self):
        """Anuluje timer ciszy."""
        with self._silence_lock:
            if self.silence_timer is not None:
                self.silence_timer.cancel()
                self.silence_timer = None
    
    def _on_silence_timeout(self):
        """Callback gdy minie 2s ciszy - GWARANTOWANE wywołanie."""
        with self._silence_lock:
            self.silence_timer = None
        
        if not self.is_running:
            return
        
        # Sprawdź czy jest coś do finalizacji
        if self.full_audio_samples <= self.finalized_samples:
            return
            
        print("[STREAM] Silence timeout - triggering final", flush=True)
        self._do_final_transcription()

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

                # WARSTWA 3 (Final) jest teraz obsługiwana przez async timer w _on_silence_timeout

            except Exception as e:
                print(f"[STREAM] Cascade error: {e}", flush=True)

    def _do_improved_transcription(self):
        """Warstwa 2: Re-transkrypcja z większym kontekstem (small model)."""
        if not self.enable_medium:
            return

        # Bierzemy audio od ostatniego improved do teraz
        if self.full_audio_samples <= self.last_improved_samples:
            return

        # Bierzemy ostatnie 10-15 sekund LUB od ostatniego improved
        max_samples = int(15.0 * self.sample_rate)
        # Startujemy od finalized (już zaakceptowane) - nie od last_improved
        # żeby nie tracić kontekstu
        start_sample = self.finalized_samples
        
        # Ale nie więcej niż 15 sekund wstecz
        if self.full_audio_samples - start_sample > max_samples:
            start_sample = self.full_audio_samples - max_samples

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
            duration = len(segment_audio) / self.sample_rate
            print(f"[STREAM] Improved: {duration:.1f}s audio (from sample {start_sample})", flush=True)

            # Użyj medium model jeśli dostępny, inaczej tiny
            model = self.model_medium if self.model_medium else self.model_tiny

            segments, info = model.transcribe(
                segment_audio,
                beam_size=3,  # Lepszy beam dla jakości
                language="pl",
                vad_filter=True
            )

            text = " ".join([s.text for s in segments]).strip()

            try:
                if text and self.callback_improved:
                    self.callback_improved(text, start_sample, self.full_audio_samples)
            except Exception as cb_err:
                print(f"[STREAM] Callback improved error: {cb_err}", flush=True)

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
            
            # Hybrid Mode: OpenVINO for finalization if available
            if self.external_backend and hasattr(self.external_backend, 'transcribe_raw'):
                print(f"[STREAM] Final (External OpenVINO): {duration:.1f}s audio", flush=True)
                # OpenVINO expects float32 array, which we have
                text = self.external_backend.transcribe_raw(segment_audio, language="pl")
            else:
                backend_name = "OpenVINOShim" if self.use_openvino else "Faster-Whisper"
                print(f"[STREAM] Final ({backend_name}): {duration:.1f}s audio", flush=True)
                # Użyj large model jeśli dostępny, inaczej medium, inaczej tiny
                if self.enable_large and self.model_large:
                    model = self.model_large
                    beam = 5
                elif self.enable_medium and self.model_medium:
                    model = self.model_medium
                    beam = 4
                else:
                    model = self.model_tiny
                    beam = 3

                segments, info = model.transcribe(
                    segment_audio,
                    beam_size=beam,
                    language="pl",
                    vad_filter=True,
                    word_timestamps=False
                )
                text = " ".join([s.text for s in segments]).strip()

            try:
                if text and self.callback_final:
                    self.callback_final(text, self.finalized_samples, self.full_audio_samples)
            except Exception as cb_err:
                print(f"[STREAM] Callback final error: {cb_err}", flush=True)

            # Oznacz jako sfinalizowane - ZAWSZE, nawet jak callback padnie
            self.finalized_samples = self.full_audio_samples

        except Exception as e:
            print(f"[STREAM] Final error: {e}", flush=True)

    def force_finalize(self):
        """Wymusza finalizację (np. przy kliknięciu STOP)."""
        self._do_final_transcription()
