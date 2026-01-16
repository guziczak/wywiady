"""
Transcript Panel Component
Panel transkrypcji z auto-scroll i bezpiecznym renderowaniem.
"""

import html
from nicegui import ui
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.live.live_state import LiveState


class TranscriptPanel:
    """
    Panel transkrypcji na żywo.
    - 3 warstwy wizualne (provisional, final, validated)
    - Auto-scroll do najnowszego tekstu
    - Bezpieczne renderowanie HTML (XSS protection)
    - Accessible (aria-live)
    """

    def __init__(self, state: 'LiveState'):
        self.state = state
        self.container = None
        self.html_element = None
        self._scroll_id = None
        self._client = None  # NiceGUI client context

    def create(self) -> ui.card:
        """Tworzy panel transkrypcji."""
        
        print(f"[TRANSCRIPT] create() called, ui.context.client = {ui.context.client}", flush=True)

        self.container = ui.card().classes(
            'w-full h-full '
            'bg-white '
            'border border-gray-200 '
            'rounded-xl shadow-sm '
            'overflow-hidden '
            'relative'
        )

        with self.container:
            # Label w rogu
            ui.label('Transkrypcja na żywo').classes(
                'absolute top-2 left-4 '
                'text-xs text-gray-400 font-medium uppercase tracking-wide '
                'z-10'
            )

            # Scrollable content area
            with ui.scroll_area().classes(
                'w-full h-full pt-8 pb-4 px-6'
            ) as scroll:
                self._scroll_id = f'transcript-scroll-{id(scroll)}'
                scroll.props(f'id="{self._scroll_id}"')

                # HTML content z aria-live dla accessibility
                # sanitize=False bo sami escapujemy przez html.escape()
                self.html_element = ui.html('', sanitize=False).classes(
                    'text-lg leading-relaxed'
                ).props(
                    'aria-live="polite" '
                    'aria-label="Transkrypcja rozmowy"'
                )

            self._render()

        # Capture client context for background updates
        self._client = ui.context.client

        # Subscribe to state changes
        self.state.on_transcript_change(self._on_state_change)

        return self.container

    def _on_state_change(self):
        """Callback gdy zmieni się stan (może być z background thread)."""
        if self._client is None:
            return
        
        # Safe update from any thread using client context
        try:
            with self._client:
                self._render()
                self._auto_scroll()
        except Exception as e:
            # Nie czyścimy _client - może być tymczasowy problem
            print(f"[TRANSCRIPT] Render error: {e}", flush=True)

    def _render(self):
        """Renderuje transkrypcję z 3 warstwami."""
        if not self.html_element:
            return

        html_parts = []

        # 1. Validated - czarny, pogrubiony (finalne)
        if self.state.validated_text:
            safe_text = self._safe_html(self.state.validated_text)
            html_parts.append(
                f'<span style="color: #1f2937; font-weight: 600;">{safe_text}</span>'
            )

        # 2. Final - czarny, normalny (czeka na walidację)
        if self.state.final_text:
            safe_text = self._safe_html(self.state.final_text)
            html_parts.append(
                f'<span style="color: #374151; font-weight: 400;">{safe_text}</span>'
            )

        # 3. Provisional - szary, italic (real-time)
        if self.state.provisional_text:
            safe_text = self._safe_html(self.state.provisional_text)
            html_parts.append(
                f'<span style="color: #6b7280; font-style: italic;">{safe_text}</span>'
            )

        if html_parts:
            self.html_element.content = ' '.join(html_parts)
        else:
            self.html_element.content = (
                '<span style="color: #9ca3af; font-style: italic;">'
                'Naciśnij START aby rozpocząć nagrywanie...'
                '</span>'
            )
        
        # Force UI update
        self.html_element.update()

    def _safe_html(self, text: str) -> str:
        """
        Bezpieczne renderowanie tekstu jako HTML.
        Escapuje wszystko oprócz nowych linii.
        """
        # Escape HTML entities (XSS protection)
        escaped = html.escape(text)
        # Zamień newlines na <br>
        return escaped.replace('\n', '<br>')

    def _auto_scroll(self):
        """Scrolluje do najnowszego tekstu."""
        if self._scroll_id and self._client:
            try:
                ui.run_javascript(f'''
                    const el = document.getElementById("{self._scroll_id}");
                    if (el) {{
                        const scrollContainer = el.querySelector('.q-scrollarea__container');
                        if (scrollContainer) {{
                            scrollContainer.scrollTop = scrollContainer.scrollHeight;
                        }}
                    }}
                ''')
            except Exception:
                pass  # Client może być usunięty

    def clear(self):
        """Czyści transkrypcję (visual only, nie state)."""
        if self.html_element:
            self.html_element.content = ''
