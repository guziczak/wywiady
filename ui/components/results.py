from nicegui import ui
import asyncio

def create_results_section(app):
    """Tworzy sekcję wyników (generowanie opisu)."""
    
    # === GENERATION ===
    with ui.card().classes('w-full items-center gap-4'):
        ui.label('Generowanie opisu').classes('font-bold')
        
        # Model selection
        with ui.row().classes('items-center gap-4'):
            ui.label('Model AI:')
            app.gen_model_radio = ui.radio(
                ['Auto', 'Claude', 'Gemini'], 
                value=app.config.get('generation_model', 'Auto')
            ).props('inline').on('change', lambda: (app.config.update({'generation_model': app.gen_model_radio.value}), app.config.save()))
        
        app.generate_button = ui.button(
            'Generuj opis',
            icon='auto_awesome',
            on_click=app.generate_description,
            color='green'
        ).classes('text-lg px-8 py-4')

    # === RESULTS FIELDS ===
    with ui.card().classes('w-full'):
        with ui.column().classes('w-full gap-4'):
            ui.label('Wygenerowany opis').classes('text-xl font-bold')

            ui.separator()

            # Recognition
            with ui.row().classes('w-full items-end gap-2'):
                app.recognition_field = ui.textarea(
                    label='Rozpoznanie (z kodem ICD-10)'
                ).classes('flex-1').props('rows=2')
                ui.button(icon='content_copy', on_click=lambda: app.copy_to_clipboard(app.recognition_field.value or '', 'Rozpoznanie')).props('flat round')

            # Service
            with ui.row().classes('w-full items-end gap-2'):
                app.service_field = ui.textarea(
                    label='Swiadczenie'
                ).classes('flex-1').props('rows=2')
                ui.button(icon='content_copy', on_click=lambda: app.copy_to_clipboard(app.service_field.value or '', 'Swiadczenie')).props('flat round')

            # Procedure
            with ui.row().classes('w-full items-end gap-2'):
                app.procedure_field = ui.textarea(
                    label='Procedura'
                ).classes('flex-1').props('rows=4')
                ui.button(icon='content_copy', on_click=lambda: app.copy_to_clipboard(app.procedure_field.value or '', 'Procedura')).props('flat round')
