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
        visit = Visit(
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

        # Dodaj diagnozy
        for i, diag in enumerate(diagnoses):
            diagnosis = VisitDiagnosis(
                icd10_code=diag.get('kod', ''),
                icd10_name=diag.get('nazwa', ''),
                location=diag.get('zab', diag.get('location', '')),
                description=diag.get('opis_tekstowy', diag.get('description', '')),
                display_order=i
            )
            visit.add_diagnosis(diagnosis)

        # Dodaj procedury
        for i, proc in enumerate(procedures):
            procedure = VisitProcedure(
                procedure_code=proc.get('kod', ''),
                procedure_name=proc.get('nazwa', ''),
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

    def get_or_create_patient(
        self,
        display_name: str,
        identifier: Optional[str] = None
    ) -> Patient:
        """Pobiera lub tworzy pacjenta."""
        return self.patient_repo.get_or_create(display_name, identifier)

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
