"""Model pacjenta."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import hashlib


@dataclass
class Patient:
    """
    Model pacjenta.

    Przechowuje minimalne dane zgodnie z RODO.
    Pełne dane osobowe mogą być zaszyfrowane w metadata_encrypted.
    """
    id: Optional[int] = None
    display_name: str = ""  # "Jan K." - do wyświetlania
    identifier_hash: Optional[str] = None  # SHA256(PESEL) - do deduplikacji
    notes: str = ""
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

    @staticmethod
    def hash_identifier(identifier: str) -> str:
        """Tworzy hash z identyfikatora (np. PESEL) dla deduplikacji."""
        return hashlib.sha256(identifier.encode()).hexdigest()

    @classmethod
    def create_anonymous(cls) -> 'Patient':
        """Tworzy anonimowego pacjenta (gdy nie chcemy zapisywać danych)."""
        return cls(display_name="Pacjent anonimowy")

    def to_dict(self) -> dict:
        """Konwertuje do słownika (do zapisu w DB)."""
        return {
            'id': self.id,
            'display_name': self.display_name,
            'identifier_hash': self.identifier_hash,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Patient':
        """Tworzy obiekt z słownika (z DB)."""
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return cls(
            id=data.get('id'),
            display_name=data.get('display_name', ''),
            identifier_hash=data.get('identifier_hash'),
            notes=data.get('notes', ''),
            created_at=created_at
        )
