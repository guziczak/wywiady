"""
Animation Styles - style CSS dla animacji w Live Interview.

Zawiera animacje:
- slide-up: wjazd od dołu
- fade-in: płynne pojawienie
- pulse-subtle: subtelne pulsowanie
- cross-dissolve: przejście fade
"""

from nicegui import ui


_ANIMATION_STYLES_INJECTED = False


def inject_animation_styles():
    """Wstrzykuje style animacji do strony (singleton)."""
    global _ANIMATION_STYLES_INJECTED
    if _ANIMATION_STYLES_INJECTED:
        return
    _ANIMATION_STYLES_INJECTED = True

    ui.add_head_html('''
    <style>
    /* === SLIDE UP === */
    @keyframes slideUp {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    .animate-slide-up {
        animation: slideUp 0.3s ease-out forwards;
    }

    /* === FADE IN === */
    @keyframes fadeIn {
        from {
            opacity: 0;
        }
        to {
            opacity: 1;
        }
    }

    .animate-fade-in {
        animation: fadeIn 0.4s ease-out forwards;
    }

    /* Staggered fade-in for children */
    .animate-fade-in-stagger > *:nth-child(1) { animation-delay: 0ms; }
    .animate-fade-in-stagger > *:nth-child(2) { animation-delay: 100ms; }
    .animate-fade-in-stagger > *:nth-child(3) { animation-delay: 200ms; }
    .animate-fade-in-stagger > *:nth-child(4) { animation-delay: 300ms; }

    /* === PULSE SUBTLE === */
    @keyframes pulseSubtle {
        0%, 100% {
            box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4);
        }
        50% {
            box-shadow: 0 0 0 8px rgba(59, 130, 246, 0);
        }
    }

    .animate-pulse-subtle {
        animation: pulseSubtle 2s ease-in-out infinite;
    }

    /* === CROSS DISSOLVE === */
    @keyframes crossDissolveOut {
        from {
            opacity: 1;
            transform: scale(1);
        }
        to {
            opacity: 0;
            transform: scale(0.95);
        }
    }

    @keyframes crossDissolveIn {
        from {
            opacity: 0;
            transform: scale(1.05);
        }
        to {
            opacity: 1;
            transform: scale(1);
        }
    }

    .animate-dissolve-out {
        animation: crossDissolveOut 0.2s ease-out forwards;
    }

    .animate-dissolve-in {
        animation: crossDissolveIn 0.3s ease-out forwards;
    }

    /* === SLIDE FROM LEFT (for diarization segments) === */
    @keyframes slideFromLeft {
        from {
            opacity: 0;
            transform: translateX(-20px);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }

    .animate-slide-left {
        animation: slideFromLeft 0.3s ease-out forwards;
    }

    /* Staggered slide for segments */
    .diarized-segment {
        animation: slideFromLeft 0.3s ease-out forwards;
    }

    .diarized-segment:nth-child(1) { animation-delay: 0ms; }
    .diarized-segment:nth-child(2) { animation-delay: 50ms; }
    .diarized-segment:nth-child(3) { animation-delay: 100ms; }
    .diarized-segment:nth-child(4) { animation-delay: 150ms; }
    .diarized-segment:nth-child(5) { animation-delay: 200ms; }
    .diarized-segment:nth-child(6) { animation-delay: 250ms; }
    .diarized-segment:nth-child(7) { animation-delay: 300ms; }
    .diarized-segment:nth-child(8) { animation-delay: 350ms; }
    .diarized-segment:nth-child(9) { animation-delay: 400ms; }
    .diarized-segment:nth-child(10) { animation-delay: 450ms; }

    /* === PROCESSING SHIMMER === */
    @keyframes processingShimmer {
        0% {
            background-position: -200% 0;
        }
        100% {
            background-position: 200% 0;
        }
    }

    .animate-processing {
        background: linear-gradient(
            90deg,
            transparent 0%,
            rgba(59, 130, 246, 0.1) 50%,
            transparent 100%
        );
        background-size: 200% 100%;
        animation: processingShimmer 1.5s ease-in-out infinite;
    }

    /* === BADGE GLOW === */
    @keyframes badgeGlow {
        0%, 100% {
            box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4);
        }
        50% {
            box-shadow: 0 0 8px 2px rgba(16, 185, 129, 0.2);
        }
    }

    .animate-badge-glow {
        animation: badgeGlow 2s ease-in-out infinite;
    }

    /* === TRANSITION UTILITIES === */
    .transition-all-smooth {
        transition: all 0.3s ease-out;
    }

    .transition-opacity-smooth {
        transition: opacity 0.3s ease-out;
    }

    .transition-transform-smooth {
        transition: transform 0.3s ease-out;
    }
    </style>
    ''')
