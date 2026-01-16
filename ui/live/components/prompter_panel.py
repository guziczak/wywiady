"""
Prompter Panel Component
Panel suflera z kartami sugestii i kontrolkami.
"""

from nicegui import ui
from typing import Callable, Optional, TYPE_CHECKING

from ui.live.components.suggestion_card import (
    SuggestionCard,
    PlaceholderCard,
    EmptyStateCard
)

if TYPE_CHECKING:
    from ui.live.live_state import LiveState, SessionStatus


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
        on_toggle_session: Optional[Callable] = None,
        on_finish: Optional[Callable] = None,
        on_card_click: Optional[Callable[[str], None]] = None
    ):
        self.state = state
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
        from ui.live.live_state import SessionStatus

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
                SuggestionCard(
                    question=suggestion.question,
                    on_click=self._handle_card_click,
                    used=suggestion.used
                ).create()

            # Dopełnij do 3 kart jeśli mniej
            remaining = 3 - len(suggestions)
            for _ in range(remaining):
                PlaceholderCard("Szukam więcej...").create()

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
        from ui.live.live_state import SessionStatus

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
