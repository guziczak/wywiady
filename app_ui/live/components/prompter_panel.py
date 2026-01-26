"""

Prompter Panel Component

Panel suflera z kartami sugestii i kontrolkami.



Obsługuje 3 tryby:

- SUGGESTIONS: normalne karty sugestii AI

- CONFIRMING: potwierdzenie zakończenia wywiadu

- SUMMARY: podsumowanie po zakończeniu

"""



from nicegui import ui

from typing import Callable, Optional, TYPE_CHECKING



from app_ui.live.components.suggestion_card import (

    SuggestionCard,

    PlaceholderCard,

    EmptyStateCard

)

from app_ui.live.components.summary_components import (
    ConfirmationBar,
    SummaryStats,
    SummaryActions
)
from app_ui.live.components.animation_styles import inject_animation_styles
from app_ui.live.ui_labels import (
    STATUS_READY,
    STATUS_RECORDING,
    MODE_LABELS,
    MODE_COLORS,
)


if TYPE_CHECKING:

    from app_ui.live.live_state import LiveState, SessionStatus, PrompterMode





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
        on_finish: Optional[Callable[[bool], None]] = None,  # callback(analyze_speakers)
        on_continue: Optional[Callable[[], None]] = None,    # nowy callback
        on_new_pool: Optional[Callable[[], None]] = None,
        on_cards_mode_change: Optional[Callable[[str], None]] = None,
        on_card_click: Optional[Callable[[object], None]] = None,
        show_record_button: bool = True
    ):
        self.state = state
        self.app_instance = app_instance
        self.on_toggle_session = on_toggle_session
        self.on_finish = on_finish
        self.on_continue = on_continue
        self.on_new_pool = on_new_pool
        self.on_cards_mode_change = on_cards_mode_change
        self.on_card_click = on_card_click
        self.show_record_button = show_record_button


        # UI refs

        self.container = None

        self.cards_container = None

        self.header_container = None
        self.action_btn = None
        self.status_badge = None
        self.mode_badge = None
        self.checklist_badge = None
        self.next_pool_btn = None
        self.cards_mode_radio = None
        self._cards_mode_sync = False
        self._is_loading = False
        self._client = None  # NiceGUI client context

        self._needs_refresh = False

        self._refresh_timer = None



    def create(self) -> ui.card:

        """Tworzy panel suflera."""

        print(f"[PROMPTER] create() called, ui.context.client = {ui.context.client}", flush=True)



        # Wstrzyknij style animacji

        inject_animation_styles()



        self.container = ui.card().classes(

            'w-full '

            'bg-slate-50 '

            'border-t-4 border-blue-500 '

            'rounded-none rounded-b-xl '

            'shadow-lg '

            'p-3 sm:p-4 '

            'h-full flex flex-col min-h-0'

        )



        with self.container:

            # Header z kontrolkami (ukrywany w niektórych trybach)

            self.header_container = ui.element('div').classes('w-full')

            with self.header_container:

                self._create_header()



            # Kontener na treść (karty/confirmation/summary)

            self._create_content_container()



        # Capture client context for background updates

        self._client = ui.context.client

        print(f"[PROMPTER] _client set to: {self._client}", flush=True)



        # UI-safe refresh timer (flushes background updates on UI thread)

        self._refresh_timer = ui.timer(0.3, self._flush_refresh)



        # Subscribe to state changes

        self.state.on_suggestions_change(self._on_suggestions_change)

        self.state.on_status_change(self._on_status_change)

        self.state.on_diarization_change(self._on_diarization_change)

        self.state.on_mode_change(self._on_mode_change)
        self.state.on_conversation_mode_change(self._on_conversation_mode_change)
        self.state.on_cards_mode_change(self._on_cards_mode_change)
        self.state.on_return_hint_change(self._on_return_hint_change)



        return self.container



    # === EVENT HANDLERS ===



    def _handle_finish_click(self):

        """Kliknięcie przycisku Zakończ (w headerze)."""

        # Przełącz na tryb potwierdzenia

        self.state.show_confirmation()



    def _handle_confirm_finish(self, analyze_speakers: bool):

        """Potwierdzenie zakończenia wywiadu."""

        # Wywołaj callback rodzica (logika biznesowa zatrzymania)

        if self.on_finish:

            self.on_finish(analyze_speakers)

        

        # Przełącz na podsumowanie

        self.state.show_summary()



    def _handle_cancel_finish(self):

        """Anulowanie zakończenia."""

        self.state.cancel_confirmation()



    def _handle_continue(self):

        """Kliknięcie Kontynuuj w podsumowaniu."""

        if self.on_continue:

            self.on_continue()

    def _handle_new_pool(self):
        """Klikniecie Nowa pula (tryb poradniczy)."""
        if self.on_new_pool:
            self.on_new_pool()

    def _handle_cards_mode_change(self):
        """Zmien tryb kart (pytania/poradniczy)."""
        if self._cards_mode_sync:
            return
        if not self.cards_mode_radio:
            return
        value = self.cards_mode_radio.value
        mode = "questions" if value == "Pytania" else "decision"
        if self.on_cards_mode_change:
            self.on_cards_mode_change(mode)

    def _handle_return_to_questions(self):
        """Powrot do kart pytan z podpowiedzi."""
        if self.on_cards_mode_change:
            self.on_cards_mode_change("questions")



    def _handle_toggle_diarization(self):

        """Przełączenie diaryzacji."""

        if self.state.diarization:

            self.state.toggle_diarization()



    def _handle_swap_roles(self):

        """Zamiana ról mówców."""

        self.state.swap_speaker_roles()



    def _on_mode_change(self):
        """Callback gdy zmieni się tryb panelu (SUGGESTIONS/CONFIRMING/SUMMARY)."""
        if self._client:
            with self._client:
                self._render_content()
                # Jeśli tryb SUMMARY lub CONFIRMING - ukryj header z przyciskiem Zakończ

                if self.header_container:

                    from app_ui.live.live_state import PrompterMode

                    should_show = self.state.prompter_mode == PrompterMode.SUGGESTIONS
                    self.header_container.set_visibility(should_show)

    def _on_conversation_mode_change(self):
        """Callback gdy zmieni się tryb rozmowy."""
        if self._client:
            with self._client:
                self._update_mode_badges()

    def _on_cards_mode_change(self):
        """Callback gdy zmieni się tryb kart."""
        if self._client:
            with self._client:
                self._update_mode_badges()

    def _on_return_hint_change(self):
        """Callback gdy zmieni się hint powrotu do pytań."""
        if self._client:
            with self._client:
                self._render_content()

    def _update_mode_badges(self):
        """Aktualizuje badge trybu rozmowy i checklisty."""
        from app_ui.live.live_state import SessionStatus
        from app_ui.live.live_state import CardsMode
        mode_key = getattr(self.state.conversation_mode, 'value', 'general')
        label = MODE_LABELS.get(mode_key, MODE_LABELS.get('general', 'Tryb: Ogolny'))
        color = MODE_COLORS.get(mode_key, 'gray')

        if self.mode_badge:
            self.mode_badge.text = label
            self.mode_badge.props(f'color={color}')

        if self.checklist_badge:
            done, total = self.state.checklist_progress
            if total > 0:
                self.checklist_badge.text = f"Check {done}/{total}"
                self.checklist_badge.set_visibility(True)
            else:
                self.checklist_badge.set_visibility(False)

        if self.next_pool_btn:
            show_next = (mode_key == "decision" and self.state.status == SessionStatus.RECORDING)
            self.next_pool_btn.set_visibility(show_next)
            if show_next:
                done, total = self.state.checklist_progress
                if total > 0 and done >= total:
                    self.next_pool_btn.props('color=green')
                else:
                    self.next_pool_btn.props('color=primary')

        if self.cards_mode_radio:
            show_radio = self.state.status == SessionStatus.RECORDING
            self.cards_mode_radio.set_visibility(show_radio)
            if show_radio:
                cards_mode = getattr(self.state.cards_mode, 'value', 'auto')
                if cards_mode == CardsMode.QUESTIONS.value:
                    value = "Pytania"
                elif cards_mode == CardsMode.DECISION.value:
                    value = "Poradniczy"
                else:
                    value = "Poradniczy" if mode_key == "decision" else "Pytania"
                if self.cards_mode_radio.value != value:
                    self._cards_mode_sync = True
                    self.cards_mode_radio.value = value
                    self._cards_mode_sync = False


    # === UI CREATION ===



    def _create_header(self):

        """Tworzy nagłówek z kontrolkami."""

        with ui.row().classes(

            'w-full justify-between items-center mb-4 flex-wrap gap-2'

        ):

            # Tytuł

            with ui.row().classes('items-center gap-2'):

                ui.icon('psychology', size='sm').classes('text-blue-600')

                ui.label('AI Asystent').classes(

                    'text-base font-semibold text-gray-700'

                )



            # Kontrolki

            with ui.row().classes('items-center gap-3'):

                # Status badge

                self.status_badge = ui.badge(STATUS_READY, color='gray').classes(
                    'text-[11px]'
                ).props('aria-live="polite"')

                # Mode badge
                mode_key = getattr(self.state.conversation_mode, 'value', 'general')
                mode_label = MODE_LABELS.get(mode_key, MODE_LABELS.get('general', 'Tryb: Ogolny'))
                mode_color = MODE_COLORS.get(mode_key, 'gray')
                self.mode_badge = ui.badge(mode_label, color=mode_color).classes('text-[10px]')

                # Przelacznik kart (Pytania / Poradniczy)
                self.cards_mode_radio = ui.radio(
                    ['Pytania', 'Poradniczy'],
                    value='Poradniczy' if mode_key == 'decision' else 'Pytania'
                ).props('inline dense').classes('text-[10px]').on('change', lambda: self._handle_cards_mode_change())
                self.cards_mode_radio.set_visibility(False)

                # Checklist progress (only in decision mode with check items)
                self.checklist_badge = ui.badge("Check 0/0", color='amber').classes('text-[10px]')
                self.checklist_badge.set_visibility(False)

                # Nowa pula (only in decision mode)
                self.next_pool_btn = ui.button(
                    'Nowa pula',
                    icon='autorenew',
                    on_click=self._handle_new_pool
                ).props('outline size=sm')
                self.next_pool_btn.set_visibility(False)

                # Przycisk START/STOP (opcjonalny, gdy jest dock)
                if self.show_record_button:
                    self.action_btn = ui.button(
                        'START',
                        icon='mic',
                        color='green',
                        on_click=self._handle_toggle
                    ).props('size=sm').classes('min-w-[88px]')

                # Przycisk Zakończ
                self.finish_btn = ui.button(
                    'Zakończ',
                    icon='check_circle',
                    color='blue',
                    on_click=self._handle_finish_click

                ).props('outline size=sm')



    def _create_content_container(self):

        """Tworzy kontener na treść (karty/confirmation/summary)."""

        self.cards_container = ui.element('div').classes(

            'w-full min-h-[140px] transition-all-smooth '

            'flex-1 min-h-0 overflow-y-auto pr-1'

        )



        with self.cards_container:

            self._render_content()



    def _render_content(self):

        """Renderuje treść na podstawie trybu."""

        from app_ui.live.live_state import PrompterMode



        # Wyczyść kontener

        self.cards_container.clear()



        with self.cards_container:

            mode = self.state.prompter_mode



            if mode == PrompterMode.CONFIRMING:

                self._render_confirmation()

            elif mode == PrompterMode.SUMMARY:

                self._render_summary()

            else:

                self._render_suggestions()



    def _render_confirmation(self):

        """Renderuje bar potwierdzenia zakończenia."""

        ConfirmationBar(

            state=self.state,

            on_confirm=self._handle_confirm_finish,

            on_cancel=self._handle_cancel_finish

        ).create()



    def _render_summary(self):

        """Renderuje podsumowanie po zakończeniu."""

        with ui.column().classes('w-full gap-4 animate-fade-in'):

            # Statystyki

            if self.state.interview_stats:

                SummaryStats(self.state.interview_stats).create()



            # Akcje

            SummaryActions(

                state=self.state,

                on_continue=self._handle_continue,

                on_toggle_diarization=self._handle_toggle_diarization,

                on_swap_roles=self._handle_swap_roles

            ).create()



    def _render_suggestions(self):

        """Renderuje karty sugestii (domyślny tryb)."""

        from app_ui.live.live_state import SessionStatus

        with ui.column().classes('w-full gap-4'):
            self._update_mode_badges()

            # Hint: powrot do pytan
            if getattr(self.state, "return_to_questions_hint", False):
                with ui.element('div').classes(
                    'w-full flex items-center justify-between gap-3 p-3 rounded-xl '
                    'bg-amber-50 border border-amber-200 text-amber-800'
                ):
                    ui.label('Wykryto pytanie w rozmowie. Wrocic do kart pytań?').classes('text-sm')
                    ui.button(
                        'Wroc do pytan',
                        icon='help',
                        on_click=lambda: self._handle_return_to_questions()
                    ).props('outline size=sm')

            # === KARTY SUGESTII ===

            if self.state.status == SessionStatus.IDLE:

                with ui.element('div').classes('w-full grid prompter-grid gap-3'):

                    for idx in range(3):

                        EmptyStateCard("Naciśnij START", tilt_index=idx).create()

            else:

                suggestions = self.state.suggestions



                if not suggestions and not self._is_loading:

                    with ui.element('div').classes('w-full grid prompter-grid gap-3'):

                        PlaceholderCard("Analizuję rozmowę...", tilt_index=0).create()

                        PlaceholderCard("Szukam pytań...", tilt_index=1).create()

                        PlaceholderCard("Czekam na kontekst...", tilt_index=2).create()

                elif self._is_loading and not suggestions:

                    with ui.element('div').classes('w-full grid prompter-grid gap-3'):

                        for idx in range(3):

                            PlaceholderCard("Generuję...", tilt_index=idx).create()

                elif any(s.question == "Brak konfiguracji AI" for s in suggestions):

                    self._render_config_error_card()

                else:

                    with ui.element('div').classes('w-full grid prompter-grid gap-3'):

                        for idx in range(3):

                            if idx < len(suggestions):

                                suggestion = suggestions[idx]

                                SuggestionCard(
                                    question=suggestion.question,
                                    on_click=self._handle_card_click,
                                    used=suggestion.used,
                                    variant="primary" if idx == 0 else "secondary",
                                    selected=(suggestion.kind == "question" and suggestion.question == self.state.selected_question),
                                    tilt_index=idx,
                                    card_kind=suggestion.kind,
                                    tag=suggestion.tag,
                                    payload=suggestion,
                                ).create()

                            else:

                                PlaceholderCard("Szukam więcej...", tilt_index=idx).create()



            # === PODPOWIEDZI ODPOWIEDZI PACJENTA ===

            self._render_answer_suggestions()



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



    def _render_answer_suggestions(self):

        """

        DEPRECATED: Odpowiedzi pacjenta przeniesione do ActiveQuestionPanel.



        Ten panel teraz pokazuje tylko subtelny hint.

        Cała logika odpowiedzi jest w osobnym komponencie który:

        - NIE znika przy regeneracji sugestii

        - Ma timer countdown

        - Ma przycisk pin

        """

        # Nie renderujemy nic - odpowiedzi są w ActiveQuestionPanel

        # Zachowujemy metodę dla kompatybilności wstecznej

        pass



    # USUNIĘTO: _handle_answer_click i _clear_answer_context

    # Przeniesione do ActiveQuestionPanel



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

        # Sugestie przychodza z AI controller ktory dziala async

        self._needs_refresh = True



    def _on_diarization_change(self):

        """Callback gdy zmieni się diaryzacja."""

        if self._client is None:

            return

        try:

            with self._client:

                self._update_diarization_ui()

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
                if self.action_btn:
                    self.action_btn.props('color=red icon=stop')
                    self.action_btn.text = 'STOP'
                self.status_badge.text = STATUS_RECORDING
                self.status_badge.props('color=red')
            else:
                if self.action_btn:
                    self.action_btn.props('color=green icon=mic')
                    self.action_btn.text = 'START'
                self.status_badge.text = STATUS_READY
                self.status_badge.props('color=gray')


            self._render_content()

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



    def _handle_card_click(self, suggestion):

        """Obsługuje kliknięcie w kartę."""

        if self.on_card_click:

            self.on_card_click(suggestion)



    def set_loading(self, loading: bool):

        """Ustawia stan ładowania (wywoływany synchronicznie z UI)."""

        self._is_loading = loading

        try:

            self._render_content()

        except Exception:

            pass



    def refresh(self):

        """Wymusza przerysowanie UI w bezpiecznym kontekście klienta."""

        self._needs_refresh = True



    def _flush_refresh(self):
        """Wykonuje odswiezenie w bezpiecznym kontekscie UI."""
        if not self._needs_refresh:
            return
        self._needs_refresh = False
        try:

            self._render_content()

        except Exception as e:
            print(f"[PROMPTER] Refresh error: {e}", flush=True)

    def destroy(self):
        """Sprząta timery i zasoby UI."""
        if self._refresh_timer:
            try:
                self._refresh_timer.cancel()
            except Exception:
                pass
            self._refresh_timer = None







