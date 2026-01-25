import math
import struct
import io
import winsound
import random
import threading

# Muzyka - climax motif
# ULTRA FIDELITY EDITION: Stereo + Chorus + Multi-Harmonic Synthesis + Pro Reverb

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
SR = 44100

def generate_wav_memory():
    """Generuj WAV Stereo Hi-Fi do pamieci"""
    sec_per_beat = 60 / TEMPO
    total_samples = int(18 * sec_per_beat * SR)
    # Stereo buffers
    audio_l = [0.0] * total_samples
    audio_r = [0.0] * total_samples

    for note, start_beat, dur_beats, vel in MOTIF:
        f = FREQ[note]
        start_sample = int(start_beat * sec_per_beat * SR)
        dur_sec = dur_beats * sec_per_beat
        num_samples = int(dur_sec * SR)

        # Chorus effect - 3 sub-oscillators with slight detune
        # (Freq, Detune, PanL, PanR, PhaseOffset)
        layers = [
            (f, 1.0, 0.7, 0.3, 0),
            (f * 1.003, 1.0, 0.2, 0.8, 0.5),
            (f * 0.997, 1.0, 0.5, 0.5, 1.2)
        ]

        for i in range(num_samples):
            t = i / SR
            
            # Envelope (Exponential for smoothness)
            env = 1.0
            att_t = 0.1
            rel_t = 0.2
            att_s = int(att_t * SR)
            rel_s = int(rel_t * SR)
            
            if i < att_s:
                env = math.pow(i / att_s, 2)
            elif i > num_samples - rel_s:
                env = math.pow((num_samples - i) / rel_s, 2)
            
            # Vibrato
            vib = math.sin(2 * math.pi * 5.6 * t) * (f * 0.008) if t > 0.1 else 0

            sample_l = 0.0
            sample_r = 0.0

            for freq, detune, pan_l, pan_r, p_off in layers:
                phase = 2 * math.pi * (freq + vib) * t + p_off
                
                # Multi-Harmonic synthesis (Violin-like spectrum)
                # Harmonics: 1, 2, 3, 4
                wave = (math.sin(phase) * 1.0 + 
                        math.sin(phase * 2) * 0.5 + 
                        math.sin(phase * 3) * 0.3 + 
                        math.sin(phase * 4) * 0.1)
                
                s = wave * env * vel * 0.1
                sample_l += s * pan_l
                sample_r += s * pan_r

            audio_l[start_sample + i] += sample_l
            audio_r[start_sample + i] += sample_r

    # Pro Stereo Reverb (Schroeder-inspired)
    def apply_reverb(buf, delay_ms, fb):
        ds = int(delay_ms * SR / 1000)
        out = list(buf)
        for i in range(ds, len(out)):
            out[i] += out[i-ds] * fb
        return out

    # Różne czasy delaya dla L i R tworzą szeroką panoramę
    audio_l = apply_reverb(audio_l, 160, 0.4)
    audio_r = apply_reverb(audio_r, 195, 0.38)

    # Mix down to 16-bit PCM Stereo
    max_val = 0
    for i in range(total_samples):
        max_val = max(max_val, abs(audio_l[i]), abs(audio_r[i]))
    max_val = max_val or 1
    
    buf = io.BytesIO()
    # RIFF/WAVE Stereo 44.1kHz
    data_size = total_samples * 2 * 2 # 2 channels * 2 bytes
    buf.write(b'RIFF')
    buf.write(struct.pack('<I', 36 + data_size))
    buf.write(b'WAVE')
    buf.write(b'fmt ')
    buf.write(struct.pack('<I', 16))
    buf.write(struct.pack('<H', 1)) # PCM
    buf.write(struct.pack('<H', 2)) # Stereo
    buf.write(struct.pack('<I', SR))
    buf.write(struct.pack('<I', SR * 4)) # Byte rate
    buf.write(struct.pack('<H', 4)) # Block align
    buf.write(struct.pack('<H', 16)) # Bits per sample
    buf.write(b'data')
    buf.write(struct.pack('<I', data_size))

    for i in range(total_samples):
        l = int((audio_l[i] / max_val) * 32767 * 0.8)
        r = int((audio_r[i] / max_val) * 32767 * 0.8)
        buf.write(struct.pack('<hh', l, r))

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
