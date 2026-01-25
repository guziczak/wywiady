"""Modele wizyty i powiązanych encji."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import uuid

from .enums import VisitStatus


@dataclass
class VisitDiagnosis:
    """Diagnoza przypisana do wizyty."""
    id: Optional[int] = None
    visit_id: Optional[str] = None
    icd10_code: str = ""
    icd10_name: str = ""  # Nazwa kodu ICD-10
    location: str = ""  # Lokalizacja (np. "16" dla zęba, "Oko lewe")
    description: str = ""  # Opis kliniczny
    display_order: int = 0

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'visit_id': self.visit_id,
            'icd10_code': self.icd10_code,
            'icd10_name': self.icd10_name,
            'location': self.location,
            'description': self.description,
            'display_order': self.display_order
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'VisitDiagnosis':
        return cls(
            id=data.get('id'),
            visit_id=data.get('visit_id'),
            icd10_code=data.get('icd10_code', data.get('kod', '')),
            icd10_name=data.get('icd10_name', data.get('nazwa', '')),
            location=data.get('location', data.get('zab', '')),
            description=data.get('description', data.get('opis_tekstowy', '')),
            display_order=data.get('display_order', 0)
        )

    @classmethod
    def from_llm_output(cls, data: dict, order: int = 0) -> 'VisitDiagnosis':
        """Tworzy z outputu LLM (format z generate_description)."""
        return cls(
            icd10_code=data.get('kod', ''),
            icd10_name=data.get('nazwa', ''),
            location=data.get('zab', ''),
            description=data.get('opis_tekstowy', ''),
            display_order=order
        )


@dataclass
class VisitProcedure:
    """Procedura wykonana podczas wizyty."""
    id: Optional[int] = None
    visit_id: Optional[str] = None
    procedure_code: str = ""
    procedure_name: str = ""  # Nazwa procedury
    location: str = ""  # Lokalizacja
    description: str = ""  # Opis wykonania
    display_order: int = 0

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'visit_id': self.visit_id,
            'procedure_code': self.procedure_code,
            'procedure_name': self.procedure_name,
            'location': self.location,
            'description': self.description,
            'display_order': self.display_order
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'VisitProcedure':
        return cls(
            id=data.get('id'),
            visit_id=data.get('visit_id'),
            procedure_code=data.get('procedure_code', data.get('kod', '')),
            procedure_name=data.get('procedure_name', data.get('nazwa', '')),
            location=data.get('location', data.get('zab', '')),
            description=data.get('description', data.get('opis_tekstowy', '')),
            display_order=data.get('display_order', 0)
        )

    @classmethod
    def from_llm_output(cls, data: dict, order: int = 0) -> 'VisitProcedure':
        """Tworzy z outputu LLM (format z generate_description)."""
        return cls(
            procedure_code=data.get('kod', ''),
            procedure_name=data.get('nazwa', ''),
            location=data.get('zab', ''),
            description=data.get('opis_tekstowy', ''),
            display_order=order
        )


@dataclass
class Visit:
    """
    Model wizyty medycznej.

    Zawiera transkrypcję, diagnozy i procedury.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    patient_id: Optional[int] = None
    patient_name: str = ""  # Denormalizowane dla szybkiego wyświetlania
    patient_identifier: str = ""  # PESEL lub inny identyfikator
    patient_birth_date: str = ""
    patient_sex: str = ""
    patient_address: str = ""
    patient_phone: str = ""
    patient_email: str = ""
    specialization_ids: List[int] = field(default_factory=lambda: [1])  # Multi-select specjalizacji
    visit_date: datetime = field(default_factory=datetime.now)
    transcript: str = ""
    subjective: str = ""  # Wywiad (S) - opcjonalnie, jeśli różne od transkrypcji
    objective: str = ""  # Badanie przedmiotowe (O)
    assessment: str = ""  # Ocena/rozpoznanie opisowe (A)
    plan: str = ""  # Plan leczenia (P)
    recommendations: str = ""
    medications: str = ""
    tests_ordered: str = ""
    tests_results: str = ""
    referrals: str = ""
    certificates: str = ""
    additional_notes: str = ""
    audio_path: Optional[str] = None
    status: VisitStatus = VisitStatus.DRAFT
    model_used: str = ""  # "Claude" / "Gemini"
    diagnoses: List[VisitDiagnosis] = field(default_factory=list)
    procedures: List[VisitProcedure] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def add_diagnosis(self, diagnosis: VisitDiagnosis) -> None:
        """Dodaje diagnozę do wizyty."""
        diagnosis.visit_id = self.id
        diagnosis.display_order = len(self.diagnoses)
        self.diagnoses.append(diagnosis)

    def add_procedure(self, procedure: VisitProcedure) -> None:
        """Dodaje procedurę do wizyty."""
        procedure.visit_id = self.id
        procedure.display_order = len(self.procedures)
        self.procedures.append(procedure)

    def complete(self) -> None:
        """Oznacza wizytę jako zakończoną."""
        self.status = VisitStatus.COMPLETED
        self.updated_at = datetime.now()

    def get_diagnoses_summary(self, max_codes: int = 3) -> str:
        """Zwraca skrócone podsumowanie diagnoz (do listy)."""
        codes = [d.icd10_code for d in self.diagnoses[:max_codes]]
        if len(self.diagnoses) > max_codes:
            codes.append(f"+{len(self.diagnoses) - max_codes}")
        return ", ".join(codes) if codes else "-"

    def to_dict(self) -> dict:
        """Konwertuje do słownika (do zapisu w DB)."""
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'patient_name': self.patient_name,
            'patient_identifier': self.patient_identifier,
            'patient_birth_date': self.patient_birth_date,
            'patient_sex': self.patient_sex,
            'patient_address': self.patient_address,
            'patient_phone': self.patient_phone,
            'patient_email': self.patient_email,
            'specialization_ids': self.specialization_ids,
            'visit_date': self.visit_date.isoformat() if self.visit_date else None,
            'transcript': self.transcript,
            'subjective': self.subjective,
            'objective': self.objective,
            'assessment': self.assessment,
            'plan': self.plan,
            'recommendations': self.recommendations,
            'medications': self.medications,
            'tests_ordered': self.tests_ordered,
            'tests_results': self.tests_results,
            'referrals': self.referrals,
            'certificates': self.certificates,
            'additional_notes': self.additional_notes,
            'audio_path': self.audio_path,
            'status': str(self.status),
            'model_used': self.model_used,
            'diagnoses': [d.to_dict() for d in self.diagnoses],
            'procedures': [p.to_dict() for p in self.procedures],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Visit':
        """Tworzy obiekt z słownika (z DB)."""
        visit_date = data.get('visit_date')
        if isinstance(visit_date, str):
            visit_date = datetime.fromisoformat(visit_date)

        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = data.get('updated_at')
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        status = data.get('status', 'draft')
        if isinstance(status, str):
            status = VisitStatus(status)

        diagnoses = [
            VisitDiagnosis.from_dict(d) if isinstance(d, dict) else d
            for d in data.get('diagnoses', [])
        ]

        procedures = [
            VisitProcedure.from_dict(p) if isinstance(p, dict) else p
            for p in data.get('procedures', [])
        ]

        # Obsłuż oba formaty: stary (int) i nowy (list)
        spec_ids = data.get('specialization_ids')
        if spec_ids is None:
            # Stary format - konwertuj int na listę
            old_id = data.get('specialization_id', 1)
            spec_ids = [old_id] if old_id else [1]
        elif isinstance(spec_ids, int):
            spec_ids = [spec_ids]

        return cls(
            id=data.get('id', str(uuid.uuid4())),
            patient_id=data.get('patient_id'),
            patient_name=data.get('patient_name', ''),
            patient_identifier=data.get('patient_identifier', ''),
            patient_birth_date=data.get('patient_birth_date', ''),
            patient_sex=data.get('patient_sex', ''),
            patient_address=data.get('patient_address', ''),
            patient_phone=data.get('patient_phone', ''),
            patient_email=data.get('patient_email', ''),
            specialization_ids=spec_ids,
            visit_date=visit_date or datetime.now(),
            transcript=data.get('transcript', ''),
            subjective=data.get('subjective', ''),
            objective=data.get('objective', ''),
            assessment=data.get('assessment', ''),
            plan=data.get('plan', ''),
            recommendations=data.get('recommendations', ''),
            medications=data.get('medications', ''),
            tests_ordered=data.get('tests_ordered', ''),
            tests_results=data.get('tests_results', ''),
            referrals=data.get('referrals', ''),
            certificates=data.get('certificates', ''),
            additional_notes=data.get('additional_notes', ''),
            audio_path=data.get('audio_path'),
            status=status,
            model_used=data.get('model_used', ''),
            diagnoses=diagnoses,
            procedures=procedures,
            created_at=created_at or datetime.now(),
            updated_at=updated_at or datetime.now()
        )

    @classmethod
    def from_llm_result(
        cls,
        transcript: str,
        llm_result: dict,
        model_used: str,
        patient_id: Optional[int] = None,
        patient_name: str = ""
    ) -> 'Visit':
        """
        Tworzy wizytę z wyniku LLM (generate_description).

        Args:
            transcript: Transkrypcja wywiadu
            llm_result: Wynik z LLMService.generate_description()
            model_used: Nazwa użytego modelu
            patient_id: ID pacjenta (opcjonalnie)
            patient_name: Nazwa pacjenta do wyświetlania
        """
        visit = cls(
            transcript=transcript,
            model_used=model_used,
            patient_id=patient_id,
            patient_name=patient_name
        )

        # Parsuj diagnozy
        for i, diag_data in enumerate(llm_result.get('diagnozy', [])):
            diagnosis = VisitDiagnosis.from_llm_output(diag_data, order=i)
            visit.add_diagnosis(diagnosis)

        # Parsuj procedury
        for i, proc_data in enumerate(llm_result.get('procedury', [])):
            procedure = VisitProcedure.from_llm_output(proc_data, order=i)
            visit.add_procedure(procedure)

        return visit

    def to_json_export(self) -> dict:
        """Format do eksportu JSON (kopiowanie do schowka)."""
        return {
            'diagnozy': [
                {
                    'kod': d.icd10_code,
                    'nazwa': d.icd10_name,
                    'zab': d.location,
                    'opis_tekstowy': d.description
                }
                for d in self.diagnoses
            ],
            'procedury': [
                {
                    'kod': p.procedure_code,
                    'nazwa': p.procedure_name,
                    'zab': p.location,
                    'opis_tekstowy': p.description
                }
                for p in self.procedures
            ]
        }
