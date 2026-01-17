from nicegui import ui

def create_settings_section(app):
    """Tworzy sekcję ustawień (urządzenia, backend, klucze)."""
    
    # === DEVICE SELECTION ===
    with ui.expansion('Urzadzenie do transkrypcji', icon='memory').classes('w-full'):
        with ui.column().classes('w-full gap-4 p-2'):
            ui.label('Wybierz urzadzenie do przetwarzania audio:').classes('text-gray-600')

            app.device_cards_container = ui.row().classes('gap-4 flex-wrap')
            # Karty urządzeń są generowane dynamicznie przez app.refresh_device_cards()
            # Wywołamy to na końcu build_ui
            
            with ui.row().classes('items-center gap-2 mt-2'):
                ui.icon('info', size='sm').classes('text-blue-500')
                ui.label('Zalecane uzycie GPU lub NPU dla szybszego dzialania.').classes('text-sm text-gray-500 italic')

    # === BACKEND & MODELS ===
    with ui.expansion('Silnik transkrypcji', icon='settings_voice').classes('w-full'):
        with ui.column().classes('w-full gap-4 p-2'):
            ui.label('Wybierz silnik (backend):').classes('text-gray-600')
            
            # Backend buttons
            backends_info = {}
            if app.transcriber_manager:
                for b in app.transcriber_manager.get_available_backends():
                    backends_info[b.type.value] = b

            backend_options = [
                ('gemini_cloud', 'Gemini Cloud', 'cloud', 'Online API'),
                ('faster_whisper', 'Faster Whisper', 'speed', 'Najszybszy offline'),
                ('openai_whisper', 'OpenAI Whisper', 'psychology', 'Oryginalny'),
                ('openvino_whisper', 'OpenVINO', 'memory', 'Intel NPU/GPU'),
            ]

            current_backend = app.config.get("transcriber_backend", "gemini_cloud")

            app.backend_buttons_container = ui.row().classes('gap-3 flex-wrap')
            with app.backend_buttons_container:
                for key, name, icon, desc in backend_options:
                    is_current = (key == current_backend)
                    info = backends_info.get(key)
                    is_installed = info.is_installed if info else True

                    with ui.card().classes(
                        f'w-44 cursor-pointer transition-all {"ring-2 ring-blue-500 bg-blue-50" if is_current else "hover:shadow-md"} {"opacity-60" if not is_installed else ""}'
                    ).on('click', lambda k=key: app.select_backend(k)):
                        with ui.column().classes('items-center gap-1 p-3'):
                            ui.icon(icon, size='md').classes('text-blue-600' if is_current else 'text-gray-500')
                            ui.label(name).classes('font-bold text-sm')
                            ui.label(desc).classes('text-xs text-gray-500')

                            if not is_installed:
                                ui.badge('Wymaga instalacji', color='orange').classes('mt-1')
                            elif is_current:
                                ui.badge('Aktywny', color='green').classes('mt-1')

            ui.separator()

            # Models
            ui.label('Dostepne modele:').classes('font-medium mt-4')
            app.model_cards_container = ui.column().classes('w-full gap-2')
            # Modele są odświeżane dynamicznie

    # === API KEYS ===
    with ui.expansion('Klucze API', icon='key').classes('w-full'):
        with ui.column().classes('w-full gap-4 p-2'):

            # Gemini API Key
            with ui.row().classes('w-full items-end gap-2'):
                app.gemini_input = ui.input(
                    'Gemini API Key',
                    password=True,
                    password_toggle_button=True,
                    value=app.config.get("api_key", "")
                ).classes('flex-1').on(
                    'change', lambda: app.config.update({"api_key": app.gemini_input.value})
                )
                ui.button(
                    'Pobierz',
                    icon='open_in_new',
                    on_click=app._open_gemini_studio
                ).props('flat dense').tooltip('Otworz Google AI Studio')
                ui.button(
                    icon='delete',
                    on_click=lambda: (setattr(app.gemini_input, 'value', ''), app.config.update({"api_key": ""}), app.config.save())
                ).props('flat dense').tooltip('Wyczyść klucz')

            # Claude Session Key
            with ui.row().classes('w-full items-end gap-2'):
                app.session_input = ui.input(
                    'Claude Session Key',
                    password=True,
                    password_toggle_button=True,
                    value=app.config.get("session_key", ""),
                    placeholder="sk-ant-sid01-..."
                ).classes('flex-1').on(
                    'change', lambda: app.config.update({"session_key": app.session_input.value})
                )
                ui.button(
                    'Auto',
                    icon='extension',
                    on_click=app._auto_get_key
                ).props('flat dense').tooltip('Zainstaluj rozszerzenie i pobierz klucz (wymaga Admin)')
                ui.button(
                    icon='delete',
                    on_click=lambda: (setattr(app.session_input, 'value', ''), app.config.update({"session_key": ""}), app.config.save())
                ).props('flat dense').tooltip('Wyczyść klucz')

            # Status
            app.claude_status_label = ui.label('')
            app._update_claude_status()

            # Extraction progress (hidden by default)
            app.extraction_spinner = ui.spinner('dots', size='sm').classes('hidden')

            ui.button('Zapisz ustawienia', icon='save', on_click=app.save_settings).classes('mt-2')
