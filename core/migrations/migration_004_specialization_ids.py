"""
Migration 004: Zmiana specialization_id na specialization_ids (multi-select).

Dodaje kolumnę specialization_ids (JSON array) i migruje dane z specialization_id.
"""

import sqlite3
from .migrator import Migration


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    """Dodaje kolumnę jeśli nie istnieje."""
    existing = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def up(conn: sqlite3.Connection) -> None:
    """Wykonuje migrację."""
    # 1. Dodaj nową kolumnę specialization_ids
    _add_column_if_missing(conn, "visits", "specialization_ids", "TEXT DEFAULT '[1]'")

    # 2. Migruj dane z starej kolumny (jeśli istnieje i ma wartości)
    existing = [row["name"] for row in conn.execute("PRAGMA table_info(visits)").fetchall()]
    if "specialization_id" in existing:
        # Konwertuj int na JSON array: 1 -> "[1]", 2 -> "[2]", etc.
        conn.execute("""
            UPDATE visits
            SET specialization_ids = '[' || COALESCE(specialization_id, 1) || ']'
            WHERE specialization_ids IS NULL OR specialization_ids = '[1]'
        """)

    conn.commit()


migration = Migration(
    version=4,
    name="specialization_ids_multiselect",
    up=up,
)
