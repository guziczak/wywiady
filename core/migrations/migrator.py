"""
System migracji bazy danych.

Automatycznie wykonuje migracje przy starcie aplikacji.
Śledzi wersję schematu w tabeli `schema_migrations`.
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Callable
import importlib
import pkgutil

DB_PATH = Path(__file__).parent.parent.parent / "medical_knowledge.db"


class Migration:
    """Reprezentuje pojedynczą migrację."""

    def __init__(self, version: int, name: str, up: Callable[[sqlite3.Connection], None]):
        self.version = version
        self.name = name
        self.up = up

    def __repr__(self):
        return f"Migration({self.version}, '{self.name}')"


class Migrator:
    """Zarządza migracjami bazy danych."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.migrations: List[Migration] = []
        self._load_migrations()

    def _get_conn(self) -> sqlite3.Connection:
        """Tworzy połączenie z bazą."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_migrations_table(self, conn: sqlite3.Connection) -> None:
        """Tworzy tabelę migracji jeśli nie istnieje."""
        conn.execute('''
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

    def _get_applied_versions(self, conn: sqlite3.Connection) -> List[int]:
        """Zwraca listę zastosowanych wersji migracji."""
        cursor = conn.execute('SELECT version FROM schema_migrations ORDER BY version')
        return [row['version'] for row in cursor.fetchall()]

    def _mark_as_applied(self, conn: sqlite3.Connection, migration: Migration) -> None:
        """Oznacza migrację jako zastosowaną."""
        conn.execute(
            'INSERT INTO schema_migrations (version, name) VALUES (?, ?)',
            (migration.version, migration.name)
        )
        conn.commit()

    def _load_migrations(self) -> None:
        """Ładuje wszystkie dostępne migracje z modułów."""
        from . import migration_001_visits
        from . import migration_002_visit_details
        from . import migration_003_patient_details

        # Rejestruj migracje
        self.migrations = [
            migration_001_visits.migration,
            migration_002_visit_details.migration,
            migration_003_patient_details.migration,
        ]

        # Sortuj po wersji
        self.migrations.sort(key=lambda m: m.version)

    def get_pending_migrations(self) -> List[Migration]:
        """Zwraca listę migracji do wykonania."""
        with self._get_conn() as conn:
            self._ensure_migrations_table(conn)
            applied = set(self._get_applied_versions(conn))
            return [m for m in self.migrations if m.version not in applied]

    def migrate(self) -> List[Migration]:
        """
        Wykonuje wszystkie oczekujące migracje.

        Returns:
            Lista zastosowanych migracji.
        """
        applied = []

        with self._get_conn() as conn:
            self._ensure_migrations_table(conn)
            applied_versions = set(self._get_applied_versions(conn))

            for migration in self.migrations:
                if migration.version in applied_versions:
                    continue

                print(f"[MIGRATION] Applying: {migration.version} - {migration.name}", flush=True)

                try:
                    migration.up(conn)
                    self._mark_as_applied(conn, migration)
                    applied.append(migration)
                    print(f"[MIGRATION] Success: {migration.name}", flush=True)
                except Exception as e:
                    print(f"[MIGRATION] Failed: {migration.name} - {e}", flush=True)
                    raise

        return applied

    def get_current_version(self) -> int:
        """Zwraca aktualną wersję schematu."""
        with self._get_conn() as conn:
            self._ensure_migrations_table(conn)
            cursor = conn.execute('SELECT MAX(version) as v FROM schema_migrations')
            row = cursor.fetchone()
            return row['v'] if row and row['v'] else 0


def run_migrations(db_path: Path = DB_PATH) -> List[Migration]:
    """
    Uruchamia migracje (do wywołania przy starcie aplikacji).

    Returns:
        Lista zastosowanych migracji.
    """
    migrator = Migrator(db_path)

    pending = migrator.get_pending_migrations()
    if pending:
        print(f"[MIGRATION] Found {len(pending)} pending migration(s)", flush=True)
        return migrator.migrate()
    else:
        print(f"[MIGRATION] Database is up to date (version {migrator.get_current_version()})", flush=True)
        return []
