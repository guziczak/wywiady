"""
Serwis wizyt - logika biznesowa.

Łączy repozytoria z logiką aplikacji.
"""

from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime, date
from pathlib import Path

from core.models import Visit, Patient, VisitStatus, VisitDiagnosis, VisitProcedure
from core.repositories import VisitRepository, PatientRepository


class VisitService:
    """
    Serwis do zarządzania wizytami.

    Zapewnia wysokopoziomowe operacje łączące repozytoria
    z logiką biznesową.
    """

    def __init__(self):
        self.visit_repo = VisitRepository()
        self.patient_repo = PatientRepository()

    def create_visit_from_llm_result(
        self,
        transcript: str,
        llm_result: Dict[str, Any],
        model_used: str,
        patient_name: Optional[str] = None,
        patient_id: Optional[int] = None,
        save_as_completed: bool = False
    ) -> Visit:
        """
        Tworzy i zapisuje wizytę z wyniku LLM.

        Args:
            transcript: Transkrypcja wywiadu
            llm_result: Wynik z LLMService.generate_description()
            model_used: Nazwa użytego modelu
            patient_name: Opcjonalna nazwa pacjenta
            patient_id: Opcjonalne ID istniejącego pacjenta
            save_as_completed: Czy oznaczyć jako zakończoną

        Returns:
            Zapisana wizyta
        """
        # Jeśli podano patient_id, pobierz dane pacjenta
        if patient_id:
            patient = self.patient_repo.get_by_id(patient_id)
            if patient:
                patient_name = patient.display_name
        elif not patient_name:
            patient_name = "Pacjent anonimowy"

        # Utwórz wizytę
        visit = Visit.from_llm_result(
            transcript=transcript,
            llm_result=llm_result,
            model_used=model_used,
            patient_id=patient_id,
            patient_name=patient_name or ""
        )

        if save_as_completed:
            visit.complete()

        # Zapisz do bazy
        return self.visit_repo.save(visit)

    def save_visit(
        self,
        transcript: str,
        diagnoses: List[Dict],
        procedures: List[Dict],
        model_used: str = "",
        visit_id: Optional[str] = None,
        patient_name: str = "",
        patient_identifier: str = "",
        patient_birth_date: str = "",
        patient_sex: str = "",
        patient_address: str = "",
        patient_phone: str = "",
        patient_email: str = "",
        patient_id: Optional[int] = None,
        status: VisitStatus = VisitStatus.DRAFT,
        visit_date: Optional[datetime] = None,
        subjective: str = "",
        objective: str = "",
        assessment: str = "",
        plan: str = "",
        recommendations: str = "",
        medications: str = "",
        tests_ordered: str = "",
        tests_results: str = "",
        referrals: str = "",
        certificates: str = "",
        additional_notes: str = ""
    ) -> Visit:
        """
        Zapisuje wizytę z ręcznie podanymi danymi.

        Args:
            transcript: Transkrypcja
            diagnoses: Lista diagnoz (format z AG-Grid)
            procedures: Lista procedur (format z AG-Grid)
            model_used: Użyty model AI
            patient_name: Nazwa pacjenta
            patient_id: ID pacjenta
            status: Status wizyty
            visit_date: Data wizyty (domyślnie teraz)

        Returns:
            Zapisana wizyta
        """
        # Pacjent: pobierz i uzupelnij dane
        patient = None
        if patient_id:
            patient = self.patient_repo.get_by_id(patient_id)
        elif patient_name:
            patient = self.get_or_create_patient(
                display_name=patient_name,
                identifier=patient_identifier,
                birth_date=patient_birth_date,
                sex=patient_sex,
                address=patient_address,
                phone=patient_phone,
                email=patient_email,
            )
            patient_id = patient.id

        if patient:
            # Uzupelnij brakujace dane wizyty z kartoteki pacjenta
            if not patient_name:
                patient_name = patient.display_name
            if not patient_identifier:
                patient_identifier = patient.identifier or patient_identifier
            if not patient_birth_date:
                patient_birth_date = patient.birth_date or patient_birth_date
            if not patient_sex:
                patient_sex = patient.sex or patient_sex
            if not patient_address:
                patient_address = patient.address or patient_address
            if not patient_phone:
                patient_phone = patient.phone or patient_phone
            if not patient_email:
                patient_email = patient.email or patient_email

            # Aktualizuj kartoteke pacjenta danymi z wizyty
            if self._merge_patient_fields(
                patient,
                display_name=patient_name,
                identifier=patient_identifier,
                birth_date=patient_birth_date,
                sex=patient_sex,
                address=patient_address,
                phone=patient_phone,
                email=patient_email,
            ):
                self.patient_repo.save(patient)
        else:
            # Jesli patient_id nie istnieje w bazie, nie zapisuj referencji
            if patient_id:
                patient_id = None

        visit_kwargs = dict(
            transcript=transcript,
            model_used=model_used,
            patient_name=patient_name,
            patient_identifier=patient_identifier,
            patient_birth_date=patient_birth_date,
            patient_sex=patient_sex,
            patient_address=patient_address,
            patient_phone=patient_phone,
            patient_email=patient_email,
            patient_id=patient_id,
            status=status,
            visit_date=visit_date or datetime.now(),
            subjective=subjective,
            objective=objective,
            assessment=assessment,
            plan=plan,
            recommendations=recommendations,
            medications=medications,
            tests_ordered=tests_ordered,
            tests_results=tests_results,
            referrals=referrals,
            certificates=certificates,
            additional_notes=additional_notes
        )
        if visit_id:
            visit_kwargs["id"] = visit_id

        visit = Visit(**visit_kwargs)

        # Dodaj diagnozy
        for i, diag in enumerate(diagnoses):
            diagnosis = VisitDiagnosis(
                icd10_code=diag.get('kod', diag.get('icd10_code', '')),
                icd10_name=diag.get('nazwa', diag.get('icd10_name', '')),
                location=diag.get('zab', diag.get('location', '')),
                description=diag.get('opis_tekstowy', diag.get('description', '')),
                display_order=i
            )
            visit.add_diagnosis(diagnosis)

        # Dodaj procedury
        for i, proc in enumerate(procedures):
            procedure = VisitProcedure(
                procedure_code=proc.get('kod', proc.get('procedure_code', '')),
                procedure_name=proc.get('nazwa', proc.get('procedure_name', '')),
                location=proc.get('zab', proc.get('location', '')),
                description=proc.get('opis_tekstowy', proc.get('description', '')),
                display_order=i
            )
            visit.add_procedure(procedure)

        return self.visit_repo.save(visit)

    def get_visit(self, visit_id: str) -> Optional[Visit]:
        """Pobiera wizytę po ID."""
        return self.visit_repo.get_by_id(visit_id)

    def get_visits(
        self,
        patient_id: Optional[int] = None,
        status: Optional[VisitStatus] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        search: Optional[str] = None,
        page: int = 1,
        per_page: int = 20
    ) -> Tuple[List[Visit], int, int]:
        """
        Pobiera listę wizyt z paginacją.

        Args:
            patient_id: Filtruj po pacjencie
            status: Filtruj po statusie
            date_from: Data od
            date_to: Data do
            search: Szukaj w transkrypcji
            page: Numer strony (od 1)
            per_page: Wyników na stronę

        Returns:
            Tuple (lista_wizyt, całkowita_liczba, liczba_stron)
        """
        offset = (page - 1) * per_page
        visits, total = self.visit_repo.find_all(
            patient_id=patient_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
            search=search,
            limit=per_page,
            offset=offset
        )

        total_pages = (total + per_page - 1) // per_page
        return visits, total, total_pages

    def update_visit_status(self, visit_id: str, status: VisitStatus) -> Optional[Visit]:
        """Aktualizuje status wizyty."""
        visit = self.visit_repo.get_by_id(visit_id)
        if not visit:
            return None

        visit.status = status
        visit.updated_at = datetime.now()
        return self.visit_repo.save(visit)

    def complete_visit(self, visit_id: str) -> Optional[Visit]:
        """Oznacza wizytę jako zakończoną."""
        return self.update_visit_status(visit_id, VisitStatus.COMPLETED)

    def delete_visit(self, visit_id: str) -> bool:
        """Usuwa wizytę."""
        return self.visit_repo.delete(visit_id)

    def get_recent_visits(self, limit: int = 10) -> List[Visit]:
        """Pobiera ostatnie wizyty."""
        return self.visit_repo.get_recent(limit)

    def get_statistics(self) -> Dict[str, Any]:
        """Zwraca statystyki wizyt."""
        return self.visit_repo.get_statistics()

    # === Operacje na pacjentach ===

    def _merge_patient_fields(
        self,
        patient: Patient,
        display_name: Optional[str] = None,
        identifier: Optional[str] = None,
        birth_date: Optional[str] = None,
        sex: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
    ) -> bool:
        """Uzupelnia dane pacjenta bez nadpisywania pustymi wartosciami."""
        changed = False

        def _set(attr: str, value: Optional[str]):
            nonlocal changed
            if value is None:
                return
            value = value.strip()
            if not value:
                return
            if getattr(patient, attr, "") != value:
                setattr(patient, attr, value)
                changed = True

        _set("display_name", display_name)
        _set("identifier", identifier)
        _set("birth_date", birth_date)
        _set("sex", sex)
        _set("address", address)
        _set("phone", phone)
        _set("email", email)

        # Aktualizuj hash identyfikatora jesli mamy identyfikator
        if identifier:
            try:
                new_hash = Patient.hash_identifier(identifier)
                if patient.identifier_hash != new_hash:
                    patient.identifier_hash = new_hash
                    changed = True
            except Exception:
                pass

        return changed

    def get_or_create_patient(
        self,
        display_name: str,
        identifier: Optional[str] = None,
        birth_date: str = "",
        sex: str = "",
        address: str = "",
        phone: str = "",
        email: str = "",
    ) -> Patient:
        """Pobiera lub tworzy pacjenta oraz uzupelnia dane."""
        patient = self.patient_repo.get_or_create(display_name, identifier)
        if self._merge_patient_fields(
            patient,
            display_name=display_name,
            identifier=identifier,
            birth_date=birth_date,
            sex=sex,
            address=address,
            phone=phone,
            email=email,
        ):
            patient = self.patient_repo.save(patient)
        return patient

    def get_patients(
        self,
        search: Optional[str] = None,
        page: int = 1,
        per_page: int = 20
    ) -> Tuple[List[Patient], int]:
        """Pobiera listę pacjentów."""
        offset = (page - 1) * per_page
        return self.patient_repo.find_all(search=search, limit=per_page, offset=offset)

    def get_recent_patients(self, limit: int = 10) -> List[Patient]:
        """Pobiera ostatnio dodanych pacjentów."""
        return self.patient_repo.get_recent(limit)

    def get_patient_visits(self, patient_id: int) -> List[Visit]:
        """Pobiera wizyty pacjenta."""
        return self.visit_repo.get_patient_visits(patient_id)


# Singleton instance
_visit_service: Optional[VisitService] = None


def get_visit_service() -> VisitService:
    """Zwraca singleton VisitService."""
    global _visit_service
    if _visit_service is None:
        _visit_service = VisitService()
    return _visit_service
