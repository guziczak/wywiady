"""
Dialog zapisywania wizyty.

Pozwala użytkownikowi zapisać wizytę z opcją wyboru/utworzenia pacjenta.
"""

from datetime import datetime
import asyncio
import re
from typing import Optional, Callable, List, Dict, Any
from nicegui import ui

from core.models import Visit, Patient, VisitStatus
from core.services.visit_service import get_visit_service
from core.llm_service import LLMService
from core.config_manager import ConfigManager


class VisitSaveDialog:
    """Dialog do zapisywania wizyty."""

    def __init__(
        self,
        transcript: str,
        diagnoses: List[Dict],
        procedures: List[Dict],
        model_used: str = "",
        existing_visit: Optional[Visit] = None,
        on_save: Optional[Callable[[Visit], None]] = None
    ):
        self.transcript = transcript
        self.diagnoses = diagnoses
        self.procedures = procedures
        self.model_used = model_used
        self.existing_visit = existing_visit
        self.on_save = on_save

        self.visit_service = get_visit_service()
        self.llm_service = LLMService()
        self.config_manager = ConfigManager()
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

        if self.existing_visit:
            self.selected_patient_id = self.existing_visit.patient_id
            self.patient_name = self.existing_visit.patient_name or ""
            self.patient_identifier = self.existing_visit.patient_identifier or ""
            self.patient_birth_date = self.existing_visit.patient_birth_date or ""
            self.patient_sex = self.existing_visit.patient_sex or ""
            self.patient_address = self.existing_visit.patient_address or ""
            self.patient_phone = self.existing_visit.patient_phone or ""
            self.patient_email = self.existing_visit.patient_email or ""
            self.visit_date = self.existing_visit.visit_date or datetime.now()
            self.save_as_completed = self.existing_visit.status == VisitStatus.COMPLETED
            self.subjective = self.existing_visit.subjective or ""
            self.objective = self.existing_visit.objective or ""
            self.assessment = self.existing_visit.assessment or ""
            self.plan = self.existing_visit.plan or ""
            self.recommendations = self.existing_visit.recommendations or ""
            self.medications = self.existing_visit.medications or ""
            self.tests_ordered = self.existing_visit.tests_ordered or ""
            self.tests_results = self.existing_visit.tests_results or ""
            self.referrals = self.existing_visit.referrals or ""
            self.certificates = self.existing_visit.certificates or ""
            self.additional_notes = self.existing_visit.additional_notes or ""

        # Komponenty
        self.patient_select = None
        self.patient_name_input = None
        self.patient_identifier_input = None
        self.patient_birth_date_input = None
        self.patient_sex_input = None
        self.patient_address_input = None
        self.patient_phone_input = None
        self.patient_email_input = None
        self.subjective_input = None
        self.objective_input = None
        self.assessment_input = None
        self.plan_input = None
        self.recommendations_input = None
        self.medications_input = None
        self.tests_ordered_input = None
        self.tests_results_input = None
        self.referrals_input = None
        self.certificates_input = None
        self.additional_notes_input = None
        self.soap_prefill_btn = None
        self.soap_spinner = None
        self.soap_model_label = None
        self._client = None

    def open(self) -> None:
        """Otwiera dialog."""
        with ui.dialog() as self.dialog, ui.card().classes('w-full max-w-lg'):
            self._create_content()

        # Capture client context for async UI updates
        self._client = ui.context.client
        self._apply_initial_state()
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
        if self.selected_patient_id and self.selected_patient_id not in patient_options:
            existing_patient = self.visit_service.patient_repo.get_by_id(self.selected_patient_id)
            if existing_patient:
                patient_options[self.selected_patient_id] = existing_patient.display_name

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
                self.patient_identifier_input = ui.input(
                    'PESEL / identyfikator',
                    value=self.patient_identifier
                ).classes('w-full').on('change', lambda e: setattr(self, 'patient_identifier', e.value))
                with ui.row().classes('w-full gap-2'):
                    self.patient_birth_date_input = ui.input(
                        'Data urodzenia',
                        placeholder='YYYY-MM-DD',
                        value=self.patient_birth_date
                    ).classes('flex-1').on('change', lambda e: setattr(self, 'patient_birth_date', e.value))
                    self.patient_sex_input = ui.select(
                        label='Plec',
                        options=['', 'K', 'M', 'Inna'],
                        value=self.patient_sex
                    ).classes('flex-1').on('change', lambda e: setattr(self, 'patient_sex', e.value))
                self.patient_address_input = ui.input(
                    'Adres',
                    value=self.patient_address
                ).classes('w-full').on('change', lambda e: setattr(self, 'patient_address', e.value))
                with ui.row().classes('w-full gap-2'):
                    self.patient_phone_input = ui.input(
                        'Telefon',
                        value=self.patient_phone
                    ).classes('flex-1').on('change', lambda e: setattr(self, 'patient_phone', e.value))
                    self.patient_email_input = ui.input(
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
                with ui.row().classes('w-full items-center gap-2'):
                    self.soap_prefill_btn = ui.button(
                        'Wypelnij z AI',
                        icon='auto_fix_high',
                        on_click=self._prefill_soap_clicked
                    ).props('flat color=primary')
                    self.soap_spinner = ui.spinner('dots', size='sm')
                    self.soap_spinner.visible = False
                    self.soap_model_label = ui.label('')

                self.subjective_input = ui.textarea(
                    'Wywiad (S)',
                    value=self.subjective,
                    placeholder='Podsumowanie wywiadu (opcjonalnie)'
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'subjective', e.value))
                self.objective_input = ui.textarea(
                    'Badanie przedmiotowe (O)',
                    value=self.objective
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'objective', e.value))
                self.assessment_input = ui.textarea(
                    'Ocena / Rozpoznanie opisowe (A)',
                    value=self.assessment
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'assessment', e.value))
                self.plan_input = ui.textarea(
                    'Plan (P)',
                    value=self.plan
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'plan', e.value))

        # Zalecenia i dokumenty
        with ui.expansion('Zalecenia i dokumenty', icon='description').classes('w-full mt-2'):
            with ui.column().classes('w-full gap-3 p-2'):
                self.recommendations_input = ui.textarea(
                    'Zalecenia',
                    value=self.recommendations
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'recommendations', e.value))
                self.medications_input = ui.textarea(
                    'Leki (z dawkowaniem)',
                    value=self.medications
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'medications', e.value))
                self.tests_ordered_input = ui.textarea(
                    'Zlecone badania / konsultacje',
                    value=self.tests_ordered
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'tests_ordered', e.value))
                self.tests_results_input = ui.textarea(
                    'Wyniki badan / konsultacji',
                    value=self.tests_results
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'tests_results', e.value))
                self.referrals_input = ui.textarea(
                    'Skierowania',
                    value=self.referrals
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'referrals', e.value))
                self.certificates_input = ui.textarea(
                    'Zaswiadczenia / Niezdolnosc do pracy',
                    value=self.certificates
                ).classes('w-full').props('outlined').on('change', lambda e: setattr(self, 'certificates', e.value))
                self.additional_notes_input = ui.textarea(
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
            self._set_patient_fields_from_patient(None, overwrite=True)
            if self.patient_name_input:
                self.patient_name_input.visible = True
        else:
            # Istniejący pacjent
            self.selected_patient_id = patient_id
            patient = self.visit_service.patient_repo.get_by_id(patient_id)
            if patient:
                self._set_patient_fields_from_patient(patient, overwrite=True)
            if self.patient_name_input:
                self.patient_name_input.visible = False

    def _set_patient_fields_from_patient(self, patient: Optional[Patient], overwrite: bool = True) -> None:
        """Uzupełnia pola formularza na podstawie kartoteki pacjenta."""
        if patient is None:
            self.patient_name = ""
            self.patient_identifier = ""
            self.patient_birth_date = ""
            self.patient_sex = ""
            self.patient_address = ""
            self.patient_phone = ""
            self.patient_email = ""
        else:
            if overwrite or not self.patient_name:
                self.patient_name = patient.display_name or self.patient_name
            if overwrite or not self.patient_identifier:
                self.patient_identifier = getattr(patient, "identifier", "") or self.patient_identifier
            if overwrite or not self.patient_birth_date:
                self.patient_birth_date = getattr(patient, "birth_date", "") or self.patient_birth_date
            if overwrite or not self.patient_sex:
                self.patient_sex = getattr(patient, "sex", "") or self.patient_sex
            if overwrite or not self.patient_address:
                self.patient_address = getattr(patient, "address", "") or self.patient_address
            if overwrite or not self.patient_phone:
                self.patient_phone = getattr(patient, "phone", "") or self.patient_phone
            if overwrite or not self.patient_email:
                self.patient_email = getattr(patient, "email", "") or self.patient_email

        if self.patient_name_input:
            self.patient_name_input.value = self.patient_name
            self.patient_name_input.update()
        if self.patient_identifier_input:
            self.patient_identifier_input.value = self.patient_identifier
            self.patient_identifier_input.update()
        if self.patient_birth_date_input:
            self.patient_birth_date_input.value = self.patient_birth_date
            self.patient_birth_date_input.update()
        if self.patient_sex_input:
            self.patient_sex_input.value = self.patient_sex
            self.patient_sex_input.update()
        if self.patient_address_input:
            self.patient_address_input.value = self.patient_address
            self.patient_address_input.update()
        if self.patient_phone_input:
            self.patient_phone_input.value = self.patient_phone
            self.patient_phone_input.update()
        if self.patient_email_input:
            self.patient_email_input.value = self.patient_email
            self.patient_email_input.update()

    def _apply_initial_state(self) -> None:
        """Ustawia stan formularza po wyrenderowaniu."""
        if self.patient_select:
            self.patient_select.value = self.selected_patient_id or 0
            self.patient_select.update()

        if self.selected_patient_id:
            patient = self.visit_service.patient_repo.get_by_id(self.selected_patient_id)
            if patient:
                # Uzupelnij brakujace pola z kartoteki pacjenta
                self._set_patient_fields_from_patient(patient, overwrite=False)
            if self.patient_name_input:
                self.patient_name_input.visible = False
        else:
            if self.patient_name_input:
                self.patient_name_input.visible = True

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

    def _set_soap_loading(self, loading: bool) -> None:
        if self.soap_prefill_btn:
            self.soap_prefill_btn.disabled = loading
        if self.soap_spinner:
            self.soap_spinner.visible = loading
            self.soap_spinner.update()
        if self.soap_model_label and not loading:
            self.soap_model_label.update()

    def _apply_soap_result(self, data: Dict[str, Any], model_used: str = "") -> None:
        def _set(field: str, input_attr: str):
            value = (data.get(field) or "").strip()
            setattr(self, field, value)
            input_elem = getattr(self, input_attr, None)
            if input_elem is not None:
                input_elem.value = value
                input_elem.update()

        _set("subjective", "subjective_input")
        _set("objective", "objective_input")
        _set("assessment", "assessment_input")
        _set("plan", "plan_input")
        _set("recommendations", "recommendations_input")
        _set("medications", "medications_input")
        _set("tests_ordered", "tests_ordered_input")
        _set("tests_results", "tests_results_input")
        _set("referrals", "referrals_input")
        _set("certificates", "certificates_input")
        _set("additional_notes", "additional_notes_input")

        if self.soap_model_label is not None:
            self.soap_model_label.text = f"Model: {model_used}" if model_used else ""
            self.soap_model_label.update()

    def _prefill_soap_clicked(self) -> None:
        asyncio.create_task(self._prefill_soap())

    async def _prefill_soap(self) -> None:
        if not self.transcript.strip():
            if self._client:
                with self._client:
                    ui.notify('Brak transkrypcji do analizy', type='warning')
            return

        if self._client:
            with self._client:
                self._set_soap_loading(True)
        try:
            result, used_model = await self.llm_service.generate_soap(
                transcript=self.transcript,
                config=self.config_manager,
                diagnoses=self.diagnoses,
                procedures=self.procedures,
            )
            if not isinstance(result, dict):
                if self._client:
                    with self._client:
                        ui.notify('Nieudane parsowanie wyniku AI', type='negative')
                return
            if self._client:
                with self._client:
                    self._apply_soap_result(result, used_model)
                    ui.notify('SOAP uzupelniony przez AI', type='positive')
        except Exception as e:
            if self._client:
                with self._client:
                    ui.notify(f'Blad AI: {e}', type='negative')
        finally:
            if self._client:
                with self._client:
                    self._set_soap_loading(False)

    def _normalize_birth_date(self, value: str) -> Optional[str]:
        raw = value.strip()
        if not raw:
            return ""
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def _normalize_phone(self, value: str) -> str:
        raw = value.strip()
        if not raw:
            return ""
        return re.sub(r"\D", "", raw)

    def _is_valid_pesel(self, pesel: str) -> bool:
        if not pesel.isdigit() or len(pesel) != 11:
            return False
        weights = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
        checksum = sum(int(pesel[i]) * weights[i] for i in range(10))
        control = (10 - (checksum % 10)) % 10
        return control == int(pesel[-1])

    def _validate_patient_fields(self) -> bool:
        ident = (self.patient_identifier or "").strip()
        if ident:
            if ident.isdigit():
                if len(ident) != 11:
                    ui.notify('PESEL powinien miec 11 cyfr', type='warning')
                    return False
                if not self._is_valid_pesel(ident):
                    ui.notify('Nieprawidlowy PESEL (suma kontrolna)', type='warning')
                    return False
            self.patient_identifier = ident
            if self.patient_identifier_input:
                self.patient_identifier_input.value = ident
                self.patient_identifier_input.update()

        birth = (self.patient_birth_date or "").strip()
        if birth:
            normalized = self._normalize_birth_date(birth)
            if normalized is None:
                ui.notify('Nieprawidlowa data urodzenia (YYYY-MM-DD lub DD.MM.YYYY)', type='warning')
                return False
            self.patient_birth_date = normalized
            if self.patient_birth_date_input:
                self.patient_birth_date_input.value = normalized
                self.patient_birth_date_input.update()

        phone = (self.patient_phone or "").strip()
        if phone:
            normalized_phone = self._normalize_phone(phone)
            if normalized_phone and (len(normalized_phone) < 7 or len(normalized_phone) > 15):
                ui.notify('Nieprawidlowy numer telefonu', type='warning')
                return False
            self.patient_phone = normalized_phone
            if self.patient_phone_input:
                self.patient_phone_input.value = normalized_phone
                self.patient_phone_input.update()

        email = (self.patient_email or "").strip()
        if email:
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                ui.notify('Nieprawidlowy email', type='warning')
                return False
            self.patient_email = email
            if self.patient_email_input:
                self.patient_email_input.value = email
                self.patient_email_input.update()

        return True

    def _save_visit(self) -> None:
        """Zapisuje wizytę."""
        # Walidacja
        if not self.selected_patient_id and not self.patient_name.strip():
            ui.notify('Podaj nazwę pacjenta', type='warning')
            return
        if not self._validate_patient_fields():
            return

        try:
            # Utwórz lub pobierz pacjenta
            patient_id = self.selected_patient_id
            patient_name = self.patient_name.strip()

            if not patient_id and patient_name:
                patient = self.visit_service.get_or_create_patient(
                    display_name=patient_name,
                    identifier=self.patient_identifier.strip(),
                    birth_date=self.patient_birth_date.strip(),
                    sex=self.patient_sex.strip(),
                    address=self.patient_address.strip(),
                    phone=self.patient_phone.strip(),
                    email=self.patient_email.strip(),
                )
                patient_id = patient.id
                patient_name = patient.display_name

            # Zapisz wizytę
            status = VisitStatus.COMPLETED if self.save_as_completed else VisitStatus.DRAFT

            visit = self.visit_service.save_visit(
                transcript=self.transcript,
                diagnoses=self.diagnoses,
                procedures=self.procedures,
                model_used=self.model_used,
                visit_id=self.existing_visit.id if self.existing_visit else None,
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

            visit_id = getattr(visit, 'id', None)
            if visit_id:
                ui.notify(f'Wizyta zapisana: {visit_id[:8]}...', type='positive')
            else:
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
    existing_visit: Optional[Visit] = None,
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
        existing_visit=existing_visit,
        on_save=on_save
    )
    dialog.open()
    return dialog
