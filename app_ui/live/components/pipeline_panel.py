"""
Pipeline Panel Component
Nowoczesny panel prezentujÄ…cy etapowy pipeline transkrypcji + ustawienia.
"""

from typing import Callable, Dict, Optional
from nicegui import ui
from app_ui.live.components.animation_styles import inject_animation_styles


class PipelinePanel:
    """Panel z pipeline modeli transkrypcji i konfiguracjÄ…."""

    PRESETS = {
        "Szybkość": {
            "enable_medium": False,
            "enable_large": False,
            "improved_interval": 7.0,
            "silence_threshold": 2.5,
        },
        "Balans": {
            "enable_medium": True,
            "enable_large": False,
            "improved_interval": 5.0,
            "silence_threshold": 2.0,
        },
        "Dokładność": {
            "enable_medium": True,
            "enable_large": True,
            "improved_interval": 4.0,
            "silence_threshold": 1.5,
        },
    }

    STATE_STYLES = {
        "ready": {
            "card": "bg-emerald-50 border-emerald-200",
            "badge": ("Gotowy", "green"),
        },
        "loading": {
            "card": "bg-amber-50 border-amber-200 animate-processing",
            "badge": ("Ładowanie", "orange"),
        },
        "idle": {
            "card": "bg-slate-50 border-slate-200",
            "badge": ("Oczekuje", "gray"),
        },
        "disabled": {
            "card": "bg-slate-50 border-slate-200",
            "badge": ("Wyłączony", "gray"),
        },
        "error": {
            "card": "bg-rose-50 border-rose-200",
            "badge": ("Błąd", "red"),
        },
    }

    def __init__(
        self,
        get_config: Callable[[], Dict],
        on_apply: Optional[Callable[[Dict], None]] = None,
    ):
        self.get_config = get_config
        self.on_apply = on_apply
        self.container = None
        self.summary_label = None
        self.preset_label = None
        self.stage_ui: Dict[str, Dict] = {}

    def create(self) -> ui.card:
        """Tworzy panel pipeline."""
        inject_animation_styles()
        with ui.card().classes(
            'w-full max-w-6xl mx-auto '
            'bg-white border border-slate-200 '
            'rounded-xl shadow-sm '
            'p-3 sm:p-4 '
            'animate-fade-in'
        ) as self.container:
            # Header
            with ui.row().classes('w-full items-center justify-between gap-3 flex-wrap'):
                with ui.column().classes('gap-1'):
                    ui.label('Pipeline transkrypcji').classes('text-sm font-semibold text-slate-700')
                    self.preset_label = ui.label('').classes('text-xs text-slate-500')

                with ui.row().classes('items-center gap-2'):
                    self.summary_label = ui.label('').classes('text-xs text-slate-500')
                    ui.button(
                        icon='tune',
                        on_click=self._open_config_dialog
                    ).props('flat dense round').classes('text-slate-500 hover:text-slate-700')

            # Pipeline steps
            with ui.row().classes('w-full items-center gap-2 sm:gap-3 flex-wrap mt-2'):
                self._create_stage_card(
                    key='tiny',
                    role='LIVE',
                    title='Tiny',
                    subtitle='Szybki podgląd na żywo'
                )
                ui.icon('east').classes('hidden sm:inline-block text-slate-300')
                self._create_stage_card(
                    key='medium',
                    role='REFINE',
                    title='Medium',
                    subtitle='Doprecyzowanie kontekstu'
                )
                ui.icon('east').classes('hidden sm:inline-block text-slate-300')
                self._create_stage_card(
                    key='large',
                    role='FINAL',
                    title='Large',
                    subtitle='Finalna wersja transkrypcji'
                )

        return self.container

    def _create_stage_card(self, key: str, role: str, title: str, subtitle: str) -> None:
        base_classes = (
            'flex-1 min-w-[180px] '
            'border rounded-xl '
            'p-3 '
            'transition-all-smooth'
        )
        with ui.card().classes(f'{base_classes} bg-slate-50 border-slate-200') as card:
            with ui.row().classes('w-full items-center justify-between'):
                ui.label(role).classes('text-[10px] uppercase tracking-widest text-slate-500')
                status_badge = ui.badge('Oczekuje', color='gray').classes('text-[10px]')

            ui.label(title).classes('text-base font-semibold text-slate-800')
            ui.label(subtitle).classes('text-xs text-slate-500')
            detail_label = ui.label('').classes('text-xs text-slate-400 mt-2')

        self.stage_ui[key] = {
            "card": card,
            "base": base_classes,
            "badge": status_badge,
            "detail": detail_label,
        }

    def update(self, status: Dict) -> None:
        """Aktualizuje UI panelu."""
        if not self.container:
            return

        cfg = status.get("config") or self.get_config()
        preset_name = self._resolve_preset(cfg)
        if self.preset_label:
            self.preset_label.text = f"Preset: {preset_name}"
        if self.summary_label:
            self.summary_label.text = status.get("summary", "")

        stages = status.get("stages", {})
        for key, info in stages.items():
            ui_refs = self.stage_ui.get(key)
            if not ui_refs:
                continue
            state = info.get("state", "idle")
            detail = info.get("detail", "")

            style = self.STATE_STYLES.get(state, self.STATE_STYLES["idle"])
            badge_text, badge_color = style["badge"]
            ui_refs["card"].classes(replace=f'{ui_refs["base"]} {style["card"]}')
            ui_refs["badge"].text = badge_text
            ui_refs["badge"].props(f'color={badge_color}')
            ui_refs["detail"].text = detail

    def _resolve_preset(self, cfg: Dict) -> str:
        """Dopasowuje preset do aktualnych wartości."""
        def _eq(a: float, b: float) -> bool:
            return abs(float(a) - float(b)) < 0.01

        for name, preset in self.PRESETS.items():
            if (
                bool(cfg.get("enable_medium")) == preset["enable_medium"]
                and bool(cfg.get("enable_large")) == preset["enable_large"]
                and _eq(cfg.get("improved_interval", 0), preset["improved_interval"])
                and _eq(cfg.get("silence_threshold", 0), preset["silence_threshold"])
            ):
                return name
        return "Własny"

    def _open_config_dialog(self) -> None:
        """Dialog konfiguracji pipeline."""
        cfg = self.get_config()

        with ui.dialog() as dialog, ui.card().classes('w-[560px] max-w-full p-0 overflow-hidden'):
            # Header
            with ui.row().classes('w-full bg-slate-50 p-4 border-b border-slate-100 items-center justify-between'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('tune', size='sm').classes('text-slate-600')
                    ui.label('Ustawienia pipeline').classes('text-lg font-bold text-slate-800')
                ui.button(icon='close', on_click=dialog.close).props('flat dense round').classes('text-slate-400')

            # Content
            with ui.column().classes('w-full p-5 gap-5'):
                ui.label('Dostosuj jakość i szybkość transkrypcji na żywo.').classes('text-sm text-slate-600')

                # Presets
                with ui.row().classes('w-full gap-2 flex-wrap'):
                    ui.label('Presety:').classes('text-xs text-slate-500 uppercase tracking-wide')
                    preset_buttons = {}

                    def _apply_preset(preset: Dict):
                        enable_medium.value = preset["enable_medium"]
                        enable_large.value = preset["enable_large"]
                        improved_slider.value = preset["improved_interval"]
                        silence_slider.value = preset["silence_threshold"]
                        _update_value_labels()

                    for name, preset in self.PRESETS.items():
                        btn = ui.button(
                            name,
                            on_click=lambda p=preset: _apply_preset(p)
                        ).props('outline dense').classes('text-slate-700')
                        preset_buttons[name] = btn

                # Toggles
                with ui.column().classes('w-full gap-2'):
                    enable_medium = ui.switch('Etap REFINE (Medium)', value=cfg.get("enable_medium", True))
                    enable_large = ui.switch('Etap FINAL (Large)', value=cfg.get("enable_large", True))
                    ui.label('Wyłączenie etapu ogranicza zużycie zasobów.').classes('text-xs text-slate-400')

                # Sliders
                with ui.column().classes('w-full gap-3'):
                    with ui.row().classes('w-full items-center justify-between'):
                        ui.label('Częstotliwość refine').classes('text-sm text-slate-700')
                        improved_value = ui.label('').classes('text-xs text-slate-500')
                    improved_slider = ui.slider(min=2, max=10, step=0.5, value=cfg.get("improved_interval", 5.0)).classes('w-full')

                    with ui.row().classes('w-full items-center justify-between'):
                        ui.label('Czułość ciszy (finalizacja)').classes('text-sm text-slate-700')
                        silence_value = ui.label('').classes('text-xs text-slate-500')
                    silence_slider = ui.slider(min=1.0, max=4.0, step=0.5, value=cfg.get("silence_threshold", 2.0)).classes('w-full')

                def _update_value_labels():
                    try:
                        improved_value.text = f"{float(improved_slider.value):.1f}s"
                    except Exception:
                        improved_value.text = "--"
                    try:
                        silence_value.text = f"{float(silence_slider.value):.1f}s"
                    except Exception:
                        silence_value.text = "--"

                _update_value_labels()
                improved_slider.on('change', lambda e: _update_value_labels())
                silence_slider.on('change', lambda e: _update_value_labels())

                # Actions
                with ui.row().classes('w-full justify-end gap-2 pt-2'):
                    ui.button('Anuluj', on_click=dialog.close).props('outline')
                    ui.button(
                        'Zapisz',
                        icon='save',
                        on_click=lambda: self._save_config(
                            dialog,
                            enable_medium.value,
                            enable_large.value,
                            improved_slider.value,
                            silence_slider.value
                        )
                    ).props('color=primary')

            dialog.open()

    def _save_config(self, dialog, enable_medium, enable_large, improved_interval, silence_threshold) -> None:
        """Zapisuje ustawienia pipeline."""
        if self.on_apply:
            self.on_apply({
                "enable_medium": enable_medium,
                "enable_large": enable_large,
                "improved_interval": improved_interval,
                "silence_threshold": silence_threshold,
            })
        ui.notify('Zapisano ustawienia pipeline', type='positive')
        dialog.close()
