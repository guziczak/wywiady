"""
Shimmer Animation Styles
CSS animacje dla efektu regeneracji tekstu.
"""

from nicegui import ui

# Flaga czy style już zostały dodane (singleton)
_styles_injected = False


SHIMMER_CSS = """
<style>
/* === SHIMMER ANIMATION === */

@keyframes shimmer-wave {
    0% {
        background-position: -200% 0;
    }
    100% {
        background-position: 200% 0;
    }
}

@keyframes shimmer-pulse {
    0%, 100% {
        opacity: 1;
    }
    50% {
        opacity: 0.7;
    }
}

@keyframes fade-in {
    from {
        opacity: 0;
        transform: translateY(2px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes text-reveal {
    0% {
        clip-path: inset(0 100% 0 0);
    }
    100% {
        clip-path: inset(0 0 0 0);
    }
}

/* === WORD TOKENS === */

.transcript-word {
    display: inline;
    padding: 1px 0;
    margin: 0 1px;
    border-radius: 3px;
    transition: all 0.3s ease;
}

/* Provisional - szary, italic */
.transcript-word.provisional {
    color: #6b7280; /* gray-500 - trochę ciemniejszy niż 400 */
    font-style: italic;
}

/* Final - czeka na walidację - wyraźny, ciemny, normalny */
.transcript-word.final {
    color: #374151; /* gray-700 */
    font-style: normal;
    font-weight: 500;
}

/* Validated - finalne, pogrubione, czarne */
.transcript-word.validated {
    color: #111827; /* gray-900 */
    font-weight: 600;
    font-style: normal;
}

/* === REGENERATING STATE (SEQUENCE) === */

/* Nowy styl dla całego ciągu zmienionych słów - Premium Shimmer */
.transcript-sequence.regenerating {
    display: inline-block; /* Lepiej dla box-modelu */
    position: relative;
    
    /* Eteryczne tło z błyskiem pod kątem */
    background: linear-gradient(
        120deg,
        rgba(255, 255, 255, 0) 20%,
        rgba(59, 130, 246, 0.1) 35%,
        rgba(147, 197, 253, 0.6) 50%, /* Jasny błysk (Cyan/Blue-300) */
        rgba(59, 130, 246, 0.1) 65%,
        rgba(255, 255, 255, 0) 80%
    );
    background-size: 250% 100%;
    
    /* Animacja przepływu światła */
    animation: shimmer-wave 2.2s cubic-bezier(0.4, 0, 0.2, 1) forwards;
    
    /* Wygląd kontenera */
    border-radius: 6px;
    padding: 0 4px;
    margin: 0 -2px; /* Lekka kompensacja paddingu */
    
    /* Delikatna poświata (Glow) */
    box-shadow: 0 0 15px rgba(59, 130, 246, 0.2), 
                inset 0 0 2px rgba(255, 255, 255, 0.5);
}

/* Słowa wewnątrz sekwencji - wyraźne, ciemnoniebieskie */
.transcript-sequence.regenerating .transcript-word {
    color: #1e40af; /* blue-800 - ciemniejszy dla kontrastu z jasnym tłem */
    font-weight: 500;
    background: none;
    animation: none;
    text-shadow: 0 1px 1px rgba(255, 255, 255, 0.8); /* Lekki obrys dla czytelności */
}

/* === OLD WORD STYLES (Cleanup or Fallback) === */

/* Efekt po zakończeniu animacji - zanikanie */
.transcript-sequence.regenerating.completed {
    animation: none;
    background: transparent;
    box-shadow: none;
    transition: all 0.8s ease-out;
}

.transcript-word.regenerating.completed.fade-out {
    background: transparent;
}

/* === ADDED WORDS (nowe) === */

.transcript-word.added {
    animation: fade-in 0.4s ease-out forwards;
    opacity: 0;
}

/* === MODIFIED WORDS === */

.transcript-word.modified {
    position: relative;
}

.transcript-word.modified::after {
    content: '';
    position: absolute;
    bottom: -2px;
    left: 0;
    right: 0;
    height: 2px;
    background: linear-gradient(90deg, #3b82f6, #8b5cf6);
    border-radius: 1px;
    animation: fade-in 0.3s ease-out forwards;
}

/* === SEGMENT CONTAINER === */

.transcript-segment {
    display: inline;
    line-height: 1.8;
}

.transcript-segment.regenerating-container {
    position: relative;
}

/* Gradient overlay na całym segmencie */
.transcript-segment.regenerating-container::before {
    content: '';
    position: absolute;
    top: -4px;
    left: -8px;
    right: -8px;
    bottom: -4px;
    background: linear-gradient(
        90deg,
        transparent 0%,
        rgba(59, 130, 246, 0.08) 50%,
        transparent 100%
    );
    background-size: 200% 100%;
    animation: shimmer-wave 2s ease-in-out infinite;
    border-radius: 8px;
    z-index: -1;
    pointer-events: none;
}

/* === LOADING PLACEHOLDER === */

.transcript-loading {
    display: inline-block;
    height: 1.2em;
    min-width: 60px;
    background: linear-gradient(
        90deg,
        #e5e7eb 0%,
        #f3f4f6 50%,
        #e5e7eb 100%
    );
    background-size: 200% 100%;
    animation: shimmer-wave 1.5s ease-in-out infinite;
    border-radius: 4px;
}

/* === SPEAKER INDICATORS === */

.transcript-word.speaker-doctor {
    border-left: 2px solid #3b82f6;
    padding-left: 4px;
    margin-left: 4px;
}

.transcript-word.speaker-patient {
    border-left: 2px solid #10b981;
    padding-left: 4px;
    margin-left: 4px;
}

/* === RESPONSIVE === */

@media (max-width: 640px) {
    .transcript-word {
        font-size: 0.95em;
    }
}

/* === ACCESSIBILITY === */

@media (prefers-reduced-motion: reduce) {
    .transcript-word.regenerating,
    .transcript-segment.regenerating-container::before,
    .transcript-loading {
        animation: none;
        background: rgba(59, 130, 246, 0.1);
    }

    .transcript-word.added {
        animation: none;
        opacity: 1;
    }
}
</style>
"""


def inject_shimmer_styles():
    """
    Wstrzykuje style CSS do strony.
    Bezpieczne do wielokrotnego wywołania (singleton).
    """
    global _styles_injected

    if _styles_injected:
        return

    ui.add_head_html(SHIMMER_CSS)
    _styles_injected = True
    print("[SHIMMER] Styles injected", flush=True)


def reset_styles_flag():
    """Reset flagi (np. przy nowej sesji/stronie)."""
    global _styles_injected
    _styles_injected = False
