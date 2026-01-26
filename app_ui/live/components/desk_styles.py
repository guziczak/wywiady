"""
Live Desk Styles - immersive layout for /live.

Keeps styles scoped to the live desk container.
"""

from nicegui import ui
import json

_DESK_STYLE_ID = "live-desk-styles"


def inject_desk_styles() -> None:
    """Injects desk-first layout styles (client-safe)."""
    css = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Fraunces:opsz,wght@9..144,600&display=swap');

.live-mode {
    --desk-ink: #0b1324;
    --desk-ink-soft: #1f2a44;
    --desk-accent: #f97316;
    --desk-accent-2: #22c55e;
    --desk-surface-1: #fdf9f2;
    --desk-surface-2: #efe7d7;
    --desk-surface-3: #e5dbc6;
    --desk-glass: rgba(255, 255, 255, 0.78);
    --desk-glass-strong: rgba(255, 255, 255, 0.92);
    font-family: "Space Grotesk", "Segoe UI", sans-serif;
    color: var(--desk-ink);
}

.live-desk-shell {
    position: relative;
    width: 100%;
    max-width: 1400px;
    margin: 0 auto;
    height: calc(100vh - 128px);
    padding: 12px 16px 18px;
    overflow: hidden;
}

@media (max-width: 900px) {
    .live-desk-shell {
        height: calc(100vh - 148px);
        padding: 10px;
    }
}

.qa-collection-container--immersive {
    height: 100%;
    position: relative;
}

.qa-stage-wrapper--immersive {
    position: relative;
    height: 100%;
    border-radius: 28px;
    overflow: hidden;
    background:
        radial-gradient(1200px 600px at 18% -20%, rgba(255, 193, 120, 0.35), transparent 60%),
        radial-gradient(900px 600px at 85% 120%, rgba(148, 163, 184, 0.35), transparent 60%),
        linear-gradient(145deg, var(--desk-surface-1) 0%, var(--desk-surface-2) 45%, var(--desk-surface-3) 100%);
    border: 1px solid rgba(148, 163, 184, 0.4);
    box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.7),
        0 26px 70px rgba(15, 23, 42, 0.18);
}

.qa-stage-wrapper--immersive::after {
    content: "";
    position: absolute;
    inset: 0;
    background:
        repeating-linear-gradient(45deg, rgba(15, 23, 42, 0.06) 0 1px, transparent 1px 8px),
        radial-gradient(600px 400px at 30% 20%, rgba(255, 255, 255, 0.6), transparent 70%);
    opacity: 0.08;
    pointer-events: none;
}

.desk-pulse {
    animation: deskPulse 0.6s ease-out;
}

@keyframes deskPulse {
    0% { box-shadow: 0 0 0 rgba(249, 115, 22, 0.0); }
    50% { box-shadow: 0 0 40px rgba(249, 115, 22, 0.25); }
    100% { box-shadow: 0 0 0 rgba(249, 115, 22, 0.0); }
}

.qa-desk-hud {
    position: absolute;
    top: 14px;
    left: 16px;
    right: 16px;
    z-index: 8;
    display: flex;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    align-items: flex-start;
    row-gap: 8px;
}

.qa-desk-hud > .qa-hud-card {
    max-width: 100%;
}

.qa-hud-card {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border-radius: 14px;
    background: var(--desk-glass);
    border: 1px solid rgba(148, 163, 184, 0.4);
    box-shadow: 0 10px 30px rgba(15, 23, 42, 0.15);
    backdrop-filter: blur(12px);
}

.qa-desk-hud .q-label {
    font-family: "Fraunces", serif;
    letter-spacing: 0.04em;
}

.live-overlay {
    position: absolute;
    z-index: 20;
    opacity: 0;
    transform: translateY(8px);
    transition: opacity 0.25s ease, transform 0.25s ease;
    pointer-events: none;
}

.live-overlay.is-peek { --overlay-height: min(32vh, 320px); }
.live-overlay.is-full { --overlay-height: min(72vh, 640px); }

.live-overlay.is-open {
    opacity: 1;
    transform: translateY(0);
    pointer-events: auto;
}

.live-overlay--spotlight {
    top: 16px;
    left: 16px;
    width: min(560px, 92vw);
}

.live-overlay--transcript {
    left: 16px;
    bottom: 86px;
    width: min(420px, 94vw);
    height: var(--overlay-height, min(45vh, 420px));
}

.live-overlay--drawer {
    right: 16px;
    bottom: 86px;
    width: min(460px, 94vw);
    height: var(--overlay-height, min(60vh, 520px));
    transform: translateY(12px);
}

.live-overlay--pipeline {
    right: 16px;
    top: 16px;
    width: min(360px, 94vw);
}

@media (max-width: 900px) {
    .live-overlay--spotlight { width: min(92vw, 520px); }
    .live-overlay--transcript,
    .live-overlay--drawer,
    .live-overlay--pipeline {
        left: 50%;
        right: auto;
        transform: translate(-50%, 8px);
        width: min(94vw, 520px);
        border-radius: 22px;
    }
    .live-overlay--transcript { bottom: 92px; }
    .live-overlay--drawer { bottom: 92px; height: min(62vh, 520px); }
    .live-overlay--pipeline { top: auto; bottom: 92px; }

    .live-desk-dock {
        width: calc(100% - 20px);
        flex-wrap: wrap;
        justify-content: center;
        gap: 10px;
        padding: 10px 12px;
    }

    .live-desk-btn {
        min-height: 44px;
        padding: 0 14px !important;
        font-size: 13px !important;
    }

    .live-desk-chip {
        font-size: 10px !important;
    }

    .live-overlay.is-peek { --overlay-height: min(28vh, 240px); }
    .live-overlay.is-full { --overlay-height: min(78vh, 620px); }
}

.overlay-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 6px 8px;
    margin-bottom: 6px;
    border-radius: 12px;
    background: rgba(15, 23, 42, 0.08);
}

.overlay-title {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: rgba(15, 23, 42, 0.6);
}

.overlay-btn {
    color: rgba(15, 23, 42, 0.6) !important;
}

.live-panel {
    background: var(--desk-glass-strong) !important;
    border: 1px solid rgba(148, 163, 184, 0.45) !important;
    box-shadow: 0 20px 40px rgba(15, 23, 42, 0.18);
    backdrop-filter: blur(12px);
}

.live-prompter-panel {
    border-top: 0 !important;
    border-radius: 18px !important;
}

.live-transcript-panel {
    border-radius: 18px !important;
}

.live-active-card {
    border-radius: 18px !important;
    box-shadow: 0 20px 40px rgba(15, 23, 42, 0.18);
}

.live-pipeline-panel {
    border-radius: 18px !important;
    width: 100% !important;
    max-width: none !important;
    margin: 0 !important;
}

.live-desk-dock {
    position: absolute;
    left: 50%;
    bottom: 18px;
    transform: translateX(-50%);
    z-index: 22;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    border-radius: 18px;
    background: rgba(15, 23, 42, 0.82);
    color: #e2e8f0;
    border: 1px solid rgba(148, 163, 184, 0.35);
    box-shadow: 0 18px 40px rgba(15, 23, 42, 0.35);
    backdrop-filter: blur(12px);
}

.live-desk-btn {
    color: #e2e8f0 !important;
    border-radius: 12px !important;
    text-transform: none !important;
    font-weight: 600 !important;
}

.live-desk-btn.is-active {
    background: rgba(249, 115, 22, 0.2) !important;
    color: #fff7ed !important;
}

.live-desk-btn--primary {
    background: rgba(249, 115, 22, 0.9) !important;
    color: #fff7ed !important;
}

.live-desk-btn--recording {
    background: rgba(239, 68, 68, 0.92) !important;
    color: #fee2e2 !important;
}

.live-desk-chip {
    border-radius: 999px !important;
    padding: 4px 10px !important;
    font-size: 11px !important;
    background: rgba(148, 163, 184, 0.2) !important;
    color: #e2e8f0 !important;
}

.live-status-live {
    background: rgba(239, 68, 68, 0.25) !important;
    color: #fee2e2 !important;
}

.qa-engine-status {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    z-index: 6;
}

.qa-engine-status .q-label {
    background: rgba(15, 23, 42, 0.75);
    color: #e2e8f0;
    padding: 8px 14px;
    border-radius: 999px;
    font-size: 12px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}

.qa-fallback-stack {
    position: absolute;
    inset: 0;
    display: flex;
    flex-wrap: wrap;
    align-content: flex-start;
    gap: 12px;
    padding: 20px 20px 80px;
    overflow: auto;
    z-index: 5;
}

.qa-fallback-card {
    transform: rotate(-1deg);
    box-shadow: 0 12px 28px rgba(15, 23, 42, 0.2);
    transition: transform 0.25s ease, box-shadow 0.25s ease;
}

.qa-fallback-card:hover {
    transform: translateY(-6px) rotate(1deg);
    box-shadow: 0 18px 36px rgba(15, 23, 42, 0.28);
}

.qa-card-visual {
    position: relative;
    background: linear-gradient(160deg, rgba(255, 255, 255, 0.98) 0%, rgba(255, 245, 230, 0.96) 100%);
    border: 1px solid rgba(148, 163, 184, 0.35);
    box-shadow: 0 18px 40px rgba(15, 23, 42, 0.18);
    overflow: visible;
}

.qa-card-visual:hover {
    box-shadow: 0 22px 50px rgba(15, 23, 42, 0.25);
}

.qa-card-visual::after {
    content: "";
    position: absolute;
    inset: 0;
    background:
        radial-gradient(120px 60px at 12% 8%, rgba(255, 255, 255, 0.8), transparent 70%),
        repeating-linear-gradient(45deg, rgba(15, 23, 42, 0.06) 0 1px, transparent 1px 8px);
    opacity: 0.08;
    pointer-events: none;
    border-radius: inherit;
}

.qa-card-index {
    background: rgba(249, 115, 22, 0.12) !important;
    color: #c2410c !important;
    font-weight: 700 !important;
    border-radius: 999px !important;
}

.qa-card-id {
    font-size: 10px !important;
    letter-spacing: 0.18em !important;
    text-transform: uppercase !important;
    color: rgba(15, 23, 42, 0.45) !important;
}

.qa-card-section {
    padding: 6px 8px;
    border-radius: 10px;
    border: 1px solid rgba(148, 163, 184, 0.18);
    background: rgba(255, 255, 255, 0.6);
}

.qa-card-question {
    background: linear-gradient(140deg, rgba(59, 130, 246, 0.12), rgba(59, 130, 246, 0.03));
    border-color: rgba(59, 130, 246, 0.2);
}

.qa-card-answer {
    margin-top: 4px;
    background: linear-gradient(140deg, rgba(16, 185, 129, 0.12), rgba(16, 185, 129, 0.03));
    border-color: rgba(16, 185, 129, 0.2);
}

.qa-card-tilt-1 { transform: rotate(-2deg); }
.qa-card-tilt-2 { transform: rotate(1.5deg); }
.qa-card-tilt-3 { transform: rotate(-1deg); }
.qa-card-tilt-4 { transform: rotate(2deg); }
.qa-card-tilt-5 { transform: rotate(-1.5deg); }

.qa-card-stamp {
    position: absolute;
    top: 12px;
    left: 12px;
    padding: 4px 10px;
    border-radius: 999px;
    border: 1px solid rgba(239, 68, 68, 0.4);
    background: rgba(239, 68, 68, 0.08);
    color: #991b1b;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    transform: rotate(-8deg);
    box-shadow: 0 8px 18px rgba(239, 68, 68, 0.15);
}

.qa-stamp-in {
    animation: stampIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}

@keyframes stampIn {
    0% { transform: translateY(-10px) rotate(-18deg) scale(0.6); opacity: 0; }
    60% { transform: translateY(2px) rotate(-10deg) scale(1.05); opacity: 1; }
    100% { transform: translateY(0) rotate(-8deg) scale(1); opacity: 1; }
}

.qa-filter-btn {
    font-size: 11px !important;
    border-radius: 999px !important;
    padding: 0 10px !important;
    color: rgba(15, 23, 42, 0.6) !important;
}

.qa-filter-btn.is-active {
    background: rgba(249, 115, 22, 0.18) !important;
    color: #9a3412 !important;
}

.qa-stack-overview {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 6px;
    border-radius: 999px;
    background: rgba(148, 163, 184, 0.18);
}

.qa-stack-dot {
    width: 8px;
    height: 8px;
    border-radius: 999px;
    background: rgba(148, 163, 184, 0.35);
}

.qa-stack-dot.is-filled {
    background: rgba(34, 197, 94, 0.65);
    box-shadow: 0 0 10px rgba(34, 197, 94, 0.3);
}

.qa-stack-dot.is-latest {
    background: rgba(249, 115, 22, 0.8);
    box-shadow: 0 0 14px rgba(249, 115, 22, 0.35);
}

.qa-card-preview {
    position: absolute;
    left: 50%;
    bottom: calc(100% + 10px);
    transform: translate(-50%, -6px);
    width: 260px;
    max-height: 220px;
    overflow: hidden;
    opacity: 0;
    pointer-events: none;
    padding: 10px 12px;
    border-radius: 14px;
    background: rgba(15, 23, 42, 0.92);
    color: #e2e8f0;
    border: 1px solid rgba(148, 163, 184, 0.4);
    box-shadow: 0 18px 32px rgba(15, 23, 42, 0.35);
    transition: opacity 0.2s ease, transform 0.2s ease;
    z-index: 3;
}

.qa-card-preview::after {
    content: "";
    position: absolute;
    bottom: -6px;
    left: 50%;
    transform: translateX(-50%) rotate(45deg);
    width: 12px;
    height: 12px;
    background: rgba(15, 23, 42, 0.92);
    border-left: 1px solid rgba(148, 163, 184, 0.3);
    border-bottom: 1px solid rgba(148, 163, 184, 0.3);
}

.qa-card-preview-title {
    font-size: 10px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: rgba(226, 232, 240, 0.6);
    margin-bottom: 4px;
}

.qa-card-preview-title--answer {
    margin-top: 8px;
}

.qa-card-preview-text {
    font-size: 11px;
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 4;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.qa-card-visual:hover .qa-card-preview {
    opacity: 1;
    transform: translate(-50%, -12px);
}
""".strip()

    ui.add_head_html(
        f"""
        <script>
        (function() {{
          const id = {json.dumps(_DESK_STYLE_ID)};
          const cssText = {json.dumps(css)};
          let style = document.getElementById(id);
          if (!style) {{
            style = document.createElement('style');
            style.id = id;
            document.head.appendChild(style);
          }}
          if (style.textContent !== cssText) {{
            style.textContent = cssText;
          }}
        }})();
        </script>
        """
    )
