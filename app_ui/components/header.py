from nicegui import ui

def create_header(app, show_spec_switcher: bool = True):
    """
    Tworzy nagłówek aplikacji.

    Args:
        app: Instancja aplikacji
        show_spec_switcher: Czy pokazać przełącznik specjalizacji
    """
    # Ensure dark mode state exists
    if not hasattr(app, 'dark_mode'):
        app.dark_mode = ui.dark_mode()

    with ui.header().classes('bg-blue-700 text-white'):
        with ui.row().classes('w-full items-center justify-between px-4'):
            # Logo / Title - Modern Interactive
            with ui.row().classes(
                'items-center gap-3 cursor-pointer group select-none'
            ).on('click', lambda: ui.navigate.to('/')):
                
                # Icon with Glow
                with ui.element('div').classes('relative flex items-center justify-center'):
                    ui.icon('medical_services', size='lg').classes(
                        'transition-all duration-300 group-hover:scale-110 group-hover:rotate-3 relative z-10'
                    )
                    # Glow effect background
                    ui.element('div').classes(
                        'absolute inset-0 bg-white/20 rounded-full blur-md opacity-0 scale-50 transition-all duration-300 group-hover:opacity-100 group-hover:scale-150'
                    )

                # Title with Color/Shadow animation (no layout shift)
                ui.label('Wywiad+').classes(
                    'text-2xl font-bold tracking-tight transition-all duration-300 group-hover:text-blue-200 group-hover:drop-shadow-lg'
                )

            # Specialization switcher
            if show_spec_switcher:
                try:
                    from app_ui.components.spec_switcher import create_spec_switcher
                    # Callback do aktualizacji UI po zmianie specjalizacji
                    on_spec_change = getattr(app, '_on_specialization_change', None)
                    app.spec_switcher = create_spec_switcher(
                        on_change=on_spec_change,
                        compact=True
                    )
                except ImportError:
                    pass  # Spec switcher not available

            # Status indicator
            with ui.row().classes('items-center gap-2 bg-white/10 rounded-full px-3 py-1'):
                app.status_indicator = ui.element('div').classes('w-3 h-3 rounded-full bg-gray-400')
                app.status_label = ui.label('Inicjalizacja...').classes('text-sm')
                # Przycisk Anuluj
                app.cancel_button = ui.button('Anuluj', icon='close', on_click=app._on_cancel_click).props('flat dense size=sm').classes('text-white bg-red-500/50 hover:bg-red-500')
                app.cancel_button.set_visibility(False)

            with ui.row().classes('items-center gap-4'):
                # History Button
                ui.button('Historia', icon='history', on_click=lambda: ui.navigate.to('/history')).props('flat dense').classes('text-white')

                # Live Mode Button
                ui.button('LIVE', icon='sensors', on_click=lambda: ui.navigate.to('/live')).props('flat dense').classes('text-red-300 font-bold border border-red-300 hover:bg-red-900/20')

                ui.label('v2.0').classes('text-sm opacity-75')
                ui.button(icon='dark_mode', on_click=app.dark_mode.toggle).props('flat round dense').classes('text-white')
