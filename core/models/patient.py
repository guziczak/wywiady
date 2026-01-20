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
    identifier: str = ""  # PESEL lub inny identyfikator (opcjonalnie)
    identifier_hash: Optional[str] = None  # SHA256(PESEL) - do deduplikacji
    birth_date: str = ""
    sex: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    notes: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()

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
            'identifier': self.identifier,
            'identifier_hash': self.identifier_hash,
            'birth_date': self.birth_date,
            'sex': self.sex,
            'address': self.address,
            'phone': self.phone,
            'email': self.email,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Patient':
        """Tworzy obiekt z słownika (z DB)."""
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        updated_at = data.get('updated_at')
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        return cls(
            id=data.get('id'),
            display_name=data.get('display_name', ''),
            identifier=data.get('identifier', ''),
            identifier_hash=data.get('identifier_hash'),
            birth_date=data.get('birth_date', ''),
            sex=data.get('sex', ''),
            address=data.get('address', ''),
            phone=data.get('phone', ''),
            email=data.get('email', ''),
            notes=data.get('notes', ''),
            created_at=created_at,
            updated_at=updated_at
        )
