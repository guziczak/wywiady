"""
Prompter Panel Component
Panel suflera z kartami sugestii i kontrolkami.
"""

from nicegui import ui
from typing import Callable, Optional, TYPE_CHECKING

from app_ui.live.components.suggestion_card import (
    SuggestionCard,
    PlaceholderCard,
    EmptyStateCard
)

if TYPE_CHECKING:
    from app_ui.live.live_state import LiveState, SessionStatus


class PrompterPanel:
    """
    Panel suflera AI.
    - Jasny design spójny z aplikacją
    - Responsywne karty
    - Kontrolki sesji (START/STOP, Zakończ)
    """

    def __init__(
        self,
        state: 'LiveState',
        app_instance=None,
        on_toggle_session: Optional[Callable] = None,
        on_finish: Optional[Callable] = None,
        on_card_click: Optional[Callable[[str], None]] = None
    ):
        self.state = state
        self.app_instance = app_instance
        self.on_toggle_session = on_toggle_session
        self.on_finish = on_finish
        self.on_card_click = on_card_click

        # UI refs
        self.container = None
        self.cards_container = None
        self.action_btn = None
        self.status_badge = None
        self._is_loading = False
        self._client = None  # NiceGUI client context

    def create(self) -> ui.card:
        """Tworzy panel suflera."""
        
        print(f"[PROMPTER] create() called, ui.context.client = {ui.context.client}", flush=True)

        self.container = ui.card().classes(
            'w-full '
            'bg-slate-50 '
            'border-t-4 border-blue-500 '
            'rounded-none rounded-b-xl '
            'shadow-lg '
            'p-4 sm:p-6'
        )

        with self.container:
            # Header z kontrolkami
            self._create_header()

            # Kontener na karty
            self._create_cards_container()

        # Capture client context for background updates
        self._client = ui.context.client
        print(f"[PROMPTER] _client set to: {self._client}", flush=True)

        # Subscribe to state changes
        self.state.on_suggestions_change(self._on_suggestions_change)
        self.state.on_status_change(self._on_status_change)

        return self.container

    def _create_header(self):
        """Tworzy nagłówek z kontrolkami."""
        with ui.row().classes(
            'w-full justify-between items-center mb-4 flex-wrap gap-2'
        ):
            # Tytuł
            with ui.row().classes('items-center gap-2'):
                ui.icon('psychology', size='sm').classes('text-blue-600')
                ui.label('AI Asystent').classes(
                    'text-lg font-semibold text-gray-700'
                )

            # Kontrolki
            with ui.row().classes('items-center gap-3'):
                # Status badge
                self.status_badge = ui.badge('GOTOWY', color='gray').classes(
                    'text-xs'
                ).props('aria-live="polite"')

                # Przycisk START/STOP
                self.action_btn = ui.button(
                    'START',
                    icon='mic',
                    color='green',
                    on_click=self._handle_toggle
                ).props('size=md').classes('min-w-[100px]')

                # Przycisk Zakończ
                ui.button(
                    'Zakończ',
                    icon='check_circle',
                    color='blue',
                    on_click=self._handle_finish
                ).props('outline size=md')

    def _create_cards_container(self):
        """Tworzy kontener na karty sugestii."""
        self.cards_container = ui.row().classes(
            'w-full '
            'justify-center '
            'gap-4 '
            'min-h-[160px]'
        )

        with self.cards_container:
            self._render_cards()

    def _render_cards(self):
        """Renderuje karty na podstawie stanu."""
        from app_ui.live.live_state import SessionStatus

        # Wyczyść istniejące karty
        self.cards_container.clear()

        with self.cards_container:
            # Sprawdź status sesji
            if self.state.status == SessionStatus.IDLE:
                # Sesja nieaktywna - empty state
                for _ in range(3):
                    EmptyStateCard("Naciśnij START").create()
                return

            # Sesja aktywna
            suggestions = self.state.suggestions

            if not suggestions and not self._is_loading:
                # Brak sugestii - placeholdery
                PlaceholderCard("Analizuję rozmowę...").create()
                PlaceholderCard("Szukam pytań...").create()
                PlaceholderCard("Czekam na kontekst...").create()
                return

            if self._is_loading and not suggestions:
                # Ładowanie
                for _ in range(3):
                    PlaceholderCard("Generuję...").create()
                return

            # Mamy sugestie - renderuj karty
            for suggestion in suggestions:
                if suggestion.question == "Brak konfiguracji AI":
                    self._render_config_error_card()
                else:
                    SuggestionCard(
                        question=suggestion.question,
                        on_click=self._handle_card_click,
                        used=suggestion.used
                    ).create()

            # Dopełnij do 3 kart jeśli mniej i nie ma błędu konfiguracji
            if not any(s.question == "Brak konfiguracji AI" for s in suggestions):
                remaining = 3 - len(suggestions)
                for _ in range(remaining):
                    PlaceholderCard("Szukam więcej...").create()

    def _render_config_error_card(self):
        """Renderuje kartę konfiguracji (modern design)."""
        with ui.card().classes(
            'w-full sm:w-1/3 min-w-[280px] '
            'bg-gradient-to-br from-indigo-50 to-white '
            'border border-indigo-100 '
            'cursor-pointer hover:shadow-lg transition-all duration-300 group'
        ).on('click', self._open_config_dialog):
            with ui.column().classes('w-full h-full items-center justify-center gap-3 p-4'):
                # Icon container with pulse effect
                with ui.element('div').classes('relative'):
                    with ui.element('div').classes('absolute inset-0 bg-indigo-200 rounded-full animate-ping opacity-20'):
                        pass
                    ui.icon('auto_awesome', size='md').classes('text-indigo-600 relative z-10')
                
                with ui.column().classes('items-center gap-1'):
                    ui.label('Aktywuj Asystenta AI').classes(
                        'font-bold text-indigo-900 text-lg group-hover:text-indigo-700 transition-colors'
                    )
                    ui.label('Wymagana konfiguracja').classes('text-xs text-indigo-500 font-medium uppercase tracking-wide')
                
                ui.label('Kliknij, aby połączyć z Gemini lub Claude').classes(
                    'text-sm text-gray-500 text-center leading-tight'
                )

    def _open_config_dialog(self):
        """Otwiera nowoczesny dialog konfiguracji API."""
        if not self.app_instance:
             ui.notify("Błąd: Brak dostępu do aplikacji", type='negative')
             return

        # Pobierz aktualne wartości
        current_gemini = self.app_instance.config.get("api_key", "")
        current_claude = self.app_instance.config.get("session_key", "")
        
        with ui.dialog() as dialog, ui.card().classes('w-[500px] max-w-full p-0 overflow-hidden'):
            
            # Header
            with ui.row().classes('w-full bg-slate-50 p-4 border-b border-gray-100 items-center justify-between'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('tune', size='sm').classes('text-slate-600')
                    ui.label('Konfiguracja AI').classes('text-lg font-bold text-slate-800')
                ui.button(icon='close', on_click=dialog.close).props('flat dense round').classes('text-gray-400')

            # Content
            with ui.column().classes('w-full p-6 gap-6'):
                
                # Intro text
                ui.label('Aby korzystać z sugestii pytań i walidacji, połącz aplikację z modelem AI.').classes('text-sm text-gray-600')

                # Tabs (Visual only for now, simple toggle logic)
                with ui.tabs().classes('w-full text-blue-600') as tabs:
                    gemini_tab = ui.tab('Gemini Cloud', icon='cloud')
                    claude_tab = ui.tab('Claude AI', icon='smart_toy')

                with ui.tab_panels(tabs, value=gemini_tab).classes('w-full'):
                    
                    # === GEMINI PANEL ===
                    with ui.tab_panel(gemini_tab):
                        with ui.column().classes('w-full gap-4'):
                            with ui.row().classes('items-start gap-3 bg-blue-50 p-3 rounded-lg border border-blue-100'):
                                ui.icon('info', size='sm').classes('text-blue-500 mt-1')
                                with ui.column().classes('gap-1'):
                                    ui.label('Polecane (Szybkie & Darmowe)').classes('font-bold text-blue-800 text-xs uppercase')
                                    ui.label('Gemini 2.0 Flash oferuje świetną jakość przy bardzo niskich opóźnieniach.').classes('text-xs text-blue-700')

                            ui.label('Klucz API Gemini:').classes('text-sm font-medium text-gray-700')
                            gemini_input = ui.input(
                                password=True, 
                                value=current_gemini,
                                placeholder="AIzaSy..."
                            ).props('outlined dense').classes('w-full')

                            with ui.row().classes('w-full justify-between items-center'):
                                ui.link('Pobierz darmowy klucz', 'https://aistudio.google.com/app/apikey', new_tab=True).classes('text-xs text-blue-600 hover:underline')
                                ui.button('Zapisz Gemini', icon='save', on_click=lambda: self._save_config(dialog, api_key=gemini_input.value)).props('color=blue')

                    # === CLAUDE PANEL ===
                    with ui.tab_panel(claude_tab):
                        with ui.column().classes('w-full gap-4'):
                            with ui.row().classes('items-start gap-3 bg-orange-50 p-3 rounded-lg border border-orange-100'):
                                ui.icon('warning', size='sm').classes('text-orange-500 mt-1')
                                with ui.column().classes('gap-1'):
                                    ui.label('Wymaga Session Key').classes('font-bold text-orange-800 text-xs uppercase')
                                    ui.label('Wymaga manualnego pobrania klucza sesji z przeglądarki (zaawansowane).').classes('text-xs text-orange-700')

                            ui.label('Claude Session Key:').classes('text-sm font-medium text-gray-700')
                            claude_input = ui.input(
                                password=True, 
                                value=current_claude,
                                placeholder="sk-ant-sid01-..."
                            ).props('outlined dense').classes('w-full')

                            ui.button('Zapisz Claude', icon='save', on_click=lambda: self._save_config(dialog, session_key=claude_input.value)).props('color=orange w-full')

            dialog.open()

    def _save_config(self, dialog: ui.dialog, api_key: str = None, session_key: str = None):
        """Zapisuje konfigurację."""
        if not self.app_instance or not hasattr(self.app_instance, 'config_manager'):
            ui.notify("Błąd: Brak menedżera konfiguracji", type='negative')
            return

        updates = {}
        if api_key is not None:
            updates['api_key'] = api_key.strip()
        if session_key is not None:
            updates['session_key'] = session_key.strip()

        try:
            self.app_instance.config_manager.update(**updates)
            
            # Update local config reference if needed
            if hasattr(self.app_instance, 'config'):
                self.app_instance.config.update(updates)
                
            ui.notify("Zapisano ustawienia!", type='positive')
            dialog.close()
            
            # Refresh suggestions
            if hasattr(self.state, 'refresh_suggestions'):
                self.state.refresh_suggestions()
                
        except Exception as e:
            ui.notify(f"Błąd zapisu: {e}", type='negative')

    def _on_suggestions_change(self):
        """Callback gdy zmienią się sugestie (może być z background thread)."""
        # Sugestie przychodzą z AI controller który działa async
        if self._client is None:
            return
        try:
            with self._client:
                self._render_cards()
        except Exception:
            pass

    def _on_status_change(self):
        """Callback gdy zmieni się status sesji (wywoływany synchronicznie z UI)."""
        from app_ui.live.live_state import SessionStatus

        print(f"[PROMPTER] Status change: {self.state.status}", flush=True)
        
        # Ten callback jest wywoływany synchronicznie z UI thread
        # więc nie potrzebujemy context managera
        try:
            if self.state.status == SessionStatus.RECORDING:
                self.action_btn.props('color=red icon=stop')
                self.action_btn.text = 'STOP'
                self.status_badge.text = 'NAGRYWANIE'
                self.status_badge.props('color=red')
            else:
                self.action_btn.props('color=green icon=mic')
                self.action_btn.text = 'START'
                self.status_badge.text = 'GOTOWY'
                self.status_badge.props('color=gray')

            self._render_cards()
            print("[PROMPTER] UI updated!", flush=True)
        except Exception as e:
            print(f"[PROMPTER] Error: {e}", flush=True)

    def _handle_toggle(self):
        """Obsługuje przycisk START/STOP."""
        if self.on_toggle_session:
            self.on_toggle_session()

    def _handle_finish(self):
        """Obsługuje przycisk Zakończ."""
        if self.on_finish:
            self.on_finish()

    def _handle_card_click(self, question: str):
        """Obsługuje kliknięcie w kartę."""
        if self.on_card_click:
            self.on_card_click(question)

    def set_loading(self, loading: bool):
        """Ustawia stan ładowania (wywoływany synchronicznie z UI)."""
        self._is_loading = loading
        try:
            self._render_cards()
        except Exception:
            pass
