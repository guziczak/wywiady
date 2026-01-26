from nicegui import ui
import asyncio

_GRID_CHECKBOX_STYLES_INJECTED = False

def _inject_grid_checkbox_styles():
    """Wstrzykuje style dla lepszej widoczności checkboxów w AG Grid."""
    global _GRID_CHECKBOX_STYLES_INJECTED
    if _GRID_CHECKBOX_STYLES_INJECTED:
        return
    _GRID_CHECKBOX_STYLES_INJECTED = True

    ui.add_head_html('''
    <style>
    /* Ujednolicone wysokosci naglowka/wierszy (fallback dla roznych theme) */
    .nicegui-aggrid {
        --ag-header-height: 32px;
        --ag-row-height: 32px;
    }

    /* Większe i bardziej widoczne checkboxy w AG Grid */
    .nicegui-aggrid .ag-checkbox-input-wrapper {
        width: 20px !important;
        height: 20px !important;
    }

    .nicegui-aggrid .ag-checkbox-input-wrapper input {
        width: 18px !important;
        height: 18px !important;
        cursor: pointer;
    }

    .nicegui-aggrid .ag-checkbox-input-wrapper::after {
        width: 18px !important;
        height: 18px !important;
        border: 2px solid #3b82f6 !important;
        border-radius: 4px;
    }

    .nicegui-aggrid .ag-checkbox-input-wrapper.ag-checked::after {
        background-color: #3b82f6 !important;
        border-color: #3b82f6 !important;
    }

    /* Podświetlenie zaznaczonego wiersza */
    .nicegui-aggrid .ag-row-selected {
        background-color: rgba(59, 130, 246, 0.15) !important;
    }

    .nicegui-aggrid .ag-row-selected:hover {
        background-color: rgba(59, 130, 246, 0.25) !important;
    }

    /* Header checkbox */
    .nicegui-aggrid .ag-header-select-all {
        margin-right: 8px;
    }

    /* Pinned column z checkboxem */
    .nicegui-aggrid .ag-pinned-left-cols-container .ag-cell {
        display: flex;
        align-items: center;
        justify-content: center;
    }
    </style>
    ''')


def _force_grid_setup(grid, column_defs):
    """Wymusza ustawienie kolumn i odswiezenie naglowkow po inicjalizacji."""
    try:
        grid.run_grid_method('setColumnDefs', column_defs)
        grid.run_grid_method('refreshHeader')
        _schedule_size_to_fit(grid)
    except Exception:
        pass


def _schedule_size_to_fit(grid, attempts=6, delay=0.1):
    async def _try(attempt):
        try:
            width = await grid.client.run_javascript(
                f"return getElement({grid.id})?.clientWidth || 0",
                timeout=2,
            )
            if width and width > 50:
                grid.run_grid_method('sizeColumnsToFit')
                return
        except Exception:
            pass
        if attempt < attempts:
            ui.timer(delay, lambda: asyncio.create_task(_try(attempt + 1)), once=True)

    asyncio.create_task(_try(0))


def _render_diagnosis_grid(app, column_defs, row_data):
    app.diagnosis_grid = ui.aggrid({
        'columnDefs': column_defs,
        'rowData': row_data,
        'rowSelection': 'multiple',
        'suppressRowClickSelection': True,
        'rowMultiSelectWithClick': True,
        'headerHeight': 32,
        'rowHeight': 32,
    }, theme='balham').classes('w-full ag-theme-balham').style('height: 12rem; width: 100%;')
    app.diagnosis_grid.on('gridReady', lambda _: _force_grid_setup(app.diagnosis_grid, column_defs))
    return app.diagnosis_grid


def _render_procedure_grid(app, column_defs, row_data):
    app.procedure_grid = ui.aggrid({
        'columnDefs': column_defs,
        'rowData': row_data,
        'rowSelection': 'multiple',
        'suppressRowClickSelection': True,
        'rowMultiSelectWithClick': True,
        'headerHeight': 32,
        'rowHeight': 32,
    }, theme='balham').classes('w-full ag-theme-balham').style('height: 16rem; width: 100%;')
    app.procedure_grid.on('gridReady', lambda _: _force_grid_setup(app.procedure_grid, column_defs))
    return app.procedure_grid


def create_results_section(app):
    """Tworzy sekcję wyników (generowanie opisu)."""

    # Wstrzyknij style dla checkboxów
    _inject_grid_checkbox_styles()

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
            with ui.row().classes('w-full items-center gap-2'):
                ui.icon('medical_services', size='sm').classes('text-blue-600')
                ui.label('Diagnozy (ICD-10)').classes('font-medium text-gray-700')
                ui.label('— zaznacz które uwzględnić').classes('text-sm text-gray-400')

            diagnosis_column_defs = [
                {
                    'headerName': '',
                    'field': 'selected',
                    'checkboxSelection': True,
                    'headerCheckboxSelection': True,
                    'width': 50,
                    'maxWidth': 50,
                    'pinned': 'left'
                },
                {'headerName': 'Kod', 'field': 'kod', 'width': 100},
                {'headerName': 'Nazwa', 'field': 'nazwa', 'flex': 1},
                {'headerName': 'Lokalizacja / Ząb', 'field': 'zab', 'width': 140},
                {'headerName': 'Opis', 'field': 'opis_tekstowy', 'flex': 1}
            ]
            app.diagnosis_grid_container = ui.element('div').classes('w-full')
            with app.diagnosis_grid_container:
                _render_diagnosis_grid(app, diagnosis_column_defs, [])

            # Tabela Procedur
            with ui.row().classes('w-full items-center gap-2'):
                ui.icon('healing', size='sm').classes('text-green-600')
                ui.label('Procedury (ICD-9 / NFZ)').classes('font-medium text-gray-700')
                ui.label('— zaznacz które uwzględnić').classes('text-sm text-gray-400')

            procedure_column_defs = [
                {
                    'headerName': '',
                    'field': 'selected',
                    'checkboxSelection': True,
                    'headerCheckboxSelection': True,
                    'width': 50,
                    'maxWidth': 50,
                    'pinned': 'left'
                },
                {'headerName': 'Kod', 'field': 'kod', 'width': 100},
                {'headerName': 'Nazwa', 'field': 'nazwa', 'flex': 1},
                {'headerName': 'Lokalizacja / Ząb', 'field': 'zab', 'width': 140},
                {'headerName': 'Opis', 'field': 'opis_tekstowy', 'flex': 1}
            ]
            app.procedure_grid_container = ui.element('div').classes('w-full')
            with app.procedure_grid_container:
                _render_procedure_grid(app, procedure_column_defs, [])
            
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
