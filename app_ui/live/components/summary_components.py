"""
Summary Components - nowoczesne komponenty UI dla flow zakończenia wywiadu.

Zawiera:
- ConfirmationBar: inline bar potwierdzenia zakończenia
- SummaryStats: statystyki sesji jako chips
- SummaryActions: przyciski akcji w podsumowaniu
"""

from typing import Callable, Optional, TYPE_CHECKING
from nicegui import ui

if TYPE_CHECKING:
    from app_ui.live.live_state import LiveState, InterviewStats


class ConfirmationBar:
    """
    Inline bar potwierdzenia zakończenia wywiadu.

    Nowoczesny pattern zamiast modala - mniej inwazyjny,
    lepszy UX na mobile.
    """

    def __init__(
        self,
        state: 'LiveState',
        on_confirm: Callable[[bool], None],  # callback(analyze_speakers)
        on_cancel: Callable[[], None]
    ):
        self.state = state
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.container = None
        self._analyze_checkbox = None

    def create(self) -> ui.element:
        """Tworzy bar potwierdzenia."""
        self.container = ui.element('div').classes(
            'w-full '
            'bg-gradient-to-r from-amber-50 to-orange-50 '
            'border border-amber-200 '
            'rounded-xl '
            'p-4 '
            'animate-slide-up'
        )

        with self.container:
            # Header z ikoną
            with ui.row().classes('w-full items-center gap-3 mb-3'):
                ui.icon('help_outline', size='sm').classes('text-amber-600')
                ui.label('Zakończyć wywiad?').classes(
                    'text-lg font-semibold text-amber-900'
                )

            # Opcja analizy mówców
            with ui.row().classes('w-full items-center gap-2 mb-4 pl-1'):
                self._analyze_checkbox = ui.checkbox(
                    'Przeanalizuj mówców (Lekarz / Pacjent)',
                    value=self.state.analyze_speakers_preference
                ).classes('text-gray-700')

                ui.label('~3 sek').classes(
                    'text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full'
                )

            # Przyciski
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button(
                    'Anuluj',
                    on_click=self._handle_cancel
                ).props('flat color=grey').classes('text-gray-600')

                ui.button(
                    'Zakończ wywiad',
                    icon='check',
                    on_click=self._handle_confirm
                ).props('color=amber').classes('font-semibold')

        return self.container

    def _handle_confirm(self):
        """Obsługuje potwierdzenie."""
        analyze = self._analyze_checkbox.value if self._analyze_checkbox else True
        # Zapamiętaj preferencję
        self.state.analyze_speakers_preference = analyze
        self.on_confirm(analyze)

    def _handle_cancel(self):
        """Obsługuje anulowanie."""
        self.on_cancel()


class SummaryStats:
    """
    Statystyki sesji jako nowoczesne chips z animacją count-up.
    """

    def __init__(self, stats: 'InterviewStats'):
        self.stats = stats
        self.container = None

    def create(self) -> ui.element:
        """Tworzy chipsy statystyk."""
        self.container = ui.row().classes(
            'w-full justify-center gap-3 flex-wrap'
        )

        with self.container:
            # Czas
            self._create_stat_chip(
                icon='schedule',
                value=self.stats.duration_display,
                label='czas',
                color='blue'
            )

            # Słowa
            self._create_stat_chip(
                icon='notes',
                value=str(self.stats.word_count),
                label='słów',
                color='green'
            )

            # Mówcy (jeśli są)
            if self.stats.speaker_count > 0:
                self._create_stat_chip(
                    icon='record_voice_over',
                    value=str(self.stats.speaker_count),
                    label='mówców',
                    color='purple'
                )

            # Status
            self._create_stat_chip(
                icon='check_circle',
                value='Gotowe',
                label='',
                color='emerald',
                is_status=True
            )

        return self.container

    def _create_stat_chip(
        self,
        icon: str,
        value: str,
        label: str,
        color: str,
        is_status: bool = False
    ):
        """Tworzy pojedynczy chip statystyki."""
        bg_colors = {
            'blue': 'bg-blue-50 border-blue-200',
            'green': 'bg-green-50 border-green-200',
            'purple': 'bg-purple-50 border-purple-200',
            'emerald': 'bg-emerald-50 border-emerald-200',
        }
        text_colors = {
            'blue': 'text-blue-600',
            'green': 'text-green-600',
            'purple': 'text-purple-600',
            'emerald': 'text-emerald-600',
        }

        with ui.element('div').classes(
            f'flex items-center gap-2 px-4 py-2 rounded-full border '
            f'{bg_colors.get(color, "bg-gray-50 border-gray-200")} '
            'animate-fade-in'
        ):
            ui.icon(icon, size='xs').classes(text_colors.get(color, 'text-gray-600'))

            if is_status:
                ui.label(value).classes(
                    f'font-semibold {text_colors.get(color, "text-gray-700")}'
                )
            else:
                ui.label(value).classes(
                    f'text-lg font-bold {text_colors.get(color, "text-gray-700")}'
                )
                if label:
                    ui.label(label).classes('text-xs text-gray-500')


class SummaryActions:
    """
    Przyciski akcji w podsumowaniu.
    """

    def __init__(
        self,
        state: 'LiveState',
        on_continue: Callable[[], None],
        on_toggle_diarization: Optional[Callable[[], None]] = None,
        on_swap_roles: Optional[Callable[[], None]] = None
    ):
        self.state = state
        self.on_continue = on_continue
        self.on_toggle_diarization = on_toggle_diarization
        self.on_swap_roles = on_swap_roles
        self.container = None

    def create(self) -> ui.element:
        """Tworzy przyciski akcji."""
        self.container = ui.column().classes('w-full items-center gap-4')

        with self.container:
            # Kontrolki diaryzacji (jeśli dostępne)
            if self.state.diarization and self.state.diarization.has_data:
                with ui.row().classes('items-center gap-2'):
                    # Toggle widoku diaryzacji
                    diar_enabled = self.state.diarization.enabled
                    ui.button(
                        'Podział na mówców' if not diar_enabled else 'Ukryj mówców',
                        icon='record_voice_over' if not diar_enabled else 'visibility_off',
                        on_click=self._handle_toggle_diarization
                    ).props('flat dense').classes(
                        'text-purple-600' if diar_enabled else 'text-gray-600'
                    )

                    # Swap roles
                    if diar_enabled:
                        ui.button(
                            icon='swap_horiz',
                            on_click=self._handle_swap_roles
                        ).props('flat dense round').classes(
                            'text-gray-500'
                        ).tooltip('Zamień role (Lekarz ↔ Pacjent)')

            # Główny przycisk kontynuacji
            ui.button(
                'Kontynuuj do opisu',
                icon='arrow_forward',
                on_click=self.on_continue
            ).props('color=blue size=lg').classes(
                'font-semibold px-8 animate-pulse-subtle'
            )

            # Hint
            ui.label('Transkrypcja zostanie przekazana do generatora opisu').classes(
                'text-xs text-gray-400'
            )

        return self.container

    def _handle_toggle_diarization(self):
        """Obsługuje toggle diaryzacji."""
        if self.on_toggle_diarization:
            self.on_toggle_diarization()

    def _handle_swap_roles(self):
        """Obsługuje zamianę ról."""
        if self.on_swap_roles:
            self.on_swap_roles()
