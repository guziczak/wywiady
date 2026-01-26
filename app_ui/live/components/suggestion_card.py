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
        used: bool = False,
        variant: str = "secondary",
        tag: Optional[str] = None,
        selected: bool = False
    ):
        self.question = question
        self.on_click = on_click
        self.used = used
        self.variant = variant
        self.tag = tag
        self.selected = selected
        self.card = None

    def create(self) -> ui.card:
        """Tworzy i zwraca kartę."""

        # Style bazowe (równe karty w siatce)
        is_primary = self.variant == "primary"
        base_classes = (
            'w-full min-h-[118px] '
            'flex flex-col items-start justify-between gap-3 '
            'p-3 rounded-2xl '
            'transition-all duration-200 ease-out '
            'prompter-card'
        )

        selected_classes = 'prompter-card--selected ' if self.selected else ''
        primary_classes = 'prompter-card--primary ' if is_primary else ''

        if self.used:
            style_classes = base_classes + (
                'prompter-card--used '
                + primary_classes +
                selected_classes +
                'cursor-not-allowed'
            )
        else:
            style_classes = base_classes + (
                'prompter-card--active '
                + primary_classes +
                selected_classes +
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

        # Header (badge + icon)
        with ui.row().classes('w-full items-center justify-between'):
            with ui.row().classes('items-center gap-2'):
                if self.variant == "primary":
                    ui.badge('Następne', color='blue').classes('prompter-badge prompter-badge--primary')
                if self.tag:
                    ui.badge(self.tag, color='gray').classes('prompter-badge')
            icon_color = 'text-slate-300' if self.used else 'text-blue-500'
            ui.icon('auto_awesome', size='sm').classes(icon_color)

        # Tekst pytania
        text_color = 'text-slate-400' if self.used else 'text-slate-800'
        with ui.column().classes('flex-grow justify-center w-full gap-1'):
            ui.label(self.question).classes(
                f'prompter-card-title {text_color}'
            )

        # Hint na dole
        if not self.used:
            with ui.row().classes('w-full justify-between items-center pt-2 prompter-card-footer'):
                ui.label('Kliknij, aby skopiować').classes(
                    'prompter-card-hint'
                )
                ui.icon('content_copy', size='xs').classes('text-slate-300')
        else:
            with ui.row().classes('w-full justify-center items-center pt-2 prompter-card-footer'):
                ui.icon('check', size='xs').classes('text-emerald-500 mr-1')
                ui.label('Użyte').classes('prompter-card-hint text-emerald-500')

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
            'w-full min-h-[118px] '
            'flex items-center justify-center '
            'rounded-2xl '
            'prompter-card prompter-card--ghost'
        ) as card:
            with ui.column().classes('items-center gap-2 px-4'):
                ui.spinner(size='sm', color='gray')
                ui.label(self.message).classes(
                    'prompter-card-hint text-center'
                )

        return card


class EmptyStateCard:
    """Karta gdy sesja nie jest aktywna."""

    def __init__(self, message: str = "Naciśnij START aby rozpocząć"):
        self.message = message

    def create(self) -> ui.card:
        """Tworzy empty state."""
        with ui.card().classes(
            'w-full min-h-[118px] '
            'flex items-center justify-center '
            'rounded-2xl '
            'prompter-card prompter-card--ghost'
        ) as card:
            with ui.column().classes('items-center gap-2 px-4'):
                ui.icon('mic_none', size='lg').classes('text-slate-300')
                ui.label(self.message).classes(
                    'prompter-card-hint text-center'
                )

        return card
