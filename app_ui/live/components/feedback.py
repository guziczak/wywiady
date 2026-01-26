"""
Live feedback (sound + haptics) for the /live desk.
"""

from nicegui import ui


def inject_feedback_script() -> None:
    """Injects a tiny feedback helper for sound + haptics (singleton)."""
    ui.add_head_html(
        '''
        <script>
        (function() {
          if (window.liveFeedback) return;

          const prefersReducedMotion = window.matchMedia
            && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

          const state = {
            enabled: true,
            audioReady: false,
            audioContext: null,
            lastAt: 0,
          };

          function ensureContext() {
            if (!state.audioContext) {
              const Ctx = window.AudioContext || window.webkitAudioContext;
              if (!Ctx) return false;
              state.audioContext = new Ctx();
            }
            if (state.audioContext.state === 'suspended') {
              state.audioContext.resume().catch(() => {});
            }
            state.audioReady = state.audioContext.state === 'running';
            return state.audioReady;
          }

          function warmup() {
            if (!state.enabled) return;
            ensureContext();
          }

          document.addEventListener('pointerdown', warmup, { passive: true });
          document.addEventListener('keydown', warmup, { passive: true });

          function playTone({ freq = 520, duration = 0.08, type = 'sine', gain = 0.045 } = {}) {
            if (!state.enabled) return;
            if (!ensureContext()) return;
            const now = state.audioContext.currentTime;
            const osc = state.audioContext.createOscillator();
            const amp = state.audioContext.createGain();
            osc.type = type;
            osc.frequency.value = freq;
            amp.gain.value = 0;
            osc.connect(amp);
            amp.connect(state.audioContext.destination);
            amp.gain.linearRampToValueAtTime(gain, now + 0.01);
            amp.gain.exponentialRampToValueAtTime(0.001, now + duration);
            osc.start(now);
            osc.stop(now + duration + 0.02);
          }

          function play(type = 'qa') {
            if (!state.enabled) return;
            const now = Date.now();
            if (now - state.lastAt < 350) return;
            state.lastAt = now;
            if (type === 'qa') {
              playTone({ freq: 620, duration: 0.07, type: 'triangle', gain: 0.04 });
            } else if (type === 'success') {
              playTone({ freq: 720, duration: 0.1, type: 'sine', gain: 0.05 });
              setTimeout(() => playTone({ freq: 900, duration: 0.08, type: 'sine', gain: 0.035 }), 90);
            }
          }

          function vibrate(pattern = [18]) {
            if (!state.enabled) return;
            if (prefersReducedMotion) return;
            if (navigator.vibrate) {
              navigator.vibrate(pattern);
            }
          }

          function setEnabled(enabled) {
            state.enabled = !!enabled;
            if (!state.enabled && state.audioContext) {
              state.audioContext.suspend().catch(() => {});
            }
          }

          window.liveFeedback = {
            play,
            vibrate,
            setEnabled,
            isEnabled: () => state.enabled,
            warmup,
          };
        })();
        </script>
        '''
    )
