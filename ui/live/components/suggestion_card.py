"""
Suggestion Card Component
Interaktywna karta z sugestią pytania.
"""

from nicegui import ui
from typing import Callable, Optional


class SuggestionCard:
    """
    Karta sugestii pytania.
    - Jasny design spójny z resztą aplikacji
    - Interaktywna (klikalna)
    - Responsywna
    - Accessible (keyboard nav, aria)
    """

    def __init__(
        self,
        question: str,
        on_click: Optional[Callable[[str], None]] = None,
        used: bool = False
    ):
        self.question = question
        self.on_click = on_click
        self.used = used
        self.card = None

    def create(self) -> ui.card:
        """Tworzy i zwraca kartę."""

        # Style bazowe
        base_classes = (
            'flex-1 min-w-[200px] max-w-[300px] '  # Równe karty w row
            'min-h-[140px] '
            'flex flex-col items-center justify-center '
            'p-4 rounded-xl '
            'transition-all duration-200 ease-out '
        )

        if self.used:
            # Użyta karta - wyszarzona
            style_classes = base_classes + (
                'bg-gray-100 border-2 border-gray-200 '
                'opacity-50 cursor-not-allowed'
            )
        else:
            # Aktywna karta - interaktywna
            style_classes = base_classes + (
                'bg-white border-2 border-blue-100 '
                'shadow-md hover:shadow-lg '
                'hover:border-blue-300 hover:scale-[1.02] '
                'cursor-pointer '
                'focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2'
            )

        # Tworzymy kartę
        self.card = ui.card().classes(style_classes)

        # Accessibility
        self.card.props(
            'tabindex="0" '
            'role="button" '
            f'aria-label="Sugerowane pytanie: {self.question[:50]}"'
        )

        # Click handler
        if self.on_click and not self.used:
            self.card.on('click', lambda: self._handle_click())
            # Keyboard support (Enter/Space)
            self.card.on('keydown', lambda e: self._handle_keydown(e))

        with self.card:
            self._create_content()

        return self.card

    def _create_content(self):
        """Tworzy zawartość karty."""

        # Ikona w górnym rogu
        with ui.row().classes('w-full justify-start mb-2'):
            icon_color = 'text-gray-400' if self.used else 'text-blue-500'
            ui.icon('help_outline', size='sm').classes(icon_color)

        # Tekst pytania
        text_color = 'text-gray-400' if self.used else 'text-gray-700'
        with ui.column().classes('flex-grow justify-center w-full'):
            ui.label(self.question).classes(
                f'text-center {text_color} text-sm sm:text-base '
                'leading-relaxed font-medium'
            )

        # Hint na dole
        if not self.used:
            with ui.row().classes('w-full justify-center mt-3 pt-2 border-t border-gray-100'):
                ui.label('Kliknij aby użyć').classes(
                    'text-xs text-gray-400 font-light'
                )
        else:
            with ui.row().classes('w-full justify-center mt-3 pt-2 border-t border-gray-100'):
                ui.icon('check', size='xs').classes('text-green-500 mr-1')
                ui.label('Użyte').classes('text-xs text-green-500 font-light')

    def _handle_click(self):
        """Obsługuje kliknięcie."""
        if self.on_click and not self.used:
            self.on_click(self.question)

    def _handle_keydown(self, event):
        """Obsługuje klawiaturę (Enter/Space)."""
        # NiceGUI przekazuje event jako dict
        key = event.args.get('key', '') if hasattr(event, 'args') else ''
        if key in ['Enter', ' ']:
            self._handle_click()


class PlaceholderCard:
    """Karta placeholder gdy nie ma jeszcze sugestii."""

    def __init__(self, message: str = "Analizuję rozmowę..."):
        self.message = message

    def create(self) -> ui.card:
        """Tworzy placeholder."""
        with ui.card().classes(
            'flex-1 min-w-[200px] max-w-[300px] '
            'min-h-[140px] '
            'flex items-center justify-center '
            'bg-gray-50 border-2 border-dashed border-gray-200 '
            'rounded-xl'
        ) as card:
            with ui.column().classes('items-center gap-2'):
                ui.spinner(size='sm', color='gray')
                ui.label(self.message).classes(
                    'text-gray-400 text-sm font-light italic text-center'
                )

        return card


class EmptyStateCard:
    """Karta gdy sesja nie jest aktywna."""

    def __init__(self, message: str = "Naciśnij START aby rozpocząć"):
        self.message = message

    def create(self) -> ui.card:
        """Tworzy empty state."""
        with ui.card().classes(
            'flex-1 min-w-[200px] max-w-[300px] '
            'min-h-[140px] '
            'flex items-center justify-center '
            'bg-slate-50 border-2 border-slate-200 '
            'rounded-xl'
        ) as card:
            with ui.column().classes('items-center gap-2'):
                ui.icon('mic_none', size='lg').classes('text-slate-300')
                ui.label(self.message).classes(
                    'text-slate-400 text-sm font-light text-center'
                )

        return card
