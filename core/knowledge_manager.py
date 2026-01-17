import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "medical_knowledge.db"

class KnowledgeManager:
    """Zarządza wiedzą medyczną (ICD-10, Procedury) w bazie SQLite."""

    def __init__(self):
        self.db_path = DB_PATH

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def get_specializations(self) -> List[Dict]:
        """Zwraca listę dostępnych specjalizacji."""
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT id, name, slug FROM specializations")
            return [{"id": row[0], "name": row[1], "slug": row[2]} for row in c.fetchall()]

    def get_context_for_specialization(self, spec_id: int) -> Dict:
        """Pobiera kody ICD-10 i Procedury dla danej specjalizacji (do promptu LLM)."""
        context = {
            "icd10": [],
            "procedures": []
        }
        
        with self._get_conn() as conn:
            c = conn.cursor()
            
            # 1. Pobierz ICD-10 przypisane do specjalizacji
            c.execute("SELECT code, description FROM icd10_codes WHERE specialization_id = ?", (spec_id,))
            context["icd10"] = [{"code": r[0], "desc": r[1]} for r in c.fetchall()]
            
            # 2. Pobierz procedury
            c.execute("SELECT code, name FROM procedures WHERE specialization_id = ?", (spec_id,))
            context["icd9"] = [{"code": r[0], "name": r[1]} for r in c.fetchall()]

        return context

    def export_to_json(self, output_path: str = "knowledge_dump.json"):
        """Eksportuje całą bazę do czytelnego JSONa."""
        data = {}
        
        # Pobierz metadane źródeł
        data["_meta"] = {
            "generated_at": str(datetime.now()),
            "sources": []
        }
        
        with self._get_conn() as conn:
            c = conn.cursor()
            # Utwórz tabelę jeśli nie istnieje (lazy migration)
            c.execute('''
                CREATE TABLE IF NOT EXISTS data_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    url TEXT,
                    description TEXT,
                    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Pobierz źródła
            c.execute("SELECT name, url, description, imported_at FROM data_sources")
            data["_meta"]["sources"] = [
                {"name": r[0], "url": r[1], "desc": r[2], "date": r[3]} 
                for r in c.fetchall()
            ]
        
        specs = self.get_specializations()
        for spec in specs:
            spec_name = spec["name"]
            ctx = self.get_context_for_specialization(spec["id"])
            data[spec_name] = ctx
            
        # Dodaj "Ogólne/Inne" (bez spec_id)
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT code, name FROM procedures WHERE specialization_id IS NULL")
            data["Ogólne"] = {
                "icd10": [], # Za dużo żeby dumpować wszystkie 23k
                "icd9": [{"code": r[0], "name": r[1]} for r in c.fetchall()]
            }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"Exported knowledge to {output_path}")

    def add_source(self, name: str, url: str, description: str):
        """Dodaje źródło danych."""
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO data_sources (name, url, description) VALUES (?, ?, ?)",
                (name, url, description)
            )
            conn.commit()

if __name__ == "__main__":
    km = KnowledgeManager()
    km.export_to_json()
