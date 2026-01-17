"""
Migration 001: Tabele dla historii wizyt.

Tworzy tabele:
- patients: Dane pacjentów (RODO-compliant)
- visits: Wizyty medyczne
- visit_diagnoses: Diagnozy przypisane do wizyt
- visit_procedures: Procedury wykonane podczas wizyt
"""

import sqlite3
from .migrator import Migration


def up(conn: sqlite3.Connection) -> None:
    """Wykonuje migrację."""
    cursor = conn.cursor()

    # 1. Tabela pacjentów
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name TEXT NOT NULL,
            identifier_hash TEXT UNIQUE,
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 2. Tabela wizyt
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS visits (
            id TEXT PRIMARY KEY,
            patient_id INTEGER REFERENCES patients(id) ON DELETE SET NULL,
            patient_name TEXT DEFAULT '',
            specialization_id INTEGER REFERENCES specializations(id) DEFAULT 1,
            visit_date TIMESTAMP NOT NULL,
            transcript TEXT DEFAULT '',
            audio_path TEXT,
            status TEXT CHECK(status IN ('draft', 'completed')) DEFAULT 'draft',
            model_used TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 3. Tabela diagnoz
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS visit_diagnoses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visit_id TEXT NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
            icd10_code TEXT NOT NULL,
            icd10_name TEXT DEFAULT '',
            location TEXT DEFAULT '',
            description TEXT DEFAULT '',
            display_order INTEGER DEFAULT 0
        )
    ''')

    # 4. Tabela procedur
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS visit_procedures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visit_id TEXT NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
            procedure_code TEXT NOT NULL,
            procedure_name TEXT DEFAULT '',
            location TEXT DEFAULT '',
            description TEXT DEFAULT '',
            display_order INTEGER DEFAULT 0
        )
    ''')

    # 5. Indeksy dla wydajności
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_visits_patient ON visits(patient_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_visits_date ON visits(visit_date DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_visits_status ON visits(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_visit_diagnoses_visit ON visit_diagnoses(visit_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_visit_procedures_visit ON visit_procedures(visit_id)')

    # 6. Trigger do aktualizacji updated_at
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS update_visit_timestamp
        AFTER UPDATE ON visits
        FOR EACH ROW
        BEGIN
            UPDATE visits SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END
    ''')

    conn.commit()


# Eksportuj obiekt migracji
migration = Migration(
    version=1,
    name="create_visits_tables",
    up=up
)
