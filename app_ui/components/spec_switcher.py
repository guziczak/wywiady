"""
Przełącznik specjalizacji medycznych.

Komponent UI pozwalający na szybką zmianę aktywnej specjalizacji.
"""

from typing import Optional, Callable
from nicegui import ui

from core.specialization_manager import get_specialization_manager, Specialization


class SpecializationSwitcher:
    """Przełącznik specjalizacji w headerze."""

    def __init__(
        self,
        on_change: Optional[Callable[[Specialization], None]] = None,
        compact: bool = True
    ):
        self.spec_manager = get_specialization_manager()
        self.on_change = on_change
        self.compact = compact
        self.button = None
        self.menu = None

    def create(self) -> None:
        """Tworzy komponent przełącznika."""
        active_spec = self.spec_manager.get_active()

        if self.compact:
            self._create_compact(active_spec)
        else:
            self._create_expanded(active_spec)

    def _create_compact(self, active_spec: Specialization) -> None:
        """Kompaktowy widok - dropdown button."""
        with ui.button(
            f"{active_spec.icon} {active_spec.name}",
            on_click=lambda: None  # Menu handles click
        ).props('flat dense dropdown-icon="arrow_drop_down"').classes(
            'text-white bg-white/10 hover:bg-white/20'
        ) as self.button:
            with ui.menu() as self.menu:
                for spec in self.spec_manager.get_all():
                    is_active = spec.id == active_spec.id
                    with ui.menu_item(
                        on_click=lambda s=spec: self._on_select(s)
                    ).classes('min-w-48'):
                        with ui.row().classes('items-center gap-2 w-full'):
                            ui.label(spec.icon).classes('text-lg')
                            ui.label(spec.name).classes(
                                'font-bold' if is_active else ''
                            )
                            if is_active:
                                ui.icon('check', size='sm').classes('ml-auto text-green-500')

    def _create_expanded(self, active_spec: Specialization) -> None:
        """Rozwinięty widok - chips/tabs."""
        with ui.row().classes('items-center gap-1'):
            for spec in self.spec_manager.get_all():
                is_active = spec.id == active_spec.id
                btn_classes = 'rounded-full px-3 py-1 text-sm'

                if is_active:
                    btn_classes += f' bg-white text-gray-800 font-bold'
                else:
                    btn_classes += ' bg-white/10 text-white hover:bg-white/20'

                ui.button(
                    f"{spec.icon} {spec.name}",
                    on_click=lambda s=spec: self._on_select(s)
                ).props('flat dense unelevated').classes(btn_classes)

    def _on_select(self, spec: Specialization) -> None:
        """Obsługa wyboru specjalizacji."""
        if spec.id == self.spec_manager.get_active().id:
            return  # Już aktywna

        self.spec_manager.set_active(spec.id)

        # Aktualizuj UI
        if self.button:
            self.button.text = f"{spec.icon} {spec.name}"

        if self.menu:
            self.menu.close()

        # Callback
        if self.on_change:
            self.on_change(spec)

        ui.notify(f'Specjalizacja: {spec.name}', type='info')

    def refresh(self) -> None:
        """Odświeża stan przełącznika."""
        active_spec = self.spec_manager.get_active()
        if self.button:
            self.button.text = f"{active_spec.icon} {active_spec.name}"


def create_spec_switcher(
    on_change: Optional[Callable[[Specialization], None]] = None,
    compact: bool = True
) -> SpecializationSwitcher:
    """
    Tworzy i zwraca przełącznik specjalizacji.

    Args:
        on_change: Callback wywoływany po zmianie specjalizacji
        compact: True = dropdown, False = chips

    Returns:
        Instancja SpecializationSwitcher
    """
    switcher = SpecializationSwitcher(on_change=on_change, compact=compact)
    switcher.create()
    return switcher
