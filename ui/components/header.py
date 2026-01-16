from nicegui import ui

def create_header(app):
    """Tworzy nagłówek aplikacji."""
    with ui.header().classes('bg-blue-700 text-white'):
        with ui.row().classes('w-full items-center justify-between px-4'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('medical_services', size='lg')
                ui.label('Wywiad+').classes('text-2xl font-bold')

            # Status indicator
            with ui.row().classes('items-center gap-2 bg-white/10 rounded-full px-3 py-1'):
                app.status_indicator = ui.element('div').classes('w-3 h-3 rounded-full bg-gray-400')
                app.status_label = ui.label('Inicjalizacja...').classes('text-sm')
                # Przycisk Anuluj
                app.cancel_button = ui.button('Anuluj', icon='close', on_click=app._on_cancel_click).props('flat dense size=sm').classes('text-white bg-red-500/50 hover:bg-red-500')
                app.cancel_button.set_visibility(False)

            with ui.row().classes('items-center gap-4'):
                ui.label('v2.0').classes('text-sm opacity-75')
                ui.button(icon='dark_mode', on_click=app.dark_mode.toggle).props('flat round dense').classes('text-white')
