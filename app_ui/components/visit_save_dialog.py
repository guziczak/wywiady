"""
Dialog zapisywania wizyty.

Pozwala użytkownikowi zapisać wizytę z opcją wyboru/utworzenia pacjenta.
"""

from datetime import datetime
from typing import Optional, Callable, List, Dict, Any
from nicegui import ui

from core.models import Visit, Patient, VisitStatus
from core.services.visit_service import get_visit_service


class VisitSaveDialog:
    """Dialog do zapisywania wizyty."""

    def __init__(
        self,
        transcript: str,
        diagnoses: List[Dict],
        procedures: List[Dict],
        model_used: str = "",
        on_save: Optional[Callable[[Visit], None]] = None
    ):
        self.transcript = transcript
        self.diagnoses = diagnoses
        self.procedures = procedures
        self.model_used = model_used
        self.on_save = on_save

        self.visit_service = get_visit_service()
        self.dialog = None

        # Stan formularza
        self.selected_patient_id: Optional[int] = None
        self.patient_name = ""
        self.patient_identifier = ""
        self.patient_birth_date = ""
        self.patient_sex = ""
        self.patient_address = ""
        self.patient_phone = ""
        self.patient_email = ""
        self.visit_date = datetime.now()
        self.save_as_completed = True
        self.subjective = ""
        self.objective = ""
        self.assessment = ""
        self.plan = ""
        self.recommendations = ""
        self.medications = ""
        self.tests_ordered = ""
        self.tests_results = ""
        self.referrals = ""
        self.certificates = ""
        self.additional_notes = ""

        # Komponenty
        self.patient_select = None
        self.patient_name_input = None

    def open(self) -> None:
        """Otwiera dialog."""
        with ui.dialog() as self.dialog, ui.card().classes('w-full max-w-lg'):
            self._create_content()

        self.dialog.open()

    def close(self) -> None:
        """Zamyka dialog."""
        if self.dialog:
            self.dialog.close()

    def _create_content(self) -> None:
        """Tworzy zawartość dialogu."""
        ui.label('Zapisz wizytę').classes('text-xl font-bold')
        ui.separator()

        # Sekcja pacjenta
        ui.label('Pacjent').classes('font-bold mt-2')

        # Wybór istniejącego pacjenta
        recent_patients = self.visit_service.get_recent_patients(limit=10)
        patient_options = {
            0: '-- Nowy pacjent --',
            **{p.id: p.display_name for p in recent_patients}
        }

        self.patient_select = ui.select(
            label='Wybierz pacjenta',
            options=patient_options,
            value=0,
            on_change=lambda e: self._on_patient_select_change(e.value)
        ).props('outlined dense').classes('w-full')

        # Nazwa nowego pacjenta
        self.patient_name_input = ui.input(
            label='Nazwa pacjenta',
            placeholder='np. Jan K.',
            value=self.patient_name,
            on_change=lambda e: setattr(self, 'patient_name', e.value)
        ).props('outlined dense').classes('w-full')

        # Dane pacjenta (opcjonalnie)
        with ui.expansion('Dane pacjenta (opcjonalnie)', icon='badge').classes('w-full mt-2'):
            with ui.column().classes('w-full gap-3 p-2'):
                ui.input(
                    'PESEL / identyfikator',
                    value=self.patient_identifier
                ).classes('w-full').on('change', lambda e: setattr(self, 'patient_identifier', e.value))
                with ui.row().classes('w-full gap-2'):
                    ui.input(
                        'Data urodzenia',
                        placeholder='YYYY-MM-DD',
                        value=self.patient_birth_date
                    ).classes('flex-1').on('change', lambda e: setattr(self, 'patient_birth_date', e.value))
                    ui.select(
                        'Plec',
                        options=['', 'K', 'M', 'Inna'],
                        value=self.patient_sex
                    ).classes('flex-1').on('change', lambda e: setattr(self, 'patient_sex', e.value))
                ui.input(
                    'Adres',
                    value=self.patient_address
                ).classes('w-full').on('change', lambda e: setattr(self, 'patient_address', e.value))
                with ui.row().classes('w-full gap-2'):
                    ui.input(
                        'Telefon',
                        value=self.patient_phone
                    ).classes('flex-1').on('change', lambda e: setattr(self, 'patient_phone', e.value))
                    ui.input(
                        'Email',
                        value=self.patient_email
                    ).classes('flex-1').on('change', lambda e: setattr(self, 'patient_email', e.value))

        # Data wizyty
        ui.label('Data wizyty').classes('font-bold mt-4')
        with ui.input(
            label='Data i godzina',
            value=self.visit_date.strftime('%d.%m.%Y %H:%M')
        ).props('outlined dense').classes('w-full') as date_input:
            with ui.menu().props('no-parent-event') as menu:
                with ui.date(
                    value=self.visit_date.strftime('%Y-%m-%d'),
                    on_change=lambda e: self._on_date_change(e.value, date_input, menu)
                ):
                    pass
            with date_input.add_slot('append'):
                ui.icon('edit_calendar').on('click', menu.open).classes('cursor-pointer')

        # Status
        ui.label('Status').classes('font-bold mt-4')
        ui.toggle(
            {True: 'Zakończona', False: 'Szkic'},
            value=self.save_as_completed,
            on_change=lambda e: setattr(self, 'save_as_completed', e.value)
        ).classes('w-full')

        # Dane medyczne (SOAP)
        with ui.expansion('Dane medyczne (SOAP)', icon='assignment').classes('w-full mt-4'):
            with ui.column().classes('w-full gap-3 p-2'):
                ui.textarea(
                    'Wywiad (S)',
                    value=self.subjective,
                    placeholder='Podsumowanie wywiadu (opcjonalnie)'
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'subjective', e.value))
                ui.textarea(
                    'Badanie przedmiotowe (O)',
                    value=self.objective
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'objective', e.value))
                ui.textarea(
                    'Ocena / Rozpoznanie opisowe (A)',
                    value=self.assessment
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'assessment', e.value))
                ui.textarea(
                    'Plan (P)',
                    value=self.plan
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'plan', e.value))

        # Zalecenia i dokumenty
        with ui.expansion('Zalecenia i dokumenty', icon='description').classes('w-full mt-2'):
            with ui.column().classes('w-full gap-3 p-2'):
                ui.textarea(
                    'Zalecenia',
                    value=self.recommendations
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'recommendations', e.value))
                ui.textarea(
                    'Leki (z dawkowaniem)',
                    value=self.medications
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'medications', e.value))
                ui.textarea(
                    'Zlecone badania / konsultacje',
                    value=self.tests_ordered
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'tests_ordered', e.value))
                ui.textarea(
                    'Wyniki badan / konsultacji',
                    value=self.tests_results
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'tests_results', e.value))
                ui.textarea(
                    'Skierowania',
                    value=self.referrals
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'referrals', e.value))
                ui.textarea(
                    'Zaswiadczenia / Niezdolnosc do pracy',
                    value=self.certificates
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'certificates', e.value))
                ui.textarea(
                    'Dodatkowe uwagi',
                    value=self.additional_notes
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'additional_notes', e.value))

        # Podsumowanie
        ui.separator().classes('mt-4')
        with ui.card().classes('w-full bg-gray-50'):
            ui.label('Podsumowanie').classes('font-bold')
            with ui.column().classes('gap-1 text-sm'):
                ui.label(f'Diagnozy: {len(self.diagnoses)}')
                ui.label(f'Procedury: {len(self.procedures)}')
                ui.label(f'Model AI: {self.model_used or "-"}')
                transcript_preview = (self.transcript[:100] + '...') if len(self.transcript) > 100 else self.transcript
                ui.label(f'Transkrypcja: {len(self.transcript)} znaków').classes('text-gray-500')

        # Przyciski
        ui.separator().classes('mt-4')
        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Anuluj', on_click=self.close).props('flat')
            ui.button(
                'Zapisz wizytę',
                icon='save',
                on_click=self._save_visit
            ).props('color=primary')

    def _on_patient_select_change(self, patient_id: int) -> None:
        """Obsługa zmiany wybranego pacjenta."""
        if patient_id == 0:
            # Nowy pacjent
            self.selected_patient_id = None
            if self.patient_name_input:
                self.patient_name_input.visible = True
        else:
            # Istniejący pacjent
            self.selected_patient_id = patient_id
            patient = self.visit_service.patient_repo.get_by_id(patient_id)
            if patient:
                self.patient_name = patient.display_name
            if self.patient_name_input:
                self.patient_name_input.visible = False

    def _on_date_change(self, value: str, input_elem, menu) -> None:
        """Obsługa zmiany daty."""
        if value:
            # Zachowaj godzinę
            new_date = datetime.strptime(value, '%Y-%m-%d')
            self.visit_date = new_date.replace(
                hour=self.visit_date.hour,
                minute=self.visit_date.minute
            )
            input_elem.value = self.visit_date.strftime('%d.%m.%Y %H:%M')
        menu.close()

    def _save_visit(self) -> None:
        """Zapisuje wizytę."""
        # Walidacja
        if not self.selected_patient_id and not self.patient_name.strip():
            ui.notify('Podaj nazwę pacjenta', type='warning')
            return

        try:
            # Utwórz lub pobierz pacjenta
            patient_id = self.selected_patient_id
            patient_name = self.patient_name.strip()

            if not patient_id and patient_name:
                patient = self.visit_service.get_or_create_patient(patient_name)
                patient_id = patient.id
                patient_name = patient.display_name

            # Zapisz wizytę
            status = VisitStatus.COMPLETED if self.save_as_completed else VisitStatus.DRAFT

            visit = self.visit_service.save_visit(
                transcript=self.transcript,
                diagnoses=self.diagnoses,
                procedures=self.procedures,
                model_used=self.model_used,
                patient_name=patient_name,
                patient_identifier=self.patient_identifier.strip(),
                patient_birth_date=self.patient_birth_date.strip(),
                patient_sex=self.patient_sex.strip(),
                patient_address=self.patient_address.strip(),
                patient_phone=self.patient_phone.strip(),
                patient_email=self.patient_email.strip(),
                patient_id=patient_id,
                status=status,
                visit_date=self.visit_date,
                subjective=self.subjective.strip(),
                objective=self.objective.strip(),
                assessment=self.assessment.strip(),
                plan=self.plan.strip(),
                recommendations=self.recommendations.strip(),
                medications=self.medications.strip(),
                tests_ordered=self.tests_ordered.strip(),
                tests_results=self.tests_results.strip(),
                referrals=self.referrals.strip(),
                certificates=self.certificates.strip(),
                additional_notes=self.additional_notes.strip()
            )

            ui.notify('Wizyta zapisana!', type='positive')

            if self.on_save:
                self.on_save(visit)

            self.close()

        except Exception as e:
            ui.notify(f'Błąd zapisu: {e}', type='negative')


def open_save_visit_dialog(
    transcript: str,
    diagnoses: List[Dict],
    procedures: List[Dict],
    model_used: str = "",
    on_save: Optional[Callable[[Visit], None]] = None
) -> VisitSaveDialog:
    """
    Otwiera dialog zapisywania wizyty.

    Args:
        transcript: Transkrypcja wywiadu
        diagnoses: Lista diagnoz (format z AG-Grid)
        procedures: Lista procedur (format z AG-Grid)
        model_used: Nazwa użytego modelu AI
        on_save: Callback po zapisie

    Returns:
        Instancja dialogu
    """
    dialog = VisitSaveDialog(
        transcript=transcript,
        diagnoses=diagnoses,
        procedures=procedures,
        model_used=model_used,
        on_save=on_save
    )
    dialog.open()
    return dialog
