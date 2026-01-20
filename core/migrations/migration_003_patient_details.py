"""
Migration 003: Dodanie rozszerzonych pol pacjenta.

Uzupelnia tabele patients o dane kontaktowe i identyfikacyjne.
"""

import sqlite3
from .migrator import Migration


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    """Dodaje kolumne jesli nie istnieje."""
    existing = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def up(conn: sqlite3.Connection) -> None:
    """Wykonuje migracje."""
    columns = [
        ("identifier", "TEXT DEFAULT ''"),
        ("birth_date", "TEXT DEFAULT ''"),
        ("sex", "TEXT DEFAULT ''"),
        ("address", "TEXT DEFAULT ''"),
        ("phone", "TEXT DEFAULT ''"),
        ("email", "TEXT DEFAULT ''"),
        ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ]

    for column, definition in columns:
        _add_column_if_missing(conn, "patients", column, definition)

    conn.commit()


migration = Migration(
    version=3,
    name="add_patient_details_fields",
    up=up,
)
