"""
QA Collection Panel Component
Panel kolekcji par Q+A z animacją 3D "rzucania kart na stół".

Gamifikacja: lekarz zbiera pary pytanie+odpowiedź podczas wywiadu.
"""

from nicegui import ui
from typing import Optional, TYPE_CHECKING

from app_ui.live.components.card_throw_styles import inject_card_throw_styles

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

    # Rotation classes for visual variety
    ROTATION_CLASSES = [
        'qa-card-rotate-1',
        'qa-card-rotate-2',
        'qa-card-rotate-3',
        'qa-card-rotate-4',
        'qa-card-rotate-5',
    ]

    def __init__(self, state: 'LiveState'):
        self.state = state
        self.container: Optional[ui.element] = None
        self.cards_container: Optional[ui.element] = None
        self.progress_badge: Optional[ui.badge] = None
        self._client = None
        self._latest_card_id: Optional[str] = None

    def create(self) -> ui.element:
        """Tworzy panel kolekcji Q+A."""
        inject_card_throw_styles()

        self.container = ui.element('div').classes(
            'w-full qa-collection-container'
        )

        with self.container:
            # Main card container with gradient "table"
            with ui.card().classes(
                'w-full qa-collection-table p-4'
            ):
                # Header row
                with ui.row().classes('w-full justify-between items-center mb-3'):
                    # Title
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('collections_bookmark', size='sm').classes('text-blue-600')
                        ui.label('Zebrane Q+A').classes(
                            'text-sm font-semibold text-slate-700'
                        )

                    # Progress badge
                    current, target = self.state.qa_progress
                    self.progress_badge = ui.badge(
                        f'{current}/{target}',
                        color='blue'
                    ).classes('qa-progress-badge text-xs px-2 py-1')

                # Cards container (the "table")
                self.cards_container = ui.element('div').classes(
                    'w-full min-h-[80px] flex flex-wrap gap-3 items-start'
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
                    self._render_qa_card(pair, idx)

    def _render_empty_state(self):
        """Renderuje placeholder gdy brak par."""
        with ui.element('div').classes(
            'qa-empty-slot w-full h-[60px] '
            'flex items-center justify-center gap-2'
        ):
            ui.icon('psychology', size='sm').classes('text-slate-400')
            ui.label('Kliknij pytanie i poczekaj na odpowiedź pacjenta').classes(
                'text-sm text-slate-400'
            )

    def _render_qa_card(self, pair: 'QAPair', index: int):
        """Renderuje pojedynczą kartę Q+A."""
        # Rotation for visual variety
        rotation_class = self.ROTATION_CLASSES[index % len(self.ROTATION_CLASSES)]
        stagger_class = f'qa-card-stagger-{(index % 5) + 1}'

        # Check if this is the newest card (for throw animation)
        is_newest = pair.id == self._latest_card_id
        throw_class = 'throwing' if is_newest else ''

        with ui.card().classes(
            f'qa-card {rotation_class} {stagger_class} {throw_class} '
            'w-[140px] p-3 bg-white border border-slate-200 '
            'rounded-xl shadow-md cursor-pointer relative'
        ):
            # Tooltip on hover
            with ui.element('div').classes('qa-card-tooltip'):
                ui.label(f'Q: {pair.question[:50]}...' if len(pair.question) > 50 else f'Q: {pair.question}')

            # Card content
            with ui.column().classes('gap-1'):
                # Question (truncated)
                ui.label(self._truncate(pair.question, 30)).classes(
                    'text-xs text-slate-600 font-medium leading-tight'
                )

                # Divider
                ui.element('div').classes('w-full h-px bg-slate-200 my-1')

                # Answer (truncated)
                ui.label(self._truncate(pair.answer, 40)).classes(
                    'text-xs text-slate-500 leading-tight'
                )

            # Number badge
            with ui.element('div').classes(
                'absolute -top-2 -right-2 w-6 h-6 '
                'bg-blue-500 text-white text-xs font-bold '
                'rounded-full flex items-center justify-center shadow-md'
            ):
                ui.label(str(index + 1))

    def _truncate(self, text: str, max_len: int) -> str:
        """Skraca tekst do max_len znaków."""
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + '...'

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
                    self._render_cards()
            except Exception as e:
                print(f"[QA_PANEL] Refresh error: {e}", flush=True)
