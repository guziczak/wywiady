"""
Dialog szczegółów wizyty.

Wyświetla pełne informacje o wizycie z możliwością edycji i eksportu.
"""

from typing import Optional, Callable
from nicegui import ui

from core.models import Visit, VisitStatus


class VisitDetailDialog:
    """Dialog wyświetlający szczegóły wizyty."""

    def __init__(
        self,
        visit: Visit,
        on_export_pdf: Optional[Callable[[Visit], None]] = None,
        on_delete: Optional[Callable[[Visit], None]] = None,
        on_edit: Optional[Callable[[Visit], None]] = None
    ):
        self.visit = visit
        self.on_export_pdf = on_export_pdf
        self.on_delete = on_delete
        self.on_edit = on_edit
        self.dialog = None

    def open(self) -> None:
        """Otwiera dialog."""
        with ui.dialog() as self.dialog, ui.card().classes('w-full max-w-4xl'):
            self._create_content()

        self.dialog.open()

    def close(self) -> None:
        """Zamyka dialog."""
        if self.dialog:
            self.dialog.close()

    def _create_content(self) -> None:
        """Tworzy zawartość dialogu."""
        # Header
        with ui.row().classes('w-full items-center justify-between'):
            with ui.row().classes('items-center gap-2'):
                ui.label('Szczegóły wizyty').classes('text-xl font-bold')
                self._create_status_badge()

            with ui.row().classes('items-center gap-2'):
                if self.on_export_pdf:
                    ui.button(
                        'Eksport PDF',
                        icon='picture_as_pdf',
                        on_click=lambda: self._export_pdf()
                    ).props('flat color=primary')

                ui.button(
                    icon='close',
                    on_click=self.close
                ).props('flat round')

        ui.separator()

        # Meta info
        with ui.card().classes('w-full bg-gray-50'):
            with ui.grid(columns=2).classes('w-full gap-4'):
                self._info_row('Data wizyty', self._format_datetime(self.visit.visit_date))
                self._info_row('Pacjent', self.visit.patient_name or 'Anonimowy')
                self._info_row('Model AI', self.visit.model_used or '-')
                self._info_row('ID', self.visit.id[:8] + '...')

        # Transcript
        ui.label('Wywiad').classes('text-lg font-bold mt-4')
        with ui.card().classes('w-full'):
            ui.label(self.visit.transcript or 'Brak transkrypcji').classes(
                'whitespace-pre-wrap text-sm'
            )

        # Diagnoses
        ui.label('Diagnozy (ICD-10)').classes('text-lg font-bold mt-4')
        if self.visit.diagnoses:
            ui.table(
                columns=[
                    {'name': 'icd10_code', 'label': 'Kod', 'field': 'icd10_code', 'align': 'left'},
                    {'name': 'location', 'label': 'Lokalizacja', 'field': 'location', 'align': 'left'},
                    {'name': 'icd10_name', 'label': 'Nazwa', 'field': 'icd10_name', 'align': 'left'},
                    {'name': 'description', 'label': 'Opis', 'field': 'description', 'align': 'left'},
                ],
                rows=[d.to_dict() for d in self.visit.diagnoses],
                row_key='icd10_code'
            ).classes('w-full')
        else:
            ui.label('Brak diagnoz').classes('text-gray-500 italic')

        # Procedures
        ui.label('Procedury').classes('text-lg font-bold mt-4')
        if self.visit.procedures:
            ui.table(
                columns=[
                    {'name': 'procedure_code', 'label': 'Kod', 'field': 'procedure_code', 'align': 'left'},
                    {'name': 'location', 'label': 'Lokalizacja', 'field': 'location', 'align': 'left'},
                    {'name': 'procedure_name', 'label': 'Procedura', 'field': 'procedure_name', 'align': 'left'},
                    {'name': 'description', 'label': 'Opis', 'field': 'description', 'align': 'left'},
                ],
                rows=[p.to_dict() for p in self.visit.procedures],
                row_key='procedure_code'
            ).classes('w-full')
        else:
            ui.label('Brak procedur').classes('text-gray-500 italic')

        # Footer actions
        ui.separator().classes('mt-4')
        with ui.row().classes('w-full justify-between'):
            if self.on_delete:
                ui.button(
                    'Usuń wizytę',
                    icon='delete',
                    on_click=self._confirm_delete
                ).props('flat color=negative')

            with ui.row().classes('gap-2'):
                ui.button('Zamknij', on_click=self.close).props('flat')

    def _create_status_badge(self) -> None:
        """Tworzy badge ze statusem."""
        if self.visit.status == VisitStatus.COMPLETED:
            ui.badge('Zakończona', color='green')
        else:
            ui.badge('Szkic', color='orange')

    def _info_row(self, label: str, value: str) -> None:
        """Tworzy wiersz informacji."""
        with ui.column().classes('gap-0'):
            ui.label(label).classes('text-xs text-gray-500')
            ui.label(value).classes('font-medium')

    def _format_datetime(self, dt) -> str:
        """Formatuje datę i czas."""
        if not dt:
            return '-'
        return dt.strftime('%d.%m.%Y, godz. %H:%M')

    def _export_pdf(self) -> None:
        """Eksportuje do PDF."""
        if self.on_export_pdf:
            self.on_export_pdf(self.visit)

    def _confirm_delete(self) -> None:
        """Potwierdza usunięcie."""
        with ui.dialog() as confirm_dialog, ui.card():
            ui.label('Czy na pewno chcesz usunąć tę wizytę?').classes('text-lg')
            ui.label('Ta operacja jest nieodwracalna.').classes('text-gray-500')

            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('Anuluj', on_click=confirm_dialog.close).props('flat')
                ui.button(
                    'Usuń',
                    on_click=lambda: self._do_delete(confirm_dialog)
                ).props('color=negative')

        confirm_dialog.open()

    def _do_delete(self, confirm_dialog) -> None:
        """Wykonuje usunięcie."""
        confirm_dialog.close()
        if self.on_delete:
            self.on_delete(self.visit)
        self.close()
