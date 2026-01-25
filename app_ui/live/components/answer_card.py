"""
Answer Card Component
Klikalna karta odpowiedzi pacjenta (do wyboru manualnego).

Wzorowana na SuggestionCard, ale z designem dla odpowiedzi:
- Zielona kolorystyka (odpowiedzi)
- Hover effects
- Stan selected
- Accessibility (keyboard nav, aria)
"""

from nicegui import ui
from typing import Callable, Optional


class AnswerCard:
    """
    Karta odpowiedzi pacjenta.
    - Jasny design z zieloną kolorystyką
    - Interaktywna (klikalna)
    - Stan selected (po kliknięciu)
    - Accessible (keyboard nav, aria)
    """

    def __init__(
        self,
        answer: str,
        on_click: Optional[Callable[[str], None]] = None,
        selected: bool = False,
        index: int = 0
    ):
        self.answer = answer
        self.on_click = on_click
        self.selected = selected
        self.index = index
        self.card = None

    def create(self) -> ui.card:
        """Tworzy i zwraca kartę."""

        # Style bazowe
        base_classes = (
            'w-full min-h-[80px] '
            'flex flex-col items-start justify-between '
            'p-3 rounded-xl '
            'transition-all duration-200 ease-out '
        )

        if self.selected:
            # Wybrana karta - zielone podswietlenie
            style_classes = base_classes + (
                'bg-green-50 border-2 border-green-500 '
                'ring-2 ring-green-200 '
                'shadow-md cursor-pointer'
            )
        else:
            # Normalna karta - interaktywna
            style_classes = base_classes + (
                'bg-white border-2 border-slate-200 '
                'shadow-sm hover:shadow-md '
                'hover:border-green-300 hover:scale-[1.01] hover:bg-green-50/30 '
                'cursor-pointer '
                'focus:outline-none focus:ring-2 focus:ring-green-400 focus:ring-offset-2'
            )

        # Tworzymy kartę
        self.card = ui.card().classes(style_classes)

        # Accessibility
        self.card.props(
            'tabindex="0" '
            'role="button" '
            f'aria-label="Odpowiedz pacjenta: {self.answer[:50]}"'
        )

        # Click handler
        if self.on_click:
            self.card.on('click', lambda: self._handle_click())
            # Keyboard support (Enter/Space)
            self.card.on('keydown', lambda e: self._handle_keydown(e))

        with self.card:
            self._create_content()

        return self.card

    def _create_content(self):
        """Tworzy zawartość karty."""

        # Header z ikoną
        with ui.row().classes('w-full items-center justify-between mb-1'):
            with ui.row().classes('items-center gap-2'):
                icon_name = 'check_circle' if self.selected else 'chat_bubble_outline'
                icon_color = 'text-green-500' if self.selected else 'text-slate-400'
                ui.icon(icon_name, size='xs').classes(icon_color)

                # Numer odpowiedzi
                label_color = 'text-green-600' if self.selected else 'text-slate-400'
                ui.label(f'Opcja {self.index + 1}').classes(
                    f'text-xs {label_color} uppercase tracking-wide font-medium'
                )

            # Ikona wyboru
            if self.selected:
                ui.icon('done', size='sm').classes('text-green-500')

        # Tekst odpowiedzi
        text_color = 'text-green-800' if self.selected else 'text-slate-700'
        with ui.column().classes('flex-grow justify-center w-full'):
            # Pokaż cały tekst lub skrócony
            display_text = self.answer if len(self.answer) <= 100 else self.answer[:97] + '...'
            ui.label(display_text).classes(
                f'{text_color} text-sm leading-relaxed'
            )

        # Hint na dole
        if not self.selected:
            with ui.row().classes('w-full justify-center items-center mt-2 pt-2 border-t border-slate-100'):
                ui.label('Kliknij aby wybrać').classes(
                    'text-xs text-slate-400 font-light'
                )
        else:
            with ui.row().classes('w-full justify-center items-center mt-2 pt-2 border-t border-green-100'):
                ui.icon('check', size='xs').classes('text-green-500 mr-1')
                ui.label('Wybrano').classes('text-xs text-green-600 font-medium')

    def _handle_click(self):
        """Obsługuje kliknięcie."""
        if self.on_click:
            self.on_click(self.answer)

    def _handle_keydown(self, event):
        """Obsługuje klawiaturę (Enter/Space)."""
        key = event.args.get('key', '') if hasattr(event, 'args') else ''
        if key in ['Enter', ' ']:
            self._handle_click()
