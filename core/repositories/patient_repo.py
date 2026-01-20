"""Repozytorium pacjentów."""

from typing import Optional, List, Tuple
from datetime import datetime

from .base import BaseRepository
from core.models import Patient


class PatientRepository(BaseRepository):
    """Repozytorium do zarządzania pacjentami."""

    def save(self, patient: Patient) -> Patient:
        """
        Zapisuje pacjenta (INSERT lub UPDATE).

        Returns:
            Pacjent z ustawionym ID.
        """
        with self._get_conn() as conn:
            if patient.id:
                # UPDATE
                conn.execute('''
                    UPDATE patients
                    SET display_name = ?, identifier = ?, identifier_hash = ?, birth_date = ?,
                        sex = ?, address = ?, phone = ?, email = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (
                    patient.display_name,
                    patient.identifier,
                    patient.identifier_hash,
                    patient.birth_date,
                    patient.sex,
                    patient.address,
                    patient.phone,
                    patient.email,
                    patient.notes,
                    patient.id
                ))
            else:
                # INSERT
                cursor = conn.execute('''
                    INSERT INTO patients (
                        display_name, identifier, identifier_hash, birth_date, sex,
                        address, phone, email, notes, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    patient.display_name,
                    patient.identifier,
                    patient.identifier_hash,
                    patient.birth_date,
                    patient.sex,
                    patient.address,
                    patient.phone,
                    patient.email,
                    patient.notes
                ))
                patient.id = cursor.lastrowid

            conn.commit()
            return patient

    def get_by_id(self, patient_id: int) -> Optional[Patient]:
        """Pobiera pacjenta po ID."""
        row = self._fetch_one(
            'SELECT * FROM patients WHERE id = ?',
            (patient_id,)
        )
        return Patient.from_dict(dict(row)) if row else None

    def get_by_identifier(self, identifier_hash: str) -> Optional[Patient]:
        """Pobiera pacjenta po hashu identyfikatora (np. PESEL)."""
        row = self._fetch_one(
            'SELECT * FROM patients WHERE identifier_hash = ?',
            (identifier_hash,)
        )
        return Patient.from_dict(dict(row)) if row else None

    def find_all(
        self,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Patient], int]:
        """
        Pobiera listę pacjentów z paginacją.

        Args:
            search: Szukana fraza (w display_name)
            limit: Maksymalna liczba wyników
            offset: Przesunięcie (dla paginacji)

        Returns:
            Tuple (lista_pacjentów, całkowita_liczba)
        """
        base_query = 'FROM patients'
        params = []

        if search:
            base_query += ' WHERE display_name LIKE ?'
            params.append(f'%{search}%')

        # Pobierz całkowitą liczbę
        count_row = self._fetch_one(f'SELECT COUNT(*) as cnt {base_query}', tuple(params))
        total = count_row['cnt'] if count_row else 0

        # Pobierz dane
        query = f'SELECT * {base_query} ORDER BY display_name ASC LIMIT ? OFFSET ?'
        params.extend([limit, offset])

        rows = self._fetch_all(query, tuple(params))
        patients = [Patient.from_dict(dict(row)) for row in rows]

        return patients, total

    def delete(self, patient_id: int) -> bool:
        """
        Usuwa pacjenta.

        Returns:
            True jeśli usunięto, False jeśli nie znaleziono.
        """
        with self._get_conn() as conn:
            cursor = conn.execute('DELETE FROM patients WHERE id = ?', (patient_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_or_create(self, display_name: str, identifier: Optional[str] = None) -> Patient:
        """
        Pobiera istniejącego pacjenta lub tworzy nowego.

        Args:
            display_name: Nazwa do wyświetlania
            identifier: Identyfikator (np. PESEL) - opcjonalny

        Returns:
            Pacjent (istniejący lub nowy)
        """
        if identifier:
            identifier_hash = Patient.hash_identifier(identifier)
            existing = self.get_by_identifier(identifier_hash)
            if existing:
                return existing

            patient = Patient(
                display_name=display_name,
                identifier=identifier,
                identifier_hash=identifier_hash
            )
        else:
            patient = Patient(display_name=display_name)

        return self.save(patient)

    def get_recent(self, limit: int = 10) -> List[Patient]:
        """Pobiera ostatnio dodanych pacjentów."""
        rows = self._fetch_all(
            'SELECT * FROM patients ORDER BY created_at DESC LIMIT ?',
            (limit,)
        )
        return [Patient.from_dict(dict(row)) for row in rows]
