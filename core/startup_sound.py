import math
import struct
import io
import winsound
import random
import threading

# Muzyka - climax motif
# CLEAN VERSION: 44.1kHz Mono, Smoothed Sawtooth (No artifacts, no horror)

MOTIF = [
    ('E4', 0, 4, 0.65), ('A4', 0, 4, 0.7), ('E5', 0, 1.5, 1.0),
    ('D5', 1.5, 0.5, 0.92), ('C5', 2, 1, 0.98), ('B4', 3, 0.5, 0.90), ('A4', 3.5, 0.5, 0.88),
    ('G4', 4, 0.75, 0.90), ('A4', 4.75, 0.25, 0.86), ('B4', 5, 1.5, 0.98),
    ('C5', 6.5, 1, 0.95), ('D5', 7.5, 0.5, 0.92),
    ('E5', 8, 0.75, 1.0), ('F5', 8.75, 0.25, 0.96), ('G5', 9, 1, 1.0),
    ('A5', 10, 1, 1.0), ('G5', 11, 0.5, 0.98), ('F5', 11.5, 0.5, 0.92),
    ('E5', 12, 1.5, 1.0), ('D5', 13.5, 0.5, 0.92),
    ('C5', 14, 0.5, 0.96), ('B4', 14.5, 0.5, 0.90), ('A4', 15, 1, 0.98)
]
FREQ = {'G4': 392, 'A4': 440, 'B4': 494, 'C5': 523, 'D5': 587,
        'E4': 330, 'E5': 659, 'F5': 698, 'G5': 784, 'A5': 880}
TEMPO = 103
SR = 44100  # High Quality, ale Mono

def generate_wav_memory():
    """Generuj WAV Mono Clean"""
    sec_per_beat = 60 / TEMPO
    total_samples = int(16 * sec_per_beat * SR)
    audio = [0.0] * total_samples

    for note, start_beat, dur_beats, vel in MOTIF:
        f = FREQ[note]
        start_sample = int(start_beat * sec_per_beat * SR)
        dur_sec = dur_beats * sec_per_beat
        num_samples = int(dur_sec * SR)

        phase = 0.0
        phase2 = 0.0
        
        # Wygładzamy parametry vibrato
        vib_rate = 5.5
        vib_depth = 0.006

        note_samples = [0.0] * num_samples

        for i in range(num_samples):
            t = i / SR

            # Vibrato
            vib_amount = 0.0
            if t > 0.15:
                # Płynniejsze wejście vibrato
                vib_fade = min(1.0, (t - 0.15) / 0.2)
                vib_amount = math.sin(2 * math.pi * vib_rate * t) * f * vib_depth * vib_fade

            # Minimalny jitter dla naturalności
            jitter = (random.random() - 0.5) * f * 0.001

            freq_now = f + vib_amount + jitter
            phase += 2 * math.pi * freq_now / SR
            phase2 += 2 * math.pi * (freq_now * 2) / SR

            # Sawtooth + 2nd Harmonic (klasyczne brzmienie skrzypiec)
            saw = 2 * ((phase / (2 * math.pi)) % 1) - 1
            harm2 = math.sin(phase2) * 0.3
            wave = saw * 0.7 + harm2

            # Bow noise (szum smyczka) - delikatniejszy
            bow_noise = 0.0
            if t < 0.08:
                noise_amount = (1 - t / 0.08) * 0.1
                bow_noise = (random.random() - 0.5) * noise_amount

            # Envelope ADSR
            env = 1.0
            att = int(0.04 * SR)
            decay = int(0.08 * SR)
            rel = int(0.12 * SR)

            if i < att:
                env = (i / att) * 1.1
            elif i < att + decay:
                decay_pos = (i - att) / decay
                env = 1.1 - decay_pos * 0.15
            elif i > num_samples - rel:
                env = 0.95 * (num_samples - i) / rel
            else:
                env = 0.95

            note_samples[i] = (wave + bow_noise) * env * vel * 0.12

        # Lowpass filter (prosty filtr dolnoprzepustowy)
        # Usuwa ostre cyfrowe krawędzie ("tekturę")
        last_val = 0.0
        for i in range(len(note_samples)):
            val = note_samples[i]
            # Mocniejszy filtr dla 44kHz
            filtered = last_val * 0.7 + val * 0.3
            note_samples[i] = filtered
            last_val = filtered

        # Mix do głównego bufora
        for i, s in enumerate(note_samples):
            if start_sample + i < total_samples:
                audio[start_sample + i] += s

    # Normalizacja
    max_val = max(abs(s) for s in audio) or 1
    # Konwersja do 16-bit PCM Mono
    audio_int = [int((s / max_val) * 32767 * 0.9) for s in audio]

    buf = io.BytesIO()
    data_size = len(audio_int) * 2
    buf.write(b'RIFF')
    buf.write(struct.pack('<I', 36 + data_size))
    buf.write(b'WAVE')
    buf.write(b'fmt ')
    buf.write(struct.pack('<I', 16))
    buf.write(struct.pack('<H', 1))   # PCM
    buf.write(struct.pack('<H', 1))   # Mono
    buf.write(struct.pack('<I', SR))
    buf.write(struct.pack('<I', SR * 2))
    buf.write(struct.pack('<H', 2))
    buf.write(struct.pack('<H', 16))
    buf.write(b'data')
    buf.write(struct.pack('<I', data_size))
    for s in audio_int:
        buf.write(struct.pack('<h', s))
    return buf.getvalue()

_WAV_CACHE = None

def play_climax_motif():
    global _WAV_CACHE
    try:
        if _WAV_CACHE is None:
            _WAV_CACHE = generate_wav_memory()
        winsound.PlaySound(_WAV_CACHE, winsound.SND_MEMORY)
    except Exception as e:
        print(f'[StartSound] Error: {e}')

def play_music_thread():
    threading.Thread(target=play_climax_motif, daemon=True).start()