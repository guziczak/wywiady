"""
QA Pair Styles - animacje 3D dla stołu Q+A.

Zawiera:
- .qa-table-3d - perspektywa stołu (1200px, gradient tła)
- @keyframes pairThrow - rzut pary (1.0s, translateZ, rotateX/Y)
- .qa-pair-card:hover - 3D lift (translateY -12px, translateZ 30px)
- .qa-pair-rotate-1..6 - warianty rotacji
"""

from nicegui import ui


_QA_PAIR_STYLES_INJECTED = False


def inject_qa_pair_styles():
    """Wstrzykuje style animacji par Q+A do strony (singleton)."""
    global _QA_PAIR_STYLES_INJECTED
    if _QA_PAIR_STYLES_INJECTED:
        return
    _QA_PAIR_STYLES_INJECTED = True

    ui.add_head_html('''
    <style>
    /* === 3D TABLE PERSPECTIVE === */
    .qa-table-3d {
        perspective: 1200px;
        perspective-origin: center center;
        background: linear-gradient(
            145deg,
            rgba(236, 253, 245, 0.8) 0%,
            rgba(209, 250, 229, 0.6) 25%,
            rgba(167, 243, 208, 0.4) 50%,
            rgba(209, 250, 229, 0.6) 75%,
            rgba(236, 253, 245, 0.8) 100%
        );
        border: 2px solid rgba(16, 185, 129, 0.2);
        border-radius: 16px;
        box-shadow:
            inset 0 2px 8px rgba(255,255,255,0.6),
            inset 0 -2px 8px rgba(16, 185, 129, 0.1),
            0 4px 16px rgba(0,0,0,0.05);
        transform-style: preserve-3d;
    }

    /* === PAIR THROW ANIMATION === */
    @keyframes pairThrow {
        0% {
            transform: translateY(-150px) translateZ(100px) rotateX(45deg) rotateY(-15deg) scale(0.6);
            opacity: 0;
            box-shadow: 0 30px 60px rgba(0,0,0,0.4);
        }
        40% {
            transform: translateY(10px) translateZ(40px) rotateX(-8deg) rotateY(5deg) scale(1.05);
            opacity: 1;
            box-shadow: 0 25px 50px rgba(0,0,0,0.35);
        }
        70% {
            transform: translateY(-5px) translateZ(20px) rotateX(3deg) rotateY(-2deg) scale(1.02);
            box-shadow: 0 15px 30px rgba(0,0,0,0.25);
        }
        100% {
            transform: translateY(0) translateZ(0) rotateX(0) rotateY(0) scale(1);
            opacity: 1;
            box-shadow: 0 6px 16px rgba(0,0,0,0.15);
        }
    }

    .qa-pair-card {
        transform-style: preserve-3d;
        backface-visibility: hidden;
        transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1),
                    box-shadow 0.35s ease;
    }

    .qa-pair-card.throwing-pair {
        animation: pairThrow 1.0s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    }

    /* === 3D HOVER LIFT === */
    .qa-pair-card:hover {
        transform: translateY(-12px) translateZ(30px) rotateX(5deg);
        box-shadow:
            0 20px 40px rgba(0,0,0,0.2),
            0 0 0 2px rgba(16, 185, 129, 0.3);
        z-index: 10;
    }

    .qa-pair-card:active {
        transform: translateY(-6px) translateZ(15px) rotateX(2deg) scale(0.98);
        box-shadow: 0 10px 20px rgba(0,0,0,0.15);
    }

    /* === ROTATION VARIANTS === */
    .qa-pair-rotate-1 { transform: rotate(-3deg); }
    .qa-pair-rotate-2 { transform: rotate(2deg); }
    .qa-pair-rotate-3 { transform: rotate(-1.5deg); }
    .qa-pair-rotate-4 { transform: rotate(2.5deg); }
    .qa-pair-rotate-5 { transform: rotate(-2deg); }
    .qa-pair-rotate-6 { transform: rotate(1deg); }

    /* Hover override - zachowaj rotację przy hover */
    .qa-pair-rotate-1:hover { transform: rotate(-3deg) translateY(-12px) translateZ(30px); }
    .qa-pair-rotate-2:hover { transform: rotate(2deg) translateY(-12px) translateZ(30px); }
    .qa-pair-rotate-3:hover { transform: rotate(-1.5deg) translateY(-12px) translateZ(30px); }
    .qa-pair-rotate-4:hover { transform: rotate(2.5deg) translateY(-12px) translateZ(30px); }
    .qa-pair-rotate-5:hover { transform: rotate(-2deg) translateY(-12px) translateZ(30px); }
    .qa-pair-rotate-6:hover { transform: rotate(1deg) translateY(-12px) translateZ(30px); }

    /* === PAIR CARD Q+A SECTIONS === */
    .qa-pair-section-q {
        background: linear-gradient(135deg,
            rgba(59, 130, 246, 0.1) 0%,
            rgba(59, 130, 246, 0.05) 100%);
        border-left: 3px solid rgba(59, 130, 246, 0.5);
        padding: 6px 8px;
        border-radius: 4px;
    }

    .qa-pair-section-a {
        background: linear-gradient(135deg,
            rgba(16, 185, 129, 0.1) 0%,
            rgba(16, 185, 129, 0.05) 100%);
        border-left: 3px solid rgba(16, 185, 129, 0.5);
        padding: 6px 8px;
        border-radius: 4px;
    }

    /* === STAGGERED ENTRY === */
    .qa-pair-stagger-1 { animation-delay: 0ms; }
    .qa-pair-stagger-2 { animation-delay: 80ms; }
    .qa-pair-stagger-3 { animation-delay: 160ms; }
    .qa-pair-stagger-4 { animation-delay: 240ms; }
    .qa-pair-stagger-5 { animation-delay: 320ms; }
    .qa-pair-stagger-6 { animation-delay: 400ms; }

    /* === EDIT MODAL STYLES === */
    .qa-edit-modal {
        backdrop-filter: blur(8px);
    }

    .qa-edit-modal .q-card {
        box-shadow: 0 25px 50px rgba(0,0,0,0.25);
        border-radius: 16px;
    }

    /* === UNDO BUTTON === */
    .qa-undo-btn {
        transition: all 0.2s ease;
    }

    .qa-undo-btn:hover {
        transform: scale(1.05);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }

    /* === EMPTY TABLE STATE === */
    .qa-table-empty {
        border: 2px dashed rgba(16, 185, 129, 0.3);
        background: rgba(236, 253, 245, 0.3);
    }
    </style>
    ''')
