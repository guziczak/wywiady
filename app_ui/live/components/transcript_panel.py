"""
Transcript Panel Component - Refactored
Panel transkrypcji z word-level rendering i animacjami shimmer.
"""

import html
import asyncio
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING
from nicegui import ui

from app_ui.live.components.shimmer_styles import inject_shimmer_styles
from app_ui.live.components.diff_engine import DiffEngine, WordToken, WordStatus

if TYPE_CHECKING:
    from app_ui.live.live_state import LiveState


@dataclass
class RenderedSegment:
    """Segment transkrypcji z tokenami."""
    tokens: List[WordToken]
    layer: str  # "provisional", "final", "validated"
    is_regenerating: bool = False


class TranscriptPanel:
    """
    Panel transkrypcji na żywo z animacjami shimmer.

    Features:
    - Word-level rendering (każde słowo = osobny span)
    - Shimmer animation przy regeneracji
    - Diff-based highlighting (tylko zmienione słowa animowane)
    - Auto-scroll do najnowszego tekstu
    - Accessible (aria-live)
    """

    # Czas trwania animacji shimmer (ms)
    SHIMMER_DURATION = 1500
    # Opóźnienie przed usunięciem klasy animacji (ms)
    SETTLE_DELAY = 300

    def __init__(self, state: 'LiveState'):
        self.state = state
        self.container = None
        self.html_element = None
        self._scroll_id = None
        self._client = None

        # Cache poprzednich tekstów dla diff
        self._prev_provisional = ""
        self._prev_improved = ""
        self._prev_final = ""

        # Stan animacji
        self._is_animating = False
        self._animation_task: Optional[asyncio.Task] = None

    def create(self) -> ui.card:
        """Tworzy panel transkrypcji."""

        # Wstrzyknij style CSS
        inject_shimmer_styles()

        print(f"[TRANSCRIPT] create() called", flush=True)

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

            # Indicator regeneracji
            self._regen_indicator = ui.html('', sanitize=False).classes(
                'absolute top-2 right-4 z-10'
            )

            # Scrollable content area
            with ui.scroll_area().classes(
                'w-full h-full pt-8 pb-4 px-6'
            ) as scroll:
                self._scroll_id = f'transcript-scroll-{id(scroll)}'
                scroll.props(f'id="{self._scroll_id}"')

                # HTML content z aria-live
                self.html_element = ui.html('', sanitize=False).classes(
                    'text-lg leading-relaxed'
                ).props(
                    'aria-live="polite" '
                    'aria-label="Transkrypcja rozmowy"'
                )

            self._render()

        # Capture client context
        self._client = ui.context.client

        # Subscribe to state changes
        self.state.on_transcript_change(self._on_state_change)
        self.state.on_diarization_change(self._on_diarization_change)

        return self.container

    def _on_diarization_change(self):
        """Callback gdy zmieni się diaryzacja."""
        if self._client is None:
            return

        try:
            with self._client:
                self._render()
                self._auto_scroll()
        except Exception as e:
            print(f"[TRANSCRIPT] Diarization render error: {e}", flush=True)

    def _on_state_change(self):
        """Callback gdy zmieni się stan."""
        if self._client is None:
            return

        # Jeśli animacja w toku - nie renderuj (animacja sama zarządza renderem)
        if self._is_animating:
            return

        try:
            with self._client:
                self._render()
                self._auto_scroll()
        except Exception as e:
            print(f"[TRANSCRIPT] Render error: {e}", flush=True)

    def trigger_regeneration_animation(self, layer: str = "improved", prev_text: str = ""):
        """
        Triggeruje animację regeneracji dla danej warstwy.

        Args:
            layer: "improved" lub "final"
            prev_text: Poprzedni tekst do porównania (dla diff)
        """
        if self._client is None:
            return

        try:
            with self._client:
                self._is_animating = True

                # Zapisz poprzedni tekst do cache (dla diff)
                if layer == "improved" and prev_text:
                    self._prev_provisional = prev_text
                elif layer == "final" and prev_text:
                    self._prev_final = prev_text

                self._update_regen_indicator(True)
                self._render_with_animation(layer)
                self._auto_scroll()

                # Zaplanuj zakończenie animacji (thread-safe timer)
                # Anuluj poprzedni timer jeśli istnieje
                if hasattr(self, '_animation_timer') and self._animation_timer:
                    self._animation_timer.cancel()
                    self._animation_timer = None

                # Użyj ui.timer który działa poprawnie z wątkami (via client context)
                self._animation_timer = ui.timer(
                    self.SHIMMER_DURATION / 1000, 
                    self._finish_animation_callback, 
                    once=True
                )

        except Exception as e:
            print(f"[TRANSCRIPT] Animation error: {e}", flush=True)

    async def _finish_animation_callback(self):
        """Callback kończący animację."""
        try:
            self._is_animating = False
            self._update_regen_indicator(False)
            # Małe opóźnienie dla płynności
            await asyncio.sleep(self.SETTLE_DELAY / 1000)
            self._render()
        except Exception as e:
             print(f"[TRANSCRIPT] Finish animation error: {e}", flush=True)

    def _update_regen_indicator(self, active: bool):
        """Aktualizuje wskaźnik regeneracji."""
        if not self._regen_indicator:
            return

        if active:
            self._regen_indicator.content = '''
                <div class="flex items-center gap-2 px-2 py-1 bg-blue-50 rounded-full">
                    <div class="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                    <span class="text-xs text-blue-600 font-medium">Regeneracja...</span>
                </div>
            '''
        else:
            self._regen_indicator.content = ''

        self._regen_indicator.update()

    def _render(self):
        """Renderuje transkrypcję (bez animacji)."""
        if not self.html_element:
            return

        html_content = self._build_html(animate=False)
        self.html_element.content = html_content
        self.html_element.update()

    def _render_with_animation(self, layer: str):
        """Renderuje z animacją shimmer na zmienonych słowach."""
        if not self.html_element:
            return

        html_content = self._build_html(animate=True, animate_layer=layer)
        self.html_element.content = html_content
        self.html_element.update()

    def _build_html(self, animate: bool = False, animate_layer: str = "improved") -> str:
        """Buduje HTML z tokenami słów."""
        # Jeśli diaryzacja włączona i ma dane - użyj specjalnego renderingu
        if (self.state.diarization and
            self.state.diarization.enabled and
            self.state.diarization.has_data):
            return self._render_diarized()

        html_parts = []

        # 1. Validated text - zawsze statyczny
        if self.state.validated_text:
            tokens = self._tokenize_simple(self.state.validated_text)
            html_parts.append(self._render_tokens(tokens, "validated", False))

        # 2. Final text
        if self.state.final_text:
            should_animate = animate and animate_layer == "final"

            if should_animate:
                # Dla final - diff z poprzednim provisional (który został sfinalizowany)
                prev = self._prev_final if self._prev_final else ""
                tokens = DiffEngine.compute_regeneration_diff(
                    prev,
                    self.state.final_text,
                    "final"
                )
            else:
                tokens = self._tokenize_simple(self.state.final_text)

            html_parts.append(self._render_tokens(tokens, "final", should_animate))

            # Aktualizuj cache po renderze
            if not animate:
                self._prev_final = self.state.final_text

        # 3. Provisional text (lub improved)
        if self.state.provisional_text:
            should_animate = animate and animate_layer == "improved"

            if should_animate:
                # Diff z poprzednim
                prev = self._prev_provisional if self._prev_provisional else ""
                tokens = DiffEngine.compute_regeneration_diff(
                    prev,
                    self.state.provisional_text,
                    "improved"
                )
            else:
                tokens = self._tokenize_simple(self.state.provisional_text)

            html_parts.append(self._render_tokens(tokens, "provisional", should_animate))

            # Aktualizuj cache po renderze
            if not animate:
                self._prev_provisional = self.state.provisional_text

        if html_parts:
            return ' '.join(html_parts)
        else:
            return self._render_empty_state()

    def _tokenize_simple(self, text: str) -> List[WordToken]:
        """Prosta tokenizacja bez diff."""
        words = DiffEngine.tokenize(text)
        return [WordToken(w, WordStatus.UNCHANGED) for w in words]

    def _render_tokens(
        self,
        tokens: List[WordToken],
        layer: str,
        animate: bool
    ) -> str:
        """Renderuje listę tokenów jako HTML z grupowaniem zmian."""
        if not tokens:
            return ""

        html_groups = []
        current_group = []
        # Stan grupy: True jeśli to sekwencja zmian (ADDED/MODIFIED), False jeśli zwykły tekst
        is_regenerating_group = False

        def flush_group():
            if not current_group:
                return
            
            # Budujemy HTML dla słów w grupie
            words_html = []
            for token in current_group:
                # Klasy dla samego słowa (kolor, styl)
                classes = ["transcript-word", layer]
                if is_regenerating_group and animate:
                    # Dodatkowe markery typu zmiany (dla debugowania lub future use)
                    if token.status == WordStatus.ADDED:
                        classes.append("added-marker")
                    elif token.status == WordStatus.MODIFIED:
                        classes.append("modified-marker")
                
                safe_text = html.escape(token.text)
                class_str = " ".join(classes)
                words_html.append(f'<span class="{class_str}">{safe_text}</span>')
            
            content = " ".join(words_html)

            # Wrapujemy w kontener sekwencji jeśli to grupa regenerowana
            if is_regenerating_group and animate:
                # To jest ten "ciąg słów" z gradientem
                html_groups.append(f'<span class="transcript-sequence regenerating">{content}</span>')
            else:
                # Zwykły tekst bez specjalnego wrappera (chyba że dla layer)
                html_groups.append(content)

        for token in tokens:
            # Sprawdź czy token jest "aktywny" (zmieniony)
            is_token_active = token.status != WordStatus.UNCHANGED
            
            # Jeśli stan się zmienił, zrzuć poprzednią grupę
            if is_token_active != is_regenerating_group:
                flush_group()
                current_group = []
                is_regenerating_group = is_token_active
            
            current_group.append(token)

        # Zrzuć ostatnią grupę
        flush_group()

        # Wrap w segment container
        container_class = "transcript-segment"
        if animate:
            container_class += " regenerating-container" # Opcjonalne tło dla całego bloku

        return f'<span class="{container_class}">{" ".join(html_groups)}</span>'

    def _render_empty_state(self) -> str:
        """Renderuje stan pusty."""
        return '''
            <span class="transcript-word provisional" style="color: #9ca3af; font-style: italic;">
                Naciśnij START aby rozpocząć nagrywanie...
            </span>
        '''

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
                pass

    def _render_diarized(self) -> str:
        """Renderuje transkrypcję z podziałem na mówców."""
        if not self.state.diarization or not self.state.diarization.segments:
            return self._render_empty_state()

        html_parts = []

        # Import SpeakerRole dynamicznie (żeby uniknąć circular import)
        try:
            from core.diarization import SpeakerRole
        except ImportError:
            SpeakerRole = None

        for segment in self.state.diarization.segments:
            if not segment.text:
                continue

            # Określ kolor i label na podstawie roli
            role = segment.role
            if SpeakerRole:
                if role == SpeakerRole.DOCTOR:
                    bg_color = "#E3F2FD"  # Jasny niebieski
                    border_color = "#1976D2"
                    label = "👨‍⚕️ Lekarz"
                    text_color = "#1565C0"
                elif role == SpeakerRole.PATIENT:
                    bg_color = "#E8F5E9"  # Jasny zielony
                    border_color = "#388E3C"
                    label = "🙍 Pacjent"
                    text_color = "#2E7D32"
                else:
                    bg_color = "#F5F5F5"  # Jasny szary
                    border_color = "#9E9E9E"
                    label = "❓ Nieznany"
                    text_color = "#616161"
            else:
                # Fallback bez importu
                bg_color = "#F5F5F5"
                border_color = "#9E9E9E"
                label = segment.speaker_id
                text_color = "#616161"

            safe_text = html.escape(segment.text)

            html_parts.append(f'''
                <div class="diarized-segment" style="
                    background: {bg_color};
                    padding: 10px 14px;
                    margin: 6px 0;
                    border-radius: 8px;
                    border-left: 4px solid {border_color};
                ">
                    <div style="
                        font-size: 11px;
                        color: {text_color};
                        font-weight: 600;
                        margin-bottom: 4px;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                    ">{label}</div>
                    <div style="color: #333; line-height: 1.5;">{safe_text}</div>
                </div>
            ''')

        if html_parts:
            # Dodaj info o liczbie mówców
            num_speakers = self.state.diarization.num_speakers
            header = f'''
                <div style="
                    text-align: center;
                    padding: 8px;
                    margin-bottom: 12px;
                    background: #FAFAFA;
                    border-radius: 6px;
                    font-size: 12px;
                    color: #666;
                ">
                    🎙️ Wykryto <strong>{num_speakers}</strong> mówców
                </div>
            '''
            return header + '\n'.join(html_parts)
        else:
            return self._render_empty_state()

    def clear(self):
        """Czyści transkrypcję."""
        self._prev_provisional = ""
        self._prev_improved = ""
        self._prev_final = ""
        if self.html_element:
            self.html_element.content = ''
