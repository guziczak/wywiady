"""
Card Throw Styles - animacje 3D dla gamifikacji Q+A.

Zawiera:
- cardThrow: animacja rzutu karty na stół (0.8s)
- perspective 3D dla efektu głębi
- hover effects na kartach
- progress pulse animation
"""

from nicegui import ui


_CARD_THROW_STYLES_INJECTED = False


def inject_card_throw_styles():
    """Wstrzykuje style animacji kart do strony (singleton)."""
    global _CARD_THROW_STYLES_INJECTED
    if _CARD_THROW_STYLES_INJECTED:
        return
    _CARD_THROW_STYLES_INJECTED = True

    ui.add_head_html('''
    <style>
    /* === 3D CARD THROW ANIMATION === */
    @keyframes cardThrow {
        0% {
            transform: translateY(-100px) rotateX(60deg) scale(0.8);
            opacity: 0;
        }
        50% {
            transform: translateY(5px) rotateX(-5deg) scale(1.02);
            box-shadow: 0 20px 40px rgba(0,0,0,0.3);
        }
        100% {
            transform: translateY(0) rotateX(0) scale(1);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
    }

    .qa-collection-container {
        perspective: 1000px;
        perspective-origin: center center;
    }

    .qa-card {
        transform-style: preserve-3d;
        backface-visibility: hidden;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }

    .qa-card.throwing {
        animation: cardThrow 0.8s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    }

    .qa-card:hover {
        transform: translateY(-4px) rotateX(2deg);
        box-shadow: 0 12px 24px rgba(0,0,0,0.2);
    }

    /* === PROGRESS BADGE PULSE === */
    @keyframes progressPulse {
        0%, 100% {
            transform: scale(1);
            box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4);
        }
        50% {
            transform: scale(1.05);
            box-shadow: 0 0 0 8px rgba(59, 130, 246, 0);
        }
    }

    .qa-progress-badge {
        transition: all 0.3s ease;
    }

    .qa-progress-badge.pulse {
        animation: progressPulse 0.6s ease-out;
    }

    /* === COLLECTION TABLE GRADIENT === */
    .qa-collection-table {
        background: linear-gradient(
            135deg,
            rgba(241, 245, 249, 0.9) 0%,
            rgba(226, 232, 240, 0.9) 50%,
            rgba(241, 245, 249, 0.9) 100%
        );
        border: 2px solid rgba(148, 163, 184, 0.3);
        border-radius: 16px;
        box-shadow:
            inset 0 2px 4px rgba(255,255,255,0.5),
            0 4px 12px rgba(0,0,0,0.05);
    }

    /* === CARD ROTATION VARIANTS === */
    .qa-card-rotate-1 { transform: rotate(-2deg); }
    .qa-card-rotate-2 { transform: rotate(1deg); }
    .qa-card-rotate-3 { transform: rotate(-1deg); }
    .qa-card-rotate-4 { transform: rotate(2deg); }
    .qa-card-rotate-5 { transform: rotate(-1.5deg); }

    /* === MATCH CELEBRATION === */
    @keyframes matchCelebrate {
        0% {
            transform: scale(1);
        }
        25% {
            transform: scale(1.1);
        }
        50% {
            transform: scale(0.95);
        }
        75% {
            transform: scale(1.05);
        }
        100% {
            transform: scale(1);
        }
    }

    .qa-match-celebrate {
        animation: matchCelebrate 0.5s ease-out;
    }

    /* === EMPTY STATE PLACEHOLDER === */
    .qa-empty-slot {
        border: 2px dashed rgba(148, 163, 184, 0.4);
        border-radius: 12px;
        background: rgba(241, 245, 249, 0.5);
        transition: all 0.3s ease;
    }

    .qa-empty-slot:hover {
        border-color: rgba(59, 130, 246, 0.4);
        background: rgba(59, 130, 246, 0.05);
    }

    /* === STAGGERED ENTRY FOR INITIAL CARDS === */
    .qa-card-stagger-1 { animation-delay: 0ms; }
    .qa-card-stagger-2 { animation-delay: 100ms; }
    .qa-card-stagger-3 { animation-delay: 200ms; }
    .qa-card-stagger-4 { animation-delay: 300ms; }
    .qa-card-stagger-5 { animation-delay: 400ms; }

    /* === TOOLTIP FOR QA CARD === */
    .qa-card-tooltip {
        position: absolute;
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        padding: 8px 12px;
        background: rgba(30, 41, 59, 0.95);
        color: white;
        border-radius: 8px;
        font-size: 12px;
        white-space: nowrap;
        opacity: 0;
        pointer-events: none;
        transition: opacity 0.2s ease, transform 0.2s ease;
        z-index: 100;
    }

    .qa-card:hover .qa-card-tooltip {
        opacity: 1;
        transform: translateX(-50%) translateY(-8px);
    }
    </style>
    ''')
