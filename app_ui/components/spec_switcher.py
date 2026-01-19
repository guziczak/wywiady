"""
Przełącznik specjalizacji medycznych.

Komponent UI pozwalający na szybką zmianę aktywnej specjalizacji.
"""

from typing import Optional, Callable
from functools import lru_cache
from pathlib import Path
import re
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
        self.button_icon = None
        self.button_label = None
        self.dropdown = None

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

    def _get_icon_html(self, spec: Specialization, size: int = 18) -> str:
        svg_path = getattr(spec, 'icon_svg', '') or ''
        if svg_path:
            svg = self._load_svg(svg_path)
            if svg:
                return self._svg_with_size(svg, size)
        icon_text = spec.icon or ''
        return f'<span style="font-size:{size}px">{icon_text}</span>'

    def create(self) -> None:
        """Tworzy komponent przełącznika."""
        active_spec = self.spec_manager.get_active()

        if self.compact:
            self._create_compact(active_spec)
        else:
            self._create_expanded(active_spec)

    def _create_compact(self, active_spec: Specialization) -> None:
        """Kompaktowy widok - dropdown button (stabilny w EXE)."""
        def _label(spec: Specialization) -> str:
            return f"{spec.icon} {spec.name}".strip() if getattr(spec, 'icon', None) else spec.name

        specs = self.spec_manager.get_all()
        button_label = _label(active_spec) if active_spec else "Specjalizacja"

        with ui.dropdown_button(button_label, auto_close=True).props(
            'flat dense dropdown-icon="arrow_drop_down" menu-class="bg-white text-gray-900"'
        ).classes('text-white bg-white/10 hover:bg-white/20') as self.dropdown:
            if not specs:
                ui.item('Brak specjalizacji').props('disabled').classes('text-gray-700')
            for spec in specs:
                is_active = spec.id == active_spec.id
                text = _label(spec)
                item = ui.item(text, on_click=lambda s=spec: self._on_select(s)).classes('text-gray-900')
                if is_active:
                    item.classes('font-bold')
        # Extra click handler to ensure open in desktop EXE
        if self.dropdown:
            self.dropdown.on('click', lambda: self.dropdown.open())

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

                with ui.button(on_click=lambda s=spec: self._on_select(s)).props('flat dense unelevated').classes(btn_classes):
                    with ui.row().classes('items-center gap-2'):
                        ui.html(self._get_icon_html(spec, 16), sanitize=False)
                        ui.label(spec.name)

    def _on_select(self, spec: Specialization) -> None:
        """Obsługa wyboru specjalizacji."""
        if spec.id == self.spec_manager.get_active().id:
            return  # Już aktywna

        self.spec_manager.set_active(spec.id)

        # Aktualizuj UI
        if self.button_icon:
            self.button_icon.set_content(self._get_icon_html(spec, 18))
        if self.button_label:
            self.button_label.text = spec.name
        if self.dropdown:
            label = f"{spec.icon} {spec.name}".strip() if getattr(spec, 'icon', None) else spec.name
            self.dropdown.text = label
        if self.menu:
            self.menu.close()

        # Callback
        if self.on_change:
            self.on_change(spec)

        ui.notify(f'Specjalizacja: {spec.name}', type='info')

    def refresh(self) -> None:
        """Odświeża stan przełącznika."""
        active_spec = self.spec_manager.get_active()
        if self.button_icon:
            self.button_icon.set_content(self._get_icon_html(active_spec, 18))
        if self.button_label:
            self.button_label.text = active_spec.name
        if self.dropdown:
            label = f"{active_spec.icon} {active_spec.name}".strip() if getattr(active_spec, 'icon', None) else active_spec.name
            self.dropdown.text = label

    def _on_select_id(self, spec_id: str) -> None:
        """Backward compat (nieużywane w dropdown button)."""
        try:
            spec = next((s for s in self.spec_manager.get_all() if str(s.id) == str(spec_id)), None)
            if spec:
                self._on_select(spec)
        except Exception:
            pass


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
