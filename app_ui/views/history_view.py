"""
Widok historii wizyt.

Wyświetla listę wizyt z filtrowaniem, paginacją i akcjami.
"""

from datetime import datetime, date
from typing import Optional, Callable
from nicegui import ui

from core.models import Visit, VisitStatus
from core.services import VisitService
from core.services.visit_service import get_visit_service
from core.pdf_generator import get_pdf_generator


class HistoryView:
    """Widok historii wizyt."""

    def __init__(self, on_edit_visit: Optional[Callable[[Visit], None]] = None):
        self.visit_service = get_visit_service()
        self.pdf_generator = get_pdf_generator()
        self.on_edit_visit = on_edit_visit

        # Stan filtrów
        self.search_text = ""
        self.status_filter: Optional[VisitStatus] = None
        self.date_from: Optional[date] = None
        self.date_to: Optional[date] = None
        self.current_page = 1
        self.per_page = 20

        # Referencje do komponentów
        self.grid = None
        self.pagination_label = None
        self.stats_label = None

    def create(self) -> None:
        """Tworzy widok historii."""
        with ui.column().classes('w-full gap-4 p-4'):
            self._create_header()
            self._create_filters()
            self._create_table()
            self._create_pagination()

        # Załaduj dane
        self.refresh_data()

    def _create_header(self) -> None:
        """Nagłówek z tytułem i statystykami."""
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('Historia wizyt').classes('text-2xl font-bold')

            with ui.row().classes('items-center gap-4'):
                self.stats_label = ui.label('').classes('text-gray-500')
                ui.button(
                    'Odśwież',
                    icon='refresh',
                    on_click=self.refresh_data
                ).props('flat')

    def _create_filters(self) -> None:
        """Sekcja filtrów."""
        with ui.card().classes('w-full'):
            with ui.row().classes('w-full items-end gap-4 flex-wrap'):
                # Wyszukiwanie
                ui.input(
                    label='Szukaj',
                    placeholder='Pacjent, transkrypcja...',
                    on_change=lambda e: self._on_search_change(e.value)
                ).props('outlined dense clearable').classes('w-64')

                # Status
                ui.select(
                    label='Status',
                    options={
                        None: 'Wszystkie',
                        'completed': 'Zakonczone',
                        'draft': 'Szkice'
                    },
                    value=None,
                    on_change=lambda e: self._on_status_change(e.value)
                ).props('outlined dense').classes('w-40')

                # Data od
                with ui.input(label='Od daty').props('outlined dense').classes('w-40') as date_from_input:
                    with ui.menu().props('no-parent-event') as menu_from:
                        with ui.date(on_change=lambda e: self._on_date_from_change(e.value, date_from_input, menu_from)):
                            pass
                    with date_from_input.add_slot('append'):
                        ui.icon('edit_calendar').on('click', menu_from.open).classes('cursor-pointer')

                # Data do
                with ui.input(label='Do daty').props('outlined dense').classes('w-40') as date_to_input:
                    with ui.menu().props('no-parent-event') as menu_to:
                        with ui.date(on_change=lambda e: self._on_date_to_change(e.value, date_to_input, menu_to)):
                            pass
                    with date_to_input.add_slot('append'):
                        ui.icon('edit_calendar').on('click', menu_to.open).classes('cursor-pointer')

                # Reset filtrów
                ui.button(
                    'Wyczyść filtry',
                    icon='filter_alt_off',
                    on_click=self._reset_filters
                ).props('flat dense')

    def _create_table(self) -> None:
        """Tabela wizyt (ui.table)."""
        columns = [
            {'name': 'visit_date', 'label': 'Data', 'field': 'visit_date', 'sortable': True},
            {'name': 'patient_name', 'label': 'Pacjent', 'field': 'patient_name', 'sortable': True},
            {'name': 'diagnoses_summary', 'label': 'Diagnozy', 'field': 'diagnoses_summary'},
            {'name': 'status', 'label': 'Status', 'field': 'status', 'sortable': True},
            {'name': 'actions', 'label': 'Akcje', 'field': 'actions'}
        ]

        self.grid = ui.table(columns=columns, rows=[], row_key='id').classes('w-full')
        
        # Slot na akcje
        self.grid.add_slot('body-cell-actions', '''
            <q-td :props="props">
                <q-btn flat round dense icon="visibility" @click="$parent.$emit('view_visit', props.row.id)" />
                <q-btn flat round dense icon="picture_as_pdf" @click="$parent.$emit('export_visit_pdf', props.row.id)" />
                <q-btn flat round dense icon="delete" color="negative" @click="$parent.$emit('delete_visit', props.row.id)" />
            </q-td>
        ''')
        
        # Slot na status (kolory)
        self.grid.add_slot('body-cell-status', '''
            <q-td :props="props">
                <q-badge :color="props.value === 'completed' ? 'green' : 'orange'">
                    {{ props.value === 'completed' ? 'Zakończona' : 'Szkic' }}
                </q-badge>
            </q-td>
        ''')

        # Obsługa eventów z tabeli
        self.grid.on('view_visit', lambda e: self._on_view_visit(e.args))
        self.grid.on('export_visit_pdf', lambda e: self._on_export_pdf(e.args))
        self.grid.on('delete_visit', lambda e: self._on_delete_visit(e.args))

    def _create_pagination(self) -> None:
        """Kontrolki paginacji."""
        with ui.row().classes('w-full items-center justify-between mt-4'):
            self.pagination_label = ui.label('').classes('text-gray-500')

            with ui.row().classes('items-center gap-2'):
                ui.button(
                    icon='first_page',
                    on_click=lambda: self._go_to_page(1)
                ).props('flat dense')

                ui.button(
                    icon='navigate_before',
                    on_click=lambda: self._go_to_page(self.current_page - 1)
                ).props('flat dense')

                ui.button(
                    icon='navigate_next',
                    on_click=lambda: self._go_to_page(self.current_page + 1)
                ).props('flat dense')

                ui.button(
                    icon='last_page',
                    on_click=lambda: self._go_to_page(999)  # Will be clamped
                ).props('flat dense')

    def refresh_data(self) -> None:
        """Odświeża dane w tabeli."""
        status = VisitStatus(self.status_filter) if self.status_filter else None

        visits, total, total_pages = self.visit_service.get_visits(
            status=status,
            date_from=self.date_from,
            date_to=self.date_to,
            search=self.search_text if self.search_text else None,
            page=self.current_page,
            per_page=self.per_page
        )

        # Przygotuj dane do tabeli
        row_data = []
        for visit in visits:
            row_data.append({
                'id': visit.id,
                'visit_date': visit.visit_date.isoformat() if visit.visit_date else None,
                'patient_name': visit.patient_name or 'Anonimowy',
                'diagnoses_summary': visit.get_diagnoses_summary(),
                'status': str(visit.status)
            })

        # Aktualizuj tabelę
        if self.grid:
            self.grid.rows = row_data
            self.grid.update()

        # Aktualizuj paginację
        if self.pagination_label:
            start = (self.current_page - 1) * self.per_page + 1
            end = min(self.current_page * self.per_page, total)
            self.pagination_label.text = f'Wyświetlanie {start}-{end} z {total}'

        # Aktualizuj statystyki
        if self.stats_label:
            stats = self.visit_service.get_statistics()
            self.stats_label.text = f"Razem: {stats['total']} | Zakończone: {stats['completed']} | Szkice: {stats['drafts']}"

        # Zapisz total_pages do nawigacji
        self._total_pages = total_pages

    def _on_search_change(self, value: str) -> None:
        """Obsługa zmiany wyszukiwania."""
        self.search_text = value
        self.current_page = 1
        self.refresh_data()

    def _on_status_change(self, value: Optional[str]) -> None:
        """Obsługa zmiany filtra statusu."""
        self.status_filter = value
        self.current_page = 1
        self.refresh_data()

    def _on_date_from_change(self, value: str, input_elem, menu) -> None:
        """Obsługa zmiany daty od."""
        if value:
            self.date_from = date.fromisoformat(value)
            input_elem.value = self.date_from.strftime('%d.%m.%Y')
        else:
            self.date_from = None
            input_elem.value = ''
        menu.close()
        self.current_page = 1
        self.refresh_data()

    def _on_date_to_change(self, value: str, input_elem, menu) -> None:
        """Obsługa zmiany daty do."""
        if value:
            self.date_to = date.fromisoformat(value)
            input_elem.value = self.date_to.strftime('%d.%m.%Y')
        else:
            self.date_to = None
            input_elem.value = ''
        menu.close()
        self.current_page = 1
        self.refresh_data()

    def _reset_filters(self) -> None:
        """Resetuje wszystkie filtry."""
        self.search_text = ""
        self.status_filter = None
        self.date_from = None
        self.date_to = None
        self.current_page = 1
        self.refresh_data()

    def _go_to_page(self, page: int) -> None:
        """Przechodzi do strony."""
        max_page = getattr(self, '_total_pages', 1) or 1
        self.current_page = max(1, min(page, max_page))
        self.refresh_data()

    def _on_view_visit(self, visit_id: str) -> None:
        """Otwiera szczegóły wizyty."""
        visit = self.visit_service.get_visit(visit_id)
        if visit:
            from .visit_detail_view import VisitDetailDialog
            dialog = VisitDetailDialog(
                visit=visit,
                on_export_pdf=lambda v: self._on_export_pdf(v.id),
                on_delete=lambda v: self._on_delete_visit(v.id)
            )
            dialog.open()

    def _on_export_pdf(self, visit_id: str) -> None:
        """Eksportuje wizytę do PDF."""
        visit = self.visit_service.get_visit(visit_id)
        if visit:
            try:
                path = self.pdf_generator.generate_visit_report(visit, open_after=True)
                ui.notify(f'PDF wygenerowany: {path}', type='positive')
            except Exception as e:
                ui.notify(f'Błąd generowania PDF: {e}', type='negative')

    def _on_delete_visit(self, visit_id: str) -> None:
        """Usuwa wizytę."""
        if self.visit_service.delete_visit(visit_id):
            ui.notify('Wizyta usunięta', type='positive')
            self.refresh_data()
        else:
            ui.notify('Nie udało się usunąć wizyty', type='negative')


def create_history_view(on_edit_visit: Optional[Callable[[Visit], None]] = None) -> HistoryView:
    """Tworzy i zwraca widok historii."""
    view = HistoryView(on_edit_visit=on_edit_visit)
    view.create()
    return view
