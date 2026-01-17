"""Bazowe klasy dla repozytoriów."""

import sqlite3
from pathlib import Path
from typing import Optional, List, Any
from abc import ABC, abstractmethod

DB_PATH = Path(__file__).parent.parent.parent / "medical_knowledge.db"


class BaseRepository(ABC):
    """Bazowa klasa repozytorium."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def _get_conn(self) -> sqlite3.Connection:
        """Tworzy połączenie z bazą."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Włącz foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Wykonuje zapytanie i zwraca kursor."""
        with self._get_conn() as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor

    def _fetch_one(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Pobiera jeden rekord."""
        with self._get_conn() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchone()

    def _fetch_all(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Pobiera wszystkie rekordy."""
        with self._get_conn() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall()
