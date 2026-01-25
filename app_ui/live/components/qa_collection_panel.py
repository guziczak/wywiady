"""
QA Collection Panel Component
Panel kolekcji par Q+A z animacją 3D "rzucania kart na stół".

Gamifikacja: lekarz zbiera pary pytanie+odpowiedź podczas wywiadu.
Funkcje:
- Stół 3D z perspektywą
- Karty par Q+A z animacją rzutu
- Modal edycji par
- Przycisk Undo
"""

from nicegui import ui
from typing import Optional, TYPE_CHECKING

from app_ui.live.components.card_throw_styles import inject_card_throw_styles
from app_ui.live.components.qa_pair_styles import inject_qa_pair_styles

if TYPE_CHECKING:
    from app_ui.live.live_state import LiveState
    from app_ui.live.state.qa_collector import QAPair


class QACollectionPanel:
    """
    Panel kolekcji par Q+A.
    - Progress badge (3/10 par)
    - "Stół" na karty (gradient background)
    - Karty Q+A z losowym obrotem
    - Animacja 3D przy nowej parze
    """

    # Rotation classes for visual variety (6 variants)
    ROTATION_CLASSES = [
        'qa-pair-rotate-1',
        'qa-pair-rotate-2',
        'qa-pair-rotate-3',
        'qa-pair-rotate-4',
        'qa-pair-rotate-5',
        'qa-pair-rotate-6',
    ]

    def __init__(self, state: 'LiveState'):
        self.state = state
        self.container: Optional[ui.element] = None
        self.cards_container: Optional[ui.element] = None
        self.progress_badge: Optional[ui.badge] = None
        self.undo_btn: Optional[ui.button] = None
        self._client = None
        self._latest_card_id: Optional[str] = None
        self._edit_dialog: Optional[ui.dialog] = None

    def create(self) -> ui.element:
        """Tworzy panel kolekcji Q+A."""
        inject_card_throw_styles()
        inject_qa_pair_styles()

        self.container = ui.element('div').classes(
            'w-full qa-collection-container'
        )

        with self.container:
            # Header row (above the table)
            with ui.row().classes('w-full justify-between items-center mb-2 px-1'):
                # Title
                with ui.row().classes('items-center gap-2'):
                    ui.icon('collections_bookmark', size='sm').classes('text-emerald-600')
                    ui.label('Zebrane Q+A').classes(
                        'text-sm font-semibold text-slate-700'
                    )

                # Controls: Undo + Progress
                with ui.row().classes('items-center gap-2'):
                    # Undo button
                    self.undo_btn = ui.button(
                        icon='undo',
                        on_click=self._undo_last
                    ).props('flat dense round color=gray').classes(
                        'qa-undo-btn text-xs'
                    ).tooltip('Cofnij ostatnią parę')
                    self._update_undo_visibility()

                    # Progress badge
                    current, target = self.state.qa_progress
                    self.progress_badge = ui.badge(
                        f'{current}/{target}',
                        color='green'
                    ).classes('qa-progress-badge text-xs px-2 py-1')

            # 3D Table container
            with ui.element('div').classes(
                'qa-table-3d w-full min-h-[150px] p-4 rounded-xl'
            ):
                # Cards container
                self.cards_container = ui.element('div').classes(
                    'w-full flex flex-wrap gap-4 items-start justify-start'
                )

                with self.cards_container:
                    self._render_cards()

        # Capture client context
        self._client = ui.context.client

        # Subscribe to Q+A pair creation (nowa architektura używa qa_collector)
        self.state.qa_collector.on_pair_added(self._on_qa_pair_created)

        return self.container

    def _render_cards(self):
        """Renderuje karty Q+A lub empty state."""
        self.cards_container.clear()

        with self.cards_container:
            if not self.state.qa_pairs:
                # Empty state
                self._render_empty_state()
            else:
                # Render collected pairs
                for idx, pair in enumerate(self.state.qa_pairs):
                    self._render_qa_pair_card(pair, idx)

    def _render_empty_state(self):
        """Renderuje placeholder gdy brak par."""
        with ui.element('div').classes(
            'qa-table-empty w-full h-[100px] '
            'flex items-center justify-center gap-3 rounded-lg'
        ):
            ui.icon('psychology', size='md').classes('text-emerald-300')
            with ui.column().classes('items-center gap-1'):
                ui.label('Brak zebranych par Q+A').classes(
                    'text-sm text-emerald-600 font-medium'
                )
                ui.label('Kliknij pytanie i wybierz odpowiedź lub poczekaj na pacjenta').classes(
                    'text-xs text-slate-400'
                )

    def _render_qa_pair_card(self, pair: 'QAPair', index: int):
        """Renderuje pojedynczą kartę pary Q+A z sekcjami."""
        # Rotation for visual variety
        rotation_class = self.ROTATION_CLASSES[index % len(self.ROTATION_CLASSES)]
        stagger_class = f'qa-pair-stagger-{(index % 6) + 1}'

        # Check if this is the newest card (for throw animation)
        is_newest = pair.id == self._latest_card_id
        throw_class = 'throwing-pair' if is_newest else ''

        card = ui.card().classes(
            f'qa-pair-card {rotation_class} {stagger_class} {throw_class} '
            'w-[180px] p-3 bg-white border border-slate-200 '
            'rounded-xl shadow-md cursor-pointer relative'
        )

        # Click handler - otwórz modal edycji
        card.on('click', lambda p=pair: self._open_edit_modal(p))

        with card:
            # Card content
            with ui.column().classes('gap-2 w-full'):
                # Question section
                with ui.element('div').classes('qa-pair-section-q w-full'):
                    with ui.row().classes('items-center gap-1 mb-1'):
                        ui.icon('help_outline', size='xs').classes('text-blue-500')
                        ui.label('Pytanie').classes('text-[10px] text-blue-600 uppercase tracking-wide font-medium')
                    ui.label(self._truncate(pair.question, 35)).classes(
                        'text-xs text-slate-700 leading-tight'
                    )

                # Answer section
                with ui.element('div').classes('qa-pair-section-a w-full'):
                    with ui.row().classes('items-center gap-1 mb-1'):
                        ui.icon('chat_bubble_outline', size='xs').classes('text-emerald-500')
                        ui.label('Odpowiedź').classes('text-[10px] text-emerald-600 uppercase tracking-wide font-medium')
                    ui.label(self._truncate(pair.answer, 45)).classes(
                        'text-xs text-slate-600 leading-tight'
                    )

            # Number badge
            with ui.element('div').classes(
                'absolute -top-2 -right-2 w-6 h-6 '
                'bg-emerald-500 text-white text-xs font-bold '
                'rounded-full flex items-center justify-center shadow-md'
            ):
                ui.label(str(index + 1))

            # Edit hint (on hover)
            with ui.element('div').classes(
                'absolute bottom-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity'
            ):
                ui.icon('edit', size='xs').classes('text-slate-400')

    def _truncate(self, text: str, max_len: int) -> str:
        """Skraca tekst do max_len znaków."""
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + '...'

    def _open_edit_modal(self, pair: 'QAPair'):
        """Otwiera modal edycji pary Q+A."""
        if self._edit_dialog:
            try:
                self._edit_dialog.close()
            except Exception:
                pass

        with ui.dialog() as self._edit_dialog, ui.card().classes('w-[400px] p-4'):
            # Header
            with ui.row().classes('w-full justify-between items-center mb-4'):
                ui.label('Edytuj parę Q+A').classes('text-lg font-semibold text-slate-800')
                ui.button(icon='close', on_click=self._edit_dialog.close).props('flat dense round')

            # Question (read-only)
            with ui.column().classes('w-full gap-1 mb-3'):
                ui.label('Pytanie').classes('text-xs text-slate-500 uppercase tracking-wide')
                ui.label(pair.question).classes(
                    'text-sm text-slate-700 p-2 bg-slate-50 rounded border border-slate-200'
                )

            # Answer (editable)
            with ui.column().classes('w-full gap-1 mb-4'):
                ui.label('Odpowiedź').classes('text-xs text-slate-500 uppercase tracking-wide')
                answer_input = ui.textarea(value=pair.answer).classes(
                    'w-full'
                ).props('outlined rows=3')

            # Buttons
            with ui.row().classes('w-full justify-between'):
                # Delete button
                ui.button(
                    'Usuń',
                    icon='delete',
                    on_click=lambda: self._delete_pair(pair.id)
                ).props('flat color=red')

                # Save button
                ui.button(
                    'Zapisz',
                    icon='save',
                    on_click=lambda: self._save_pair_edit(pair.id, answer_input.value)
                ).props('color=primary')

        self._edit_dialog.open()

    def _save_pair_edit(self, pair_id: str, new_answer: str):
        """Zapisuje edycję odpowiedzi."""
        if self.state.qa_collector.update_answer(pair_id, new_answer):
            if self._edit_dialog:
                self._edit_dialog.close()
            self.refresh()
            if self._client:
                try:
                    with self._client:
                        ui.notify('Zapisano zmiany', type='positive')
                except Exception:
                    pass

    def _delete_pair(self, pair_id: str):
        """Usuwa parę Q+A."""
        if self.state.qa_collector.remove(pair_id):
            if self._edit_dialog:
                self._edit_dialog.close()
            self.refresh()
            if self._client:
                try:
                    with self._client:
                        ui.notify('Usunięto parę Q+A', type='info')
                except Exception:
                    pass

    def _undo_last(self):
        """Cofa ostatnią parę (undo)."""
        removed = self.state.qa_collector.undo_last()
        if removed:
            self.refresh()
            if self._client:
                try:
                    with self._client:
                        ui.notify(f'Cofnięto parę: {self._truncate(removed.question, 30)}', type='info')
                except Exception:
                    pass

    def _update_undo_visibility(self):
        """Aktualizuje widoczność przycisku Undo."""
        if self.undo_btn:
            if self.state.qa_pairs:
                self.undo_btn.classes(remove='hidden')
                self.undo_btn.props(remove='disabled')
            else:
                self.undo_btn.classes(add='hidden')

    def _on_qa_pair_created(self, pair: 'QAPair'):
        """Callback gdy utworzono nową parę Q+A."""
        print(f"[QA_PANEL] New pair created: {pair.id}", flush=True)

        self._latest_card_id = pair.id

        if self._client:
            try:
                with self._client:
                    # Update progress badge with pulse animation
                    current, target = self.state.qa_progress
                    if self.progress_badge:
                        self.progress_badge.text = f'{current}/{target}'
                        self.progress_badge.classes(add='pulse')

                        # Remove pulse class after animation
                        ui.timer(0.7, lambda: self.progress_badge.classes(remove='pulse'), once=True)

                    # Update undo visibility
                    self._update_undo_visibility()

                    # Re-render cards with throw animation
                    self._render_cards()

                    # Show toast notification
                    ui.notify(
                        f'Zebrano parę Q+A! ({current}/{target})',
                        type='positive',
                        position='top-right',
                        icon='check_circle'
                    )

            except Exception as e:
                print(f"[QA_PANEL] Update error: {e}", flush=True)

    def refresh(self):
        """Wymusza odświeżenie panelu."""
        if self._client:
            try:
                with self._client:
                    current, target = self.state.qa_progress
                    if self.progress_badge:
                        self.progress_badge.text = f'{current}/{target}'
                    self._update_undo_visibility()
                    self._render_cards()
            except Exception as e:
                print(f"[QA_PANEL] Refresh error: {e}", flush=True)
