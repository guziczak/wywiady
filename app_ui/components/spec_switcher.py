"""
Przełącznik specjalizacji medycznych.

Komponent UI pozwalający na wybór wielu specjalizacji jednocześnie (multi-select).
"""

from typing import Optional, Callable, List
from functools import lru_cache
from pathlib import Path
import re
from nicegui import ui

from core.specialization_manager import get_specialization_manager, Specialization


class SpecializationSwitcher:
    """Przełącznik specjalizacji w headerze (multi-select)."""

    def __init__(
        self,
        on_change: Optional[Callable[[List[Specialization]], None]] = None,
        compact: bool = True
    ):
        self.spec_manager = get_specialization_manager()
        self.on_change = on_change
        self.compact = compact
        self.button = None
        self.menu = None
        self.button_icons = None
        self.button_label = None
        self.item_checks = {}

    @staticmethod
    @lru_cache(maxsize=64)
    def _load_svg(path_str: str) -> str:
        if not path_str:
            return ""
        try:
            root = Path(__file__).parent.parent.parent
            svg_path = (root / path_str).resolve()
            if not svg_path.exists():
                return ""
            return svg_path.read_text(encoding='utf-8')
        except Exception:
            return ""

    @staticmethod
    def _svg_with_size(svg: str, size: int) -> str:
        if not svg:
            return ""
        svg = re.sub(r'width="[^"]+"', f'width="{size}"', svg, count=1)
        svg = re.sub(r'height="[^"]+"', f'height="{size}"', svg, count=1)
        return svg

    def _get_icon_html(self, spec: Specialization, size: int = 20) -> str:
        svg_path = getattr(spec, 'icon_svg', '') or ''
        if svg_path:
            svg = self._load_svg(svg_path)
            if svg:
                icon = self._svg_with_size(svg, max(12, size - 6))
                color = getattr(spec, 'color_primary', '#1976D2') or '#1976D2'
                return (
                    f'<span style="display:inline-flex;align-items:center;justify-content:center;'
                    f'width:{size}px;height:{size}px;border-radius:999px;background:{color};color:white;">'
                    f'{icon}</span>'
                )
        icon_text = spec.icon or ''
        color = getattr(spec, 'color_primary', '#1976D2') or '#1976D2'
        return (
            f'<span style="display:inline-flex;align-items:center;justify-content:center;'
            f'width:{size}px;height:{size}px;border-radius:999px;background:{color};color:white;'
            f'font-size:{max(12, size - 6)}px">{icon_text}</span>'
        )

    def _get_button_label(self, active_specs: List[Specialization]) -> str:
        """Generuje tekst przycisku dla wybranych specjalizacji."""
        if not active_specs:
            return "Wybierz specjalizację"
        if len(active_specs) == 1:
            return active_specs[0].name
        elif len(active_specs) == 2:
            return f"{active_specs[0].name}, {active_specs[1].name}"
        else:
            return f"{active_specs[0].name} +{len(active_specs) - 1}"

    def _get_button_icons_html(self, active_specs: List[Specialization]) -> str:
        """Generuje HTML z ikonami wybranych specjalizacji."""
        if not active_specs:
            return ""
        # Pokaż max 3 ikony
        icons = [self._get_icon_html(spec, 18) for spec in active_specs[:3]]
        if len(active_specs) > 3:
            icons.append(f'<span style="font-size:12px;color:white;">+{len(active_specs) - 3}</span>')
        return ''.join(icons)

    def create(self) -> None:
        """Tworzy komponent przełącznika."""
        active_specs = self.spec_manager.get_active_list()

        if self.compact:
            self._create_compact(active_specs)
        else:
            self._create_expanded(active_specs)

    def _create_compact(self, active_specs: List[Specialization]) -> None:
        """Kompaktowy widok - dropdown button z checkboxami."""
        specs = self.spec_manager.get_all()
        button_label = self._get_button_label(active_specs)

        with ui.button().props('flat dense').classes('text-white bg-white/10 hover:bg-white/20') as self.button:
            with ui.row().classes('items-center gap-1'):
                self.button_icons = ui.html(self._get_button_icons_html(active_specs), sanitize=False)
                self.button_label = ui.label(button_label).classes('text-white max-w-[200px] truncate')
                ui.icon('arrow_drop_down').classes('text-white/70')

            with ui.menu().classes('bg-white text-gray-900 min-w-[200px]') as self.menu:
                # Header
                with ui.item().props('disable').classes('bg-gray-100 text-gray-600'):
                    ui.label('Wybierz specjalizacje').classes('text-xs uppercase tracking-wide')

                ui.separator()

                if not specs:
                    ui.item('Brak specjalizacji').props('disabled').classes('text-gray-700')
                else:
                    for spec in specs:
                        is_active = self.spec_manager.is_active(spec.id)
                        self._create_menu_item(spec, is_active)

        if self.menu and self.button:
            self.button.on('click', lambda: self.menu.open())

    def _create_menu_item(self, spec: Specialization, is_active: bool) -> None:
        """Tworzy pozycję menu z checkboxem."""
        with ui.item(on_click=lambda s=spec: self._on_toggle(s)).classes('text-gray-900 hover:bg-gray-100'):
            with ui.row().classes('items-center gap-2 w-full'):
                # Checkbox (wizualny)
                check = ui.icon(
                    'check_box' if is_active else 'check_box_outline_blank',
                    size='sm'
                ).classes('text-blue-600' if is_active else 'text-gray-400')
                self.item_checks[spec.id] = check

                # Ikona specjalizacji
                ui.html(self._get_icon_html(spec, 18), sanitize=False)

                # Nazwa
                ui.label(spec.name).classes('flex-grow')

    def _create_expanded(self, active_specs: List[Specialization]) -> None:
        """Rozwinięty widok - chips z checkboxami."""
        active_ids = [s.id for s in active_specs]

        with ui.row().classes('items-center gap-1 flex-wrap'):
            for spec in self.spec_manager.get_all():
                is_active = spec.id in active_ids
                btn_classes = 'rounded-full px-3 py-1 text-sm transition-all'

                if is_active:
                    btn_classes += ' bg-white text-gray-800 font-bold shadow-md'
                else:
                    btn_classes += ' bg-white/10 text-white hover:bg-white/20'

                with ui.button(on_click=lambda s=spec: self._on_toggle(s)).props('flat dense unelevated').classes(btn_classes):
                    with ui.row().classes('items-center gap-1'):
                        if is_active:
                            ui.icon('check', size='xs').classes('text-green-600')
                        ui.html(self._get_icon_html(spec, 16), sanitize=False)
                        ui.label(spec.name)

    def _on_toggle(self, spec: Specialization) -> None:
        """Obsługa przełączenia specjalizacji (multi-select)."""
        is_now_active = self.spec_manager.toggle_active(spec.id)

        # Aktualizuj checkbox w menu
        if spec.id in self.item_checks:
            icon = self.item_checks[spec.id]
            try:
                icon._props['name'] = 'check_box' if is_now_active else 'check_box_outline_blank'
                icon.classes(remove='text-gray-400 text-blue-600')
                icon.classes(add='text-blue-600' if is_now_active else 'text-gray-400')
                icon.update()
            except Exception:
                pass

        # Aktualizuj przycisk
        active_specs = self.spec_manager.get_active_list()
        if self.button_icons:
            self.button_icons.set_content(self._get_button_icons_html(active_specs))
        if self.button_label:
            self.button_label.text = self._get_button_label(active_specs)

        # Callback z listą aktywnych specjalizacji
        if self.on_change:
            self.on_change(active_specs)

        # Notyfikacja
        if is_now_active:
            ui.notify(f'Dodano: {spec.name}', type='positive', position='bottom')
        else:
            ui.notify(f'Usunięto: {spec.name}', type='info', position='bottom')

    def refresh(self) -> None:
        """Odświeża stan przełącznika."""
        active_specs = self.spec_manager.get_active_list()
        active_ids = [s.id for s in active_specs]

        if self.button_icons:
            self.button_icons.set_content(self._get_button_icons_html(active_specs))
        if self.button_label:
            self.button_label.text = self._get_button_label(active_specs)

        for spec_id, icon in self.item_checks.items():
            try:
                is_active = spec_id in active_ids
                icon._props['name'] = 'check_box' if is_active else 'check_box_outline_blank'
                icon.classes(remove='text-gray-400 text-blue-600')
                icon.classes(add='text-blue-600' if is_active else 'text-gray-400')
                icon.update()
            except Exception:
                pass


def create_spec_switcher(
    on_change: Optional[Callable[[List[Specialization]], None]] = None,
    compact: bool = True
) -> SpecializationSwitcher:
    """
    Tworzy i zwraca przełącznik specjalizacji (multi-select).

    Args:
        on_change: Callback wywoływany po zmianie specjalizacji (otrzymuje listę)
        compact: True = dropdown, False = chips

    Returns:
        Instancja SpecializationSwitcher
    """
    switcher = SpecializationSwitcher(on_change=on_change, compact=compact)
    switcher.create()
    return switcher
