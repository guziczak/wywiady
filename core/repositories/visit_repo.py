"""Repozytorium wizyt."""

from typing import Optional, List, Tuple
from datetime import datetime, date

from .base import BaseRepository
from core.models import Visit, VisitDiagnosis, VisitProcedure, VisitStatus


class VisitRepository(BaseRepository):
    """Repozytorium do zarządzania wizytami."""

    def save(self, visit: Visit) -> Visit:
        """
        Zapisuje wizytę wraz z diagnozami i procedurami.

        Returns:
            Wizyta z ustawionym ID.
        """
        with self._get_conn() as conn:
            # Sprawdź czy istnieje
            existing = conn.execute(
                'SELECT id FROM visits WHERE id = ?',
                (visit.id,)
            ).fetchone()

            if existing:
                # UPDATE
                conn.execute('''
                    UPDATE visits
                    SET patient_id = ?, patient_name = ?, specialization_id = ?,
                        visit_date = ?, transcript = ?, audio_path = ?,
                        status = ?, model_used = ?, updated_at = ?
                    WHERE id = ?
                ''', (
                    visit.patient_id,
                    visit.patient_name,
                    visit.specialization_id,
                    visit.visit_date.isoformat() if visit.visit_date else None,
                    visit.transcript,
                    visit.audio_path,
                    str(visit.status),
                    visit.model_used,
                    datetime.now().isoformat(),
                    visit.id
                ))

                # Usuń stare diagnozy i procedury
                conn.execute('DELETE FROM visit_diagnoses WHERE visit_id = ?', (visit.id,))
                conn.execute('DELETE FROM visit_procedures WHERE visit_id = ?', (visit.id,))
            else:
                # INSERT
                conn.execute('''
                    INSERT INTO visits (
                        id, patient_id, patient_name, specialization_id,
                        visit_date, transcript, audio_path, status, model_used
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    visit.id,
                    visit.patient_id,
                    visit.patient_name,
                    visit.specialization_id,
                    visit.visit_date.isoformat() if visit.visit_date else None,
                    visit.transcript,
                    visit.audio_path,
                    str(visit.status),
                    visit.model_used
                ))

            # Zapisz diagnozy
            for diag in visit.diagnoses:
                diag.visit_id = visit.id
                conn.execute('''
                    INSERT INTO visit_diagnoses (
                        visit_id, icd10_code, icd10_name, location, description, display_order
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    diag.visit_id,
                    diag.icd10_code,
                    diag.icd10_name,
                    diag.location,
                    diag.description,
                    diag.display_order
                ))

            # Zapisz procedury
            for proc in visit.procedures:
                proc.visit_id = visit.id
                conn.execute('''
                    INSERT INTO visit_procedures (
                        visit_id, procedure_code, procedure_name, location, description, display_order
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    proc.visit_id,
                    proc.procedure_code,
                    proc.procedure_name,
                    proc.location,
                    proc.description,
                    proc.display_order
                ))

            conn.commit()
            return visit

    def get_by_id(self, visit_id: str) -> Optional[Visit]:
        """Pobiera wizytę po ID wraz z diagnozami i procedurami."""
        with self._get_conn() as conn:
            # Pobierz wizytę
            row = conn.execute(
                'SELECT * FROM visits WHERE id = ?',
                (visit_id,)
            ).fetchone()

            if not row:
                return None

            visit = self._row_to_visit(dict(row))

            # Pobierz diagnozy
            diag_rows = conn.execute(
                'SELECT * FROM visit_diagnoses WHERE visit_id = ? ORDER BY display_order',
                (visit_id,)
            ).fetchall()
            visit.diagnoses = [VisitDiagnosis.from_dict(dict(r)) for r in diag_rows]

            # Pobierz procedury
            proc_rows = conn.execute(
                'SELECT * FROM visit_procedures WHERE visit_id = ? ORDER BY display_order',
                (visit_id,)
            ).fetchall()
            visit.procedures = [VisitProcedure.from_dict(dict(r)) for r in proc_rows]

            return visit

    def find_all(
        self,
        patient_id: Optional[int] = None,
        status: Optional[VisitStatus] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Visit], int]:
        """
        Pobiera listę wizyt z filtrowaniem i paginacją.

        Args:
            patient_id: Filtruj po pacjencie
            status: Filtruj po statusie
            date_from: Data od
            date_to: Data do
            search: Szukaj w transkrypcji lub nazwie pacjenta
            limit: Maksymalna liczba wyników
            offset: Przesunięcie

        Returns:
            Tuple (lista_wizyt, całkowita_liczba)
        """
        conditions = []
        params = []

        if patient_id is not None:
            conditions.append('v.patient_id = ?')
            params.append(patient_id)

        if status is not None:
            conditions.append('v.status = ?')
            params.append(str(status))

        if date_from is not None:
            conditions.append('DATE(v.visit_date) >= ?')
            params.append(date_from.isoformat())

        if date_to is not None:
            conditions.append('DATE(v.visit_date) <= ?')
            params.append(date_to.isoformat())

        if search:
            conditions.append('(v.transcript LIKE ? OR v.patient_name LIKE ?)')
            params.extend([f'%{search}%', f'%{search}%'])

        where_clause = ' AND '.join(conditions) if conditions else '1=1'

        with self._get_conn() as conn:
            # Całkowita liczba
            count_row = conn.execute(
                f'SELECT COUNT(*) as cnt FROM visits v WHERE {where_clause}',
                tuple(params)
            ).fetchone()
            total = count_row['cnt'] if count_row else 0

            # Pobierz wizyty
            query = f'''
                SELECT v.*,
                    (SELECT GROUP_CONCAT(icd10_code, ', ')
                     FROM visit_diagnoses vd
                     WHERE vd.visit_id = v.id
                     ORDER BY vd.display_order
                     LIMIT 3) as diagnoses_preview
                FROM visits v
                WHERE {where_clause}
                ORDER BY v.visit_date DESC
                LIMIT ? OFFSET ?
            '''
            params.extend([limit, offset])

            rows = conn.execute(query, tuple(params)).fetchall()
            visits = []

            for row in rows:
                visit = self._row_to_visit(dict(row))
                # Dla listy nie ładujemy pełnych diagnoz/procedur
                visits.append(visit)

            return visits, total

    def delete(self, visit_id: str) -> bool:
        """
        Usuwa wizytę (CASCADE usuwa też diagnozy i procedury).

        Returns:
            True jeśli usunięto.
        """
        with self._get_conn() as conn:
            cursor = conn.execute('DELETE FROM visits WHERE id = ?', (visit_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_patient_visits(self, patient_id: int, limit: int = 20) -> List[Visit]:
        """Pobiera wizyty pacjenta."""
        visits, _ = self.find_all(patient_id=patient_id, limit=limit)
        return visits

    def get_recent(self, limit: int = 10) -> List[Visit]:
        """Pobiera ostatnie wizyty."""
        visits, _ = self.find_all(limit=limit)
        return visits

    def get_statistics(self) -> dict:
        """Zwraca statystyki wizyt."""
        with self._get_conn() as conn:
            total = conn.execute('SELECT COUNT(*) as cnt FROM visits').fetchone()['cnt']
            completed = conn.execute(
                "SELECT COUNT(*) as cnt FROM visits WHERE status = 'completed'"
            ).fetchone()['cnt']
            drafts = conn.execute(
                "SELECT COUNT(*) as cnt FROM visits WHERE status = 'draft'"
            ).fetchone()['cnt']

            # Wizyty z ostatniego tygodnia
            recent = conn.execute('''
                SELECT COUNT(*) as cnt FROM visits
                WHERE visit_date >= datetime('now', '-7 days')
            ''').fetchone()['cnt']

            return {
                'total': total,
                'completed': completed,
                'drafts': drafts,
                'last_week': recent
            }

    def _row_to_visit(self, row: dict) -> Visit:
        """Konwertuje wiersz DB do obiektu Visit."""
        visit_date = row.get('visit_date')
        if isinstance(visit_date, str):
            visit_date = datetime.fromisoformat(visit_date)

        created_at = row.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = row.get('updated_at')
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        status = row.get('status', 'draft')
        if isinstance(status, str):
            status = VisitStatus(status)

        return Visit(
            id=row['id'],
            patient_id=row.get('patient_id'),
            patient_name=row.get('patient_name', ''),
            specialization_id=row.get('specialization_id', 1),
            visit_date=visit_date or datetime.now(),
            transcript=row.get('transcript', ''),
            audio_path=row.get('audio_path'),
            status=status,
            model_used=row.get('model_used', ''),
            diagnoses=[],  # Ładowane osobno gdy potrzebne
            procedures=[],
            created_at=created_at or datetime.now(),
            updated_at=updated_at or datetime.now()
        )
