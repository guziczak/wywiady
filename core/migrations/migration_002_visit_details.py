"""
Migration 002: Dodanie rozszerzonych pól wizyty.

Uzupełnia tabelę visits o dane pacjenta oraz sekcje medyczne (SOAP/zalecenia).
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
    columns = [
        ("patient_identifier", "TEXT DEFAULT ''"),
        ("patient_birth_date", "TEXT DEFAULT ''"),
        ("patient_sex", "TEXT DEFAULT ''"),
        ("patient_address", "TEXT DEFAULT ''"),
        ("patient_phone", "TEXT DEFAULT ''"),
        ("patient_email", "TEXT DEFAULT ''"),
        ("subjective", "TEXT DEFAULT ''"),
        ("objective", "TEXT DEFAULT ''"),
        ("assessment", "TEXT DEFAULT ''"),
        ("plan", "TEXT DEFAULT ''"),
        ("recommendations", "TEXT DEFAULT ''"),
        ("medications", "TEXT DEFAULT ''"),
        ("tests_ordered", "TEXT DEFAULT ''"),
        ("tests_results", "TEXT DEFAULT ''"),
        ("referrals", "TEXT DEFAULT ''"),
        ("certificates", "TEXT DEFAULT ''"),
        ("additional_notes", "TEXT DEFAULT ''"),
    ]

    for column, definition in columns:
        _add_column_if_missing(conn, "visits", column, definition)

    conn.commit()


migration = Migration(
    version=2,
    name="add_visit_details_fields",
    up=up,
)
