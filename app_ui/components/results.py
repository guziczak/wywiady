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
            ui.label('Wygenerowany opis (Struktura)').classes('text-xl font-bold')

            ui.separator()

            # Tabela Diagnoz
            ui.label('Diagnozy (ICD-10)').classes('font-medium text-gray-600')
            app.diagnosis_grid = ui.aggrid({
                'columnDefs': [
                    {'headerName': 'Kod', 'field': 'kod', 'checkboxSelection': True},
                    {'headerName': 'Nazwa', 'field': 'nazwa'},
                    {'headerName': 'Lokalizacja / Ząb', 'field': 'zab'},
                    {'headerName': 'Opis', 'field': 'opis_tekstowy'}
                ],
                'rowData': []
            }).classes('h-48 w-full')

            # Tabela Procedur
            ui.label('Procedury (ICD-9 / NFZ)').classes('font-medium text-gray-600')
            app.procedure_grid = ui.aggrid({
                'columnDefs': [
                    {'headerName': 'Kod', 'field': 'kod', 'checkboxSelection': True},
                    {'headerName': 'Nazwa', 'field': 'nazwa'},
                    {'headerName': 'Lokalizacja / Ząb', 'field': 'zab'},
                    {'headerName': 'Opis', 'field': 'opis_tekstowy'}
                ],
                'rowData': []
            }).classes('h-64 w-full')
            
            # Kopiowanie i zapisywanie
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Kopiuj JSON', icon='code', on_click=app._copy_results_json).props('flat')
                app.save_visit_button = ui.button(
                    'Zapisz wizytę',
                    icon='save',
                    on_click=app._open_save_visit_dialog,
                    color='primary'
                ).props('flat')
                app.save_visit_button.set_visibility(False)  # Pokaż dopiero po wygenerowaniu
