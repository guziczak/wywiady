import math
import struct
import io
import winsound
import random
import threading

# Muzyka - climax motif (synteza do pamieci)
# REMASTERED EDITION: 44.1kHz + Reverb + Smoother Bowing

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
SR = 44100  # High Quality Audio

def generate_wav_memory():
    """Generuj WAV do pamieci - synteza skrzypiec z Reverbem"""
    sec_per_beat = 60 / TEMPO
    total_samples = int(17 * sec_per_beat * SR) # +1 sekunda na wybrzmienie reverbu
    audio = [0.0] * total_samples

    # 1. Synteza instrumentu
    for note, start_beat, dur_beats, vel in MOTIF:
        f = FREQ[note]
        start_sample = int(start_beat * sec_per_beat * SR)
        dur_sec = dur_beats * sec_per_beat
        num_samples = int(dur_sec * SR)

        phase = 0.0
        phase2 = 0.0
        
        # Parametry brzmienia
        vib_rate = 5.5
        vib_depth = 0.007
        
        # Pre-allocate note buffer
        note_samples = [0.0] * num_samples
        
        for i in range(num_samples):
            t = i / SR
            
            # Vibrato z opóźnieniem
            vib_amount = 0.0
            if t > 0.15:
                vib_fade = min(1.0, (t - 0.15) / 0.2)
                vib_amount = math.sin(2 * math.pi * vib_rate * t) * f * vib_depth * vib_fade

            freq_now = f + vib_amount
            phase += 2 * math.pi * freq_now / SR
            phase2 += 2 * math.pi * (freq_now * 2) / SR

            # Sawtooth wygładzony (mniej "buzz", więcej "tone")
            saw = 2 * ((phase / (2 * math.pi)) % 1) - 1
            harm2 = math.sin(phase2) * 0.4
            
            # Mieszanka: 60% piła, 40% sinusoida harmoniczna
            wave = (saw * 0.6) + (harm2 * 0.4)

            # Szum smyczka (bow noise) - tylko na ataku
            noise = 0.0
            if t < 0.1:
                noise_env = (1.0 - t/0.1)
                noise = (random.random() - 0.5) * 0.3 * noise_env

            # ADSR Envelope
            env = 1.0
            att_t = 0.08
            dec_t = 0.1
            rel_t = 0.15
            
            att_s = int(att_t * SR)
            dec_s = int(dec_t * SR)
            rel_s = int(rel_t * SR)

            if i < att_s:
                env = (i / att_s)
            elif i < att_s + dec_s:
                env = 1.0 - ((i - att_s) / dec_s) * 0.2 # decay to 0.8
            elif i > num_samples - rel_s:
                env = 0.8 * (num_samples - i) / rel_s
            else:
                env = 0.8

            note_samples[i] = (wave + noise) * env * vel * 0.15

        # Prosty Lowpass Filter dla każdej nuty (usuwa cyfrowe "ostrza")
        last_val = 0.0
        for i in range(len(note_samples)):
            val = note_samples[i]
            filtered = last_val * 0.6 + val * 0.4 # Mocniejsze filtrowanie
            note_samples[i] = filtered
            last_val = filtered

        # Dodaj do głównego bufora
        for i, s in enumerate(note_samples):
            if start_sample + i < total_samples:
                audio[start_sample + i] += s

    # 2. Efekt REVERB (prosty delay line)
    # Symulacja odbicia od ścian
    delay_ms = 180 # ms
    feedback = 0.35
    delay_samples = int(delay_ms * SR / 1000)
    
    # Tworzymy kopię do reverbu żeby nie zapętlić w nieskończoność przy edycji in-place
    reverb_buffer = list(audio)
    
    for i in range(len(audio)):
        # Pobierz próbkę z przeszłości
        if i >= delay_samples:
            reverb_signal = reverb_buffer[i - delay_samples] * feedback
            # Dodaj lekki filtr na odbiciu (ściany tłumią wysokie tony)
            if i > 0:
                 reverb_signal = (reverb_signal + reverb_buffer[i - delay_samples - 1] * feedback) * 0.5
            
            audio[i] += reverb_signal

    # 3. Normalizacja i konwersja
    max_val = max(abs(s) for s in audio) or 1
    # Lekki headroom (0.8)
    audio_int = [int((s / max_val) * 32767 * 0.9) for s in audio]

    buf = io.BytesIO()
    # RIFF/WAVE header for 44.1kHz mono 16-bit
    data_size = len(audio_int) * 2
    buf.write(b'RIFF')
    buf.write(struct.pack('<I', 36 + data_size))
    buf.write(b'WAVE')
    buf.write(b'fmt ')
    buf.write(struct.pack('<I', 16))
    buf.write(struct.pack('<H', 1))
    buf.write(struct.pack('<H', 1))
    buf.write(struct.pack('<I', SR))
    buf.write(struct.pack('<I', SR * 2))
    buf.write(struct.pack('<H', 2))
    buf.write(struct.pack('<H', 16))
    buf.write(b'data')
    buf.write(struct.pack('<I', data_size))
    
    # Pack data
    for sample in audio_int:
        buf.write(struct.pack('<h', sample))
        
    return buf.getvalue()

_WAV_CACHE = None

def play_climax_motif():
    global _WAV_CACHE
    try:
        if _WAV_CACHE is None:
            # Generowanie przy 44kHz może chwilę potrwać, ale robi się raz
            _WAV_CACHE = generate_wav_memory()
        winsound.PlaySound(_WAV_CACHE, winsound.SND_MEMORY)
    except Exception as e:
        print(f'[StartSound] Error: {e}')

def play_music_thread():
    threading.Thread(target=play_climax_motif, daemon=True).start()