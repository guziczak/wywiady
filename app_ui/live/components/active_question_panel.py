"""
Active Question Panel Component
Panel aktywnego pytania - ODDZIELONY od puli sugestii.

Pokazuje:
- Aktywne pytanie (przypięte, nie znika przy regeneracji sugestii)
- Podpowiedzi odpowiedzi pacjenta
- Timer countdown
- Stan (loading/ready/waiting/matched)
- Przycisk pin i close
"""

from nicegui import ui
from typing import Optional, Callable, TYPE_CHECKING
import json

from app_ui.live.components.answer_card import AnswerCard

if TYPE_CHECKING:
    from app_ui.live.state.active_question import ActiveQuestionContext, QuestionState


class ActiveQuestionPanel:
    """
    Panel aktywnego pytania.

    Kluczowe cechy:
    - ODDZIELONY od sugestii - nie znika przy regeneracji
    - Timer countdown pokazuje ile zostało
    - Pin pozwala zachować pytanie
    - Animacje przy zmianie stanu
    """

    # Kolory dla stanów
    STATE_COLORS = {
        'loading': ('bg-blue-50', 'border-blue-200', 'text-blue-700'),
        'ready': ('bg-green-50', 'border-green-200', 'text-green-700'),
        'waiting': ('bg-amber-50', 'border-amber-200', 'text-amber-700'),
        'matched': ('bg-emerald-50', 'border-emerald-300', 'text-emerald-700'),
        'expired': ('bg-gray-50', 'border-gray-200', 'text-gray-500'),
    }

    STATE_LABELS = {
        'loading': 'Ładowanie odpowiedzi...',
        'ready': 'Gotowe',
        'waiting': 'Czekam na odpowiedź pacjenta',
        'matched': 'Dopasowano!',
        'expired': 'Wygasło',
    }

    STATE_ICONS = {
        'loading': 'hourglass_empty',
        'ready': 'check_circle',
        'waiting': 'hearing',
        'matched': 'celebration',
        'expired': 'timer_off',
    }

    def __init__(
        self,
        context: 'ActiveQuestionContext',
        on_answer_click: Optional[Callable[[str], None]] = None,
        on_manual_answer: Optional[Callable[[str, str], None]] = None,  # (question, answer)
        on_close: Optional[Callable[[], None]] = None
    ):
        self.context = context
        self.on_answer_click = on_answer_click
        self.on_manual_answer = on_manual_answer
        self.on_close = on_close

        # UI refs
        self.container: Optional[ui.element] = None
        self.timer_label: Optional[ui.label] = None
        self.state_badge: Optional[ui.badge] = None
        self.answers_container: Optional[ui.element] = None
        self.pin_btn: Optional[ui.button] = None

        # Stan wybranej odpowiedzi (dla manual mode)
        self._selected_answer: Optional[str] = None

        self._client = None
        self._timer = None

    def create(self) -> ui.element:
        """Tworzy panel."""
        self.container = ui.element('div').classes('w-full')

        with self.container:
            self._render()

        # Timer do aktualizacji countdown
        self._timer = ui.timer(1.0, self._update_timer)

        # Capture client
        self._client = ui.context.client

        # Subscribe to context changes
        self.context.on_state_change(self._on_context_change)

        return self.container

    def _render(self):
        """Renderuje zawartość panelu."""
        self.container.clear()

        # Jeśli brak aktywnego pytania - pokaż placeholder
        if not self.context.is_active:
            with self.container:
                self._render_placeholder()
            return

        # Stan aktywny - pokaż panel
        state_name = self.context.state.value
        bg, border, text = self.STATE_COLORS.get(state_name, self.STATE_COLORS['ready'])

        with self.container:
            with ui.card().classes(
                f'w-full {bg} border-2 {border} rounded-xl p-4 '
                'transition-all duration-300 ease-out'
            ):
                # Header
                self._render_header(state_name, text)

                # Pytanie
                self._render_question()

                # Odpowiedzi (jeśli są)
                if self.context.answers:
                    self._render_answers()

                # Footer z hintami
                self._render_footer(state_name)

    def _render_placeholder(self):
        """Placeholder gdy brak aktywnego pytania."""
        with ui.card().classes(
            'w-full bg-slate-50 border-2 border-dashed border-slate-200 '
            'rounded-xl p-4'
        ):
            with ui.row().classes('w-full items-center justify-center gap-3 py-2'):
                ui.icon('touch_app', size='sm').classes('text-slate-400')
                ui.label('Kliknij kartę pytania aby aktywować').classes(
                    'text-sm text-slate-500'
                )

    def _render_header(self, state_name: str, text_color: str):
        """Renderuje nagłówek z kontrolkami."""
        with ui.row().classes('w-full justify-between items-center mb-3'):
            # Lewa strona: ikona stanu + label
            with ui.row().classes('items-center gap-2'):
                icon = self.STATE_ICONS.get(state_name, 'help')
                ui.icon(icon, size='sm').classes(text_color)

                # Stan
                label = self.STATE_LABELS.get(state_name, state_name)
                self.state_badge = ui.badge(label).classes(
                    f'text-xs {text_color}'
                )

            # Prawa strona: timer, pin, close
            with ui.row().classes('items-center gap-1'):
                # Timer countdown
                if self.context.state.value in ('ready', 'waiting'):
                    remaining = int(self.context.time_remaining)
                    mins, secs = divmod(remaining, 60)
                    timer_text = f"{mins}:{secs:02d}"
                    color = 'orange' if remaining < 30 else 'gray'
                    self.timer_label = ui.badge(
                        f'{timer_text}',
                        color=color
                    ).classes('text-xs')

                # Pin button
                pin_icon = 'push_pin' if self.context.pinned else 'push_pin'
                pin_color = 'blue' if self.context.pinned else 'gray'
                self.pin_btn = ui.button(
                    icon=pin_icon,
                    on_click=self._toggle_pin
                ).props(f'flat dense round color={pin_color}').classes(
                    'text-xs'
                ).tooltip('Przypnij pytanie' if not self.context.pinned else 'Odepnij')

                # Close button
                ui.button(
                    icon='close',
                    on_click=self._handle_close
                ).props('flat dense round color=gray').classes('text-xs')

    def _render_question(self):
        """Renderuje pytanie."""
        with ui.row().classes('w-full items-start gap-2 mb-3'):
            ui.icon('help_outline', size='xs').classes('text-blue-500 mt-1')
            ui.label(self.context.question).classes(
                'text-base font-medium text-slate-800 leading-relaxed'
            )

    def _render_answers(self):
        """Renderuje karty odpowiedzi (3 opcje do wyboru)."""
        with ui.column().classes('w-full gap-3'):
            # Header
            with ui.row().classes('items-center gap-2'):
                ui.icon('touch_app', size='xs').classes('text-green-500')
                ui.label('Wybierz odpowiedź pacjenta:').classes(
                    'text-xs text-slate-600 uppercase tracking-wide font-medium'
                )

            # Grid z 3 kartami odpowiedzi
            self.answers_container = ui.element('div').classes(
                'grid grid-cols-1 sm:grid-cols-3 gap-3 w-full'
            )

            with self.answers_container:
                for idx, answer in enumerate(self.context.answers[:3]):
                    AnswerCard(
                        answer=answer,
                        on_click=self._handle_answer_select,
                        selected=self._selected_answer == answer,
                        index=idx
                    ).create()

    def _render_footer(self, state_name: str):
        """Renderuje footer z hintami."""
        hints = {
            'loading': 'Generuję podpowiedzi odpowiedzi...',
            'ready': 'Kliknij odpowiedź LUB poczekaj na pacjenta',
            'waiting': 'Nasłuchuję odpowiedzi pacjenta...',
            'matched': 'Para Q+A została zapisana!',
        }

        hint = hints.get(state_name)
        if hint:
            with ui.row().classes('w-full justify-center mt-3 pt-2 border-t border-slate-200'):
                ui.label(hint).classes('text-xs text-slate-400')

    def _handle_answer_click(self, answer: str):
        """Obsługuje kliknięcie w odpowiedź (kopiowanie do schowka)."""
        # Kopiuj do schowka
        if self._client:
            try:
                self._client.run_javascript(
                    f'navigator.clipboard.writeText({json.dumps(answer)})'
                )
            except Exception:
                pass

            try:
                with self._client:
                    ui.notify('Skopiowano odpowiedź!', type='positive', position='top')
            except Exception:
                pass

        # Callback
        if self.on_answer_click:
            self.on_answer_click(answer)

    def _handle_answer_select(self, answer: str):
        """
        Obsługuje wybór odpowiedzi (manual mode).
        Tworzy parę Q+A natychmiast po kliknięciu.
        """
        # Zapisz jako wybraną
        self._selected_answer = answer

        # Dopasuj odpowiedź (manual source)
        if self.context.match(answer, source='manual'):
            # Callback do live_view (dodanie pary Q+A)
            if self.on_manual_answer:
                self.on_manual_answer(self.context.question, answer)

            # Notyfikacja
            if self._client:
                try:
                    with self._client:
                        ui.notify('Para Q+A zebrana!', type='positive', position='top', icon='check_circle')
                except Exception:
                    pass

    def _toggle_pin(self):
        """Przełącza pin."""
        self.context.toggle_pin()

    def _handle_close(self):
        """Zamyka panel."""
        self.context.clear(force=True)
        if self.on_close:
            self.on_close()

    def _update_timer(self):
        """Aktualizuje timer countdown."""
        if not self.context.is_active:
            return

        # Sprawdź timeout
        if self.context.check_timeout():
            self._refresh_ui()
            return

        # Update timer label
        if self.timer_label and self.context.state.value in ('ready', 'waiting'):
            remaining = int(self.context.time_remaining)
            mins, secs = divmod(remaining, 60)
            timer_text = f"{mins}:{secs:02d}"

            try:
                if self._client:
                    with self._client:
                        self.timer_label.text = timer_text
                        # Zmień kolor gdy mało czasu
                        if remaining < 30:
                            self.timer_label.props('color=red')
                        elif remaining < 60:
                            self.timer_label.props('color=orange')
            except Exception:
                pass

    def _on_context_change(self, context: 'ActiveQuestionContext'):
        """Callback gdy zmieni się kontekst."""
        self._refresh_ui()

    def _refresh_ui(self):
        """Odświeża UI."""
        if self._client:
            try:
                with self._client:
                    self._render()
            except Exception as e:
                print(f"[ActiveQPanel] Refresh error: {e}", flush=True)

    def refresh(self):
        """Publiczna metoda refresh."""
        self._refresh_ui()

    def destroy(self):
        """Cleanup."""
        if self._timer:
            self._timer.cancel()
