"""Repozytoria do obsługi danych."""

from .patient_repo import PatientRepository
from .visit_repo import VisitRepository

__all__ = ['PatientRepository', 'VisitRepository']
