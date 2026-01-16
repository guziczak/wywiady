from nicegui import ui

def create_recording_section(app):
    """Tworzy sekcję nagrywania i transkrypcji."""
    
    with ui.card().classes('w-full'):
        with ui.column().classes('w-full gap-4'):
            ui.label('Nagrywanie wywiadu').classes('text-xl font-bold')
            ui.separator()

            with ui.row().classes('w-full items-center justify-center gap-4'):
                # Record button with tooltip
                with ui.element('div'):
                    app.record_button = ui.button(
                        'Nagrywaj',
                        icon='mic',
                        on_click=app.toggle_recording,
                        color='primary'
                    ).classes('text-lg px-8 py-4')
                    app.record_tooltip = ui.tooltip('Kliknij aby nagrać')

                app.record_status = ui.label('Gotowy do nagrywania').classes('text-gray-500')
                # Update initial state immediately
                app._update_record_button()

            app.transcript_area = ui.textarea(
                label='Transkrypcja wywiadu',
                placeholder='Tutaj pojawi sie transkrypcja nagrania...'
            ).classes('w-full').props('rows=5').on(
                'keydown.ctrl.enter', 
                app.generate_description
            )

            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Wyczysc', icon='delete', on_click=lambda: setattr(app.transcript_area, 'value', '')).props('flat')
                ui.button('Kopiuj', icon='content_copy', on_click=lambda: app.copy_to_clipboard(app.transcript_area.value or '', 'Transkrypcja')).props('flat')
