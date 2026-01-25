"""
QA Collection Panel Component (3D Version)
Panel kolekcji par Q+A z prawdziwą animacją 3D (Three.js + CSS3DRenderer).

Gamifikacja: lekarz zbiera pary pytanie+odpowiedź podczas wywiadu.
Funkcje:
- Scena 3D z "biurkiem"
- Karty renderowane jako elementy DOM w przestrzeni 3D
- Fizyka rzutu i układania na stosie
- Pełna interaktywność (kliknięcie otwiera modal)
"""

from nicegui import ui
from typing import Optional, TYPE_CHECKING
import asyncio

from app_ui.live.components.three_scene import ThreeStage

if TYPE_CHECKING:
    from app_ui.live.live_state import LiveState
    from app_ui.live.state.qa_collector import QAPair


class QACollectionPanel:
    """
    Panel kolekcji par Q+A (Wersja 3D).
    """

    def __init__(self, state: 'LiveState'):
        self.state = state
        self.container: Optional[ui.element] = None
        self.three_stage: Optional[ThreeStage] = None
        
        # Kontener na elementy, które Three.js przejmie
        # Musi być w DOM, ale niewidoczny (Three.js i tak nada im position:absolute)
        self.staging_container: Optional[ui.element] = None
        
        self.progress_badge: Optional[ui.badge] = None
        self.undo_btn: Optional[ui.button] = None
        self._client = None
        self._edit_dialog: Optional[ui.dialog] = None
        
        # Śledzimy dodane ID, by nie dodawać duplikatów przy odświeżaniu
        self._added_card_ids = set()
        # Mapa: pair_id -> element (ui.card)
        self._pair_element_map = {}

    def create(self) -> ui.element:
        """Tworzy panel kolekcji Q+A."""
        self.container = ui.element('div').classes(
            'w-full qa-collection-container flex flex-col gap-2'
        )

        with self.container:
            # Header row
            with ui.row().classes('w-full justify-between items-center px-1'):
                # Title
                with ui.row().classes('items-center gap-2'):
                    ui.icon('collections_bookmark', size='sm').classes('text-emerald-600')
                    ui.label('Zebrane Q+A (3D Desk)').classes(
                        'text-sm font-semibold text-slate-700'
                    )

                # Controls
                with ui.row().classes('items-center gap-2'):
                    self.undo_btn = ui.button(
                        icon='undo',
                        on_click=self._undo_last
                    ).props('flat dense round color=gray').classes(
                        'qa-undo-btn text-xs'
                    ).tooltip('Cofnij ostatnią parę')
                    self._update_undo_visibility()

                    current, target = self.state.qa_progress
                    self.progress_badge = ui.badge(
                        f'{current}/{target}',
                        color='green'
                    ).classes('qa-progress-badge text-xs px-2 py-1')

            # 3D Stage Container
            # Use relative positioning and define height
            with ui.element('div').classes(
                'qa-stage-wrapper w-full h-[400px] relative rounded-xl overflow-hidden bg-slate-50 border border-slate-200 shadow-inner'
            ):
                # Background decoration (gradient floor)
                ui.element('div').classes(
                    'absolute inset-0 bg-gradient-to-b from-slate-100 to-slate-200 opacity-50 pointer-events-none'
                )
                
                # The Three.js Scene
                self.three_stage = ThreeStage()

            # Staging Area (Hidden from view, but in DOM)
            # We hide it via CSS, but ensure content is rendered
            self.staging_container = ui.element('div').classes('hidden-staging fixed top-0 left-0 opacity-0 pointer-events-none')

        # Capture client context
        self._client = ui.context.client

        # Subscribe to events
        self.state.qa_collector.on_pair_added(self._on_qa_pair_created)
        
        # Initial population (delayed slightly to ensure Three.js init)
        ui.timer(0.5, self._populate_existing_cards, once=True)

        return self.container

    async def _populate_existing_cards(self):
        """Dodaje istniejące karty do sceny po starcie."""
        if not self.state.qa_pairs:
            return
            
        for pair in self.state.qa_pairs:
            if pair.id not in self._added_card_ids:
                await self._create_and_throw_card(pair)

    async def _create_and_throw_card(self, pair: 'QAPair'):
        """Tworzy element karty i wrzuca go do sceny 3D."""
        if not self.staging_container:
            return

        self._added_card_ids.add(pair.id)

        # Create the card element in the staging area
        with self.staging_container:
            card_el = self._build_card_element(pair)
        
        self._pair_element_map[pair.id] = card_el

        # Tell Three.js to take it
        # We need to wait a tick for NiceGUI/Vue to mount it
        await asyncio.sleep(0.05)
        if self.three_stage:
            await self.three_stage.add_card(card_el)

    def _build_card_element(self, pair: 'QAPair') -> ui.card:
        """Tworzy wizualną reprezentację karty (NiceGUI Element)."""
        # Styl karty identyczny jak wcześniej, ale bez klas animacji CSS (bo Three.js to robi)
        card = ui.card().classes(
            'w-[220px] p-3 bg-white border border-slate-200 '
            'rounded-xl shadow-lg cursor-pointer select-none '
            'hover:shadow-xl hover:border-blue-300 transition-colors'
        )
        # Ensure DOM ID matches what ThreeStage expects
        card.props(f'id=c{card.id}')
        
        # Ważne: ID elementu musi być unikalne i znane, NiceGUI generuje je automatycznie.
        # Handler kliknięcia
        card.on('click', lambda: self._open_edit_modal(pair))

        with card:
            # Card content
            with ui.column().classes('gap-2 w-full'):
                # Question section
                with ui.element('div').classes('w-full border-b border-slate-100 pb-2'):
                    with ui.row().classes('items-center gap-1 mb-1'):
                        ui.icon('help_outline', size='xs').classes('text-blue-500')
                        ui.label('Pytanie').classes('text-[10px] text-blue-600 uppercase tracking-wide font-medium')
                    ui.label(self._truncate(pair.question, 40)).classes(
                        'text-xs text-slate-700 leading-tight font-medium'
                    )

                # Answer section
                with ui.element('div').classes('w-full pt-1'):
                    with ui.row().classes('items-center gap-1 mb-1'):
                        ui.icon('chat_bubble_outline', size='xs').classes('text-emerald-500')
                        ui.label('Odpowiedź').classes('text-[10px] text-emerald-600 uppercase tracking-wide font-medium')
                    ui.label(self._truncate(pair.answer, 50)).classes(
                        'text-xs text-slate-600 leading-tight'
                    )
            
            # Decoration (Corner Fold or ID)
            with ui.element('div').classes(
                'absolute top-2 right-2 w-2 h-2 rounded-full bg-emerald-400'
            ):
                pass

        return card

    def _on_qa_pair_created(self, pair: 'QAPair'):
        """Callback: Nowa para = nowa karta 3D."""
        if self._client:
            # Używamy background tasks dla async w sync callbacku
            # Fix: Client nie ma atrybutu loop, używamy get_running_loop() lub create_task
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._handle_new_pair_async(pair))
            except RuntimeError:
                # Fallback jeśli nie ma aktywnego loopa (np. inny wątek)
                asyncio.run_coroutine_threadsafe(
                    self._handle_new_pair_async(pair), 
                    asyncio.get_event_loop()
                )

    async def _handle_new_pair_async(self, pair: 'QAPair'):
        """Async handler dla nowej karty."""
        if not self._client:
            return

        with self._client:
            # Update UI text
            current, target = self.state.qa_progress
            if self.progress_badge:
                self.progress_badge.text = f'{current}/{target}'
                self.progress_badge.classes(add='pulse')
                ui.timer(0.7, lambda: self.progress_badge.classes(remove='pulse'), once=True)
            
            self._update_undo_visibility()
            
            # Add to 3D scene
            await self._create_and_throw_card(pair)
            
            ui.notify('Zebrano parę Q+A!', type='positive', position='top-right')

    def _truncate(self, text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + '...'

    # === Modal i Logika Biznesowa (Bez zmian) ===

    def _open_edit_modal(self, pair: 'QAPair'):
        if self._edit_dialog:
            try:
                self._edit_dialog.close()
            except Exception:
                pass

        with ui.dialog() as self._edit_dialog, ui.card().classes('w-[400px] p-4'):
            with ui.row().classes('w-full justify-between items-center mb-4'):
                ui.label('Edytuj parę Q+A').classes('text-lg font-semibold text-slate-800')
                ui.button(icon='close', on_click=self._edit_dialog.close).props('flat dense round')

            with ui.column().classes('w-full gap-1 mb-3'):
                ui.label('Pytanie').classes('text-xs text-slate-500 uppercase tracking-wide')
                ui.label(pair.question).classes(
                    'text-sm text-slate-700 p-2 bg-slate-50 rounded border border-slate-200'
                )

            with ui.column().classes('w-full gap-1 mb-4'):
                ui.label('Odpowiedź').classes('text-xs text-slate-500 uppercase tracking-wide')
                answer_input = ui.textarea(value=pair.answer).classes('w-full').props('outlined rows=3')

            with ui.row().classes('w-full justify-between'):
                ui.button('Usuń', icon='delete', on_click=lambda: self._delete_pair(pair.id)).props('flat color=red')
                ui.button('Zapisz', icon='save', on_click=lambda: self._save_pair_edit(pair.id, answer_input.value)).props('color=primary')

        self._edit_dialog.open()

    def _save_pair_edit(self, pair_id: str, new_answer: str):
        if self.state.qa_collector.update_answer(pair_id, new_answer):
            if self._edit_dialog: self._edit_dialog.close()
            # Tutaj moglibyśmy zaktualizować tekst na karcie 3D, ale to wymagałoby 
            # znalezienia elementu w DOM. Na razie prosty notify.
            ui.notify('Zapisano zmiany', type='positive')
            # W przyszłości: self.three_stage.update_card_content(...)

    def _delete_pair(self, pair_id: str):
        if self.state.qa_collector.remove(pair_id):
            if self._edit_dialog: self._edit_dialog.close()
            # TODO: Usunąć z 3D
            # self.three_stage.discard(pair_id) - wymagałoby mapowania ID elementu na ID pary
            ui.notify('Usunięto parę Q+A', type='info')
            self._remove_visual_card(pair_id)

    def _undo_last(self):
        removed = self.state.qa_collector.undo_last()
        if removed:
            ui.notify(f'Cofnięto parę: {self._truncate(removed.question, 30)}', type='info')
            self._remove_visual_card(removed.id)
            self._update_undo_visibility()

    def _remove_visual_card(self, pair_id: str):
        """Usuwa kartę z widoku (i ze zbioru dodanych)."""
        if pair_id in self._pair_element_map:
            card_el = self._pair_element_map[pair_id]
            if self.three_stage:
                # Async call from sync method needs handling if not already in loop
                # But typically this is called from callback.
                # Use background task for safety
                asyncio.create_task(self.three_stage.discard(card_el))
            
            # Cleanup maps
            del self._pair_element_map[pair_id]
            if pair_id in self._added_card_ids:
                self._added_card_ids.remove(pair_id)

    def _update_undo_visibility(self):
        if self.undo_btn:
            self.undo_btn.set_visibility(bool(self.state.qa_pairs))

    def refresh(self):
        """Metoda zgodności interfejsu."""
        pass