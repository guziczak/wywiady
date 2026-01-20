"""
Transcript Panel Component - Refactored
Panel transkrypcji z word-level rendering i animacjami shimmer.
"""

import html
import asyncio
import json
import re
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
        self._sentence_popup = None
        self._sentence_popup_sentence = None
        self._sentence_popup_items = None
        self._selected_sentence = ""

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

                # Klik w zdanie -> podpowiedzi pytań
                self.html_element.on(
                    'click',
                    handler=self._handle_sentence_click,
                    js_handler='''
                        (e) => {
                            const word = e.target.closest('.transcript-word');
                            if (!word) return;
                            const sentence = word.dataset.sentence;
                            if (!sentence || sentence.length < 3) return;
                            const pad = 12;
                            const width = 340;
                            const height = 180;
                            let x = (e.clientX || 0) + 12;
                            let y = (e.clientY || 0) + 12;
                            x = Math.min(Math.max(x, pad), window.innerWidth - width - pad);
                            y = Math.min(Math.max(y, pad), window.innerHeight - height - pad);
                            emit({sentence: sentence, x: x, y: y});
                        }
                    '''
                )

            # Szybki dymek z pytaniami
            self._sentence_popup = ui.card().classes(
                'hidden fixed z-50 '
                'w-[340px] max-w-[calc(100%-32px)] '
                'bg-white border border-slate-200 '
                'rounded-xl shadow-lg '
                'p-3'
            ).style('left: 16px; top: 80px;')
            self._sentence_popup.set_visibility(False)
            with self._sentence_popup:
                with ui.row().classes('w-full items-center justify-between gap-2'):
                    ui.label('Pytania do zdania').classes(
                        'text-[11px] uppercase tracking-wide text-slate-500 font-medium'
                    )
                    ui.button(icon='close', on_click=self._hide_sentence_popup).props(
                        'flat dense round'
                    ).classes('text-slate-400 hover:text-slate-600')

                self._sentence_popup_sentence = ui.label('').classes(
                    'text-xs text-slate-600 mt-1 leading-snug'
                )
                self._sentence_popup_items = ui.column().classes('w-full gap-2 mt-3')
                ui.label('Kliknij pytanie, aby skopiować.').classes('text-xs text-slate-400 mt-2')

            self._render()

        # Capture client context
        self._client = ui.context.client

        # Subscribe to state changes
        self.state.on_transcript_change(self._on_state_change)
        self.state.on_diarization_change(self._on_diarization_change)

        return self.container

    def _handle_sentence_click(self, event):
        """Obsługuje klik w zdanie transkrypcji."""
        payload = event.args if isinstance(event.args, dict) else {}
        sentence = (payload.get("sentence") or "").strip()
        if not sentence:
            return
        if sentence == self._selected_sentence and self._sentence_popup and self._sentence_popup.visible:
            self._hide_sentence_popup()
            return

        self._selected_sentence = sentence
        questions = self._generate_followup_questions(sentence)
        self._show_sentence_popup(
            sentence,
            questions,
            payload.get("x"),
            payload.get("y")
        )

    def _show_sentence_popup(self, sentence: str, questions: list, x=None, y=None):
        """Pokazuje dymek z pytaniami."""
        if not self._sentence_popup or not self._sentence_popup_items or not self._sentence_popup_sentence:
            return

        display_sentence = sentence if len(sentence) <= 160 else sentence[:157] + "..."
        self._sentence_popup_sentence.text = display_sentence

        self._sentence_popup_items.clear()
        with self._sentence_popup_items:
            for question in questions[:3]:
                with ui.element('div').classes(
                    'w-full px-3 py-2 '
                    'bg-slate-50 border border-slate-200 rounded-lg '
                    'cursor-pointer hover:bg-slate-100 transition-colors'
                ).on('click', lambda e=None, q=question: self._copy_question(q)):
                    with ui.row().classes('items-start gap-2'):
                        ui.icon('help_outline', size='xs').classes('text-slate-400 mt-[2px]')
                        ui.label(question).classes('text-sm text-slate-700 leading-snug')

        if x is not None and y is not None:
            try:
                self._sentence_popup.style(f'left: {int(x)}px; top: {int(y)}px;')
            except Exception:
                pass
        self._sentence_popup.set_visibility(True)

    def _hide_sentence_popup(self):
        if self._sentence_popup:
            self._sentence_popup.set_visibility(False)

    def _copy_question(self, question: str):
        try:
            ui.run_javascript(f'navigator.clipboard.writeText({json.dumps(question)})')
            ui.notify("Skopiowano pytanie", type='positive', position='top')
        except Exception:
            pass

    def _generate_followup_questions(self, sentence: str) -> list:
        """Generuje szybkie pytania follow-up (bez AI)."""
        q = sentence.lower()
        questions: list[str] = []

        def add(*items: str):
            for item in items:
                if item and item not in questions:
                    questions.append(item)

        def has_any(*terms: str) -> bool:
            return any(term in q for term in terms)

        if has_any("ból", "boli", "bolesn", "kłuje", "piecze", "pulsuje"):
            add(
                "W skali 0–10 jak silny jest ból?",
                "Czy ból nasila się przy gryzieniu lub dotyku?",
                "Czy ból promieniuje w inne miejsce?"
            )

        if has_any("opuch", "obrzęk", "spuch", "puchnie"):
            add(
                "Od kiedy jest obrzęk?",
                "Czy obrzęk narasta czy jest stały?",
                "Czy towarzyszy temu ból lub gorączka?"
            )

        if has_any("krwaw", "krew"):
            add(
                "Kiedy pojawia się krwawienie?",
                "Czy krwawienie jest przy szczotkowaniu lub nitkowaniu?",
                "Czy krwawienie jest obfite?"
            )

        if has_any("gorączk", "temperatur", "dreszcz"):
            add(
                "Jaka była najwyższa temperatura?",
                "Od kiedy utrzymuje się gorączka?",
                "Czy są dreszcze lub osłabienie?"
            )

        if has_any("oko", "widzen", "wzrok", "mroczki", "błyski", "blyski"):
            add(
                "Które oko jest problematyczne?",
                "Czy pogorszenie było nagłe czy stopniowe?",
                "Czy występują mroczki lub błyski światła?"
            )

        if has_any("lek", "tablet", "przyjm", "stosuj", "antybiot"):
            add(
                "Jakie leki i w jakiej dawce były stosowane?",
                "Czy leki przyniosły ulgę?",
                "Od kiedy przyjmuje Pan/Pani leki?"
            )

        if has_any("alerg", "uczulen"):
            add(
                "Na co ma Pan/Pani alergię?",
                "Jakie były reakcje alergiczne?",
                "Czy były ostatnio nowe leki lub preparaty?"
            )

        if has_any("od kiedy", "jak długo", "ile czasu", "trwa", "zacz"):
            add(
                "Od kiedy to trwa?",
                "Czy objawy się nasilają z czasem?",
                "Czy wcześniej były podobne epizody?"
            )

        if not questions:
            add(
                "Od kiedy to trwa?",
                "Co nasila lub łagodzi objawy?",
                "Czy występują inne objawy towarzyszące?"
            )

        if len(questions) < 3:
            add(
                "Czy objawy utrudniają codzienne funkcjonowanie?",
                "Czy wcześniej występowało coś podobnego?",
                "Czy coś wyraźnie pogarsza lub poprawia stan?"
            )

        return questions[:3]

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
        current_group: list[tuple[WordToken, int]] = []
        # Stan grupy: True jeśli to sekwencja zmian (ADDED/MODIFIED), False jeśli zwykły tekst
        is_regenerating_group = False
        sentence_map = self._map_tokens_to_sentences(tokens)

        def flush_group():
            if not current_group:
                return
            
            # Budujemy HTML dla słów w grupie
            words_html = []
            for token, idx in current_group:
                # Klasy dla samego słowa (kolor, styl)
                classes = ["transcript-word", layer]
                if is_regenerating_group and animate:
                    # Dodatkowe markery typu zmiany (dla debugowania lub future use)
                    if token.status == WordStatus.ADDED:
                        classes.append("added-marker")
                    elif token.status == WordStatus.MODIFIED:
                        classes.append("modified-marker")
                sentence = sentence_map[idx] if idx < len(sentence_map) else ""
                sentence_attr = ""
                if sentence:
                    sentence_attr = f' data-sentence="{html.escape(sentence, quote=True)}"'
                safe_text = html.escape(token.text)
                class_str = " ".join(classes)
                words_html.append(f'<span class="{class_str}"{sentence_attr}>{safe_text}</span>')
            
            content = " ".join(words_html)

            # Wrapujemy w kontener sekwencji jeśli to grupa regenerowana
            if is_regenerating_group and animate:
                # To jest ten "ciąg słów" z gradientem
                html_groups.append(f'<span class="transcript-sequence regenerating">{content}</span>')
            else:
                # Zwykły tekst bez specjalnego wrappera (chyba że dla layer)
                html_groups.append(content)

        for idx, token in enumerate(tokens):
            # Sprawdź czy token jest "aktywny" (zmieniony)
            is_token_active = token.status != WordStatus.UNCHANGED
            
            # Jeśli stan się zmienił, zrzuć poprzednią grupę
            if is_token_active != is_regenerating_group:
                flush_group()
                current_group = []
                is_regenerating_group = is_token_active
            
                current_group.append((token, idx))

        # Zrzuć ostatnią grupę
        flush_group()

        # Wrap w segment container
        container_class = "transcript-segment"
        if animate:
            container_class += " regenerating-container" # Opcjonalne tło dla całego bloku

        return f'<span class="{container_class}">{" ".join(html_groups)}</span>'

    def _map_tokens_to_sentences(self, tokens: List[WordToken]) -> List[str]:
        """Mapuje tokeny do zdań na podstawie interpunkcji."""
        if not tokens:
            return []

        sentence_map = [""] * len(tokens)
        start = 0

        for i, token in enumerate(tokens):
            if self._is_sentence_end(token.text):
                sentence = " ".join(t.text for t in tokens[start:i + 1]).strip()
                for j in range(start, i + 1):
                    sentence_map[j] = sentence
                start = i + 1

        if start < len(tokens):
            sentence = " ".join(t.text for t in tokens[start:]).strip()
            for j in range(start, len(tokens)):
                sentence_map[j] = sentence

        # Odfiltruj bardzo krótkie "zdania"
        for i, sentence in enumerate(sentence_map):
            if len(sentence) < 3:
                sentence_map[i] = ""

        return sentence_map

    def _is_sentence_end(self, word: str) -> bool:
        """Sprawdza czy token kończy zdanie."""
        if not word:
            return False
        return re.search(r'[.!?…]+["\')\]]?$', word) is not None

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
        self._selected_sentence = ""
        self._hide_sentence_popup()
