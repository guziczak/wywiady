import asyncio
import json
import sqlite3
from pathlib import Path
from typing import List, Dict

# Imports from app
import sys
sys.path.append(str(Path(__file__).parent.parent))

from core.llm_service import LLMService
from core.config_manager import ConfigManager

DB_PATH = Path(__file__).parent.parent / "medical_knowledge.db"

SPECIALIZATIONS = [
    ("Kardiologia", 2),
    ("Okulistyka", 3),
    ("Ortopedia", 4),
    ("Chirurgia Ogólna", 5),
    ("Ginekologia", 6),
    ("Laryngologia", 7),
    ("Neurologia", 8),
    ("Urologia", 9),
    ("Dermatologia", 10),
    ("Psychiatria", 11)
]

async def generate_procedures(llm: LLMService, config: dict, spec_name: str) -> List[Dict]:
    print(f"Generating procedures for {spec_name}...")
    
    prompt = f"""Jesteś ekspertem kodowania medycznego w Polsce (NFZ).
Twoim zadaniem jest stworzenie listy procedur medycznych wg klasyfikacji ICD-9 PL (Polska) dla specjalizacji: {spec_name}.

Wymagania:
1. Wypisz od 30 do 50 NAJCZĘSTSZYCH i KLUCZOWYCH procedur dla tej specjalizacji.
2. Użyj poprawnego formatu kodów ICD-9 PL (np. 89.52, 13.41).
3. Nazwy muszą być profesjonalne, medyczne, po polsku.
4. Przypisz kategorię (np. "Diagnostyka", "Zabiegi", "Operacje").

Odpowiedz TYLKO czystym JSONem (lista obiektów):
[
  {{"code": "89.52", "name": "Elektrokardiogram z 12 lub więcej odprowadzeniami", "category": "Diagnostyka"}},
  ...
]
"""
    # Używamy generate_description jako wrappera lub bezpośrednio _call_gemini
    # LLMService nie ma publicznej metody 'generate_raw', ale ma _call_gemini.
    # Użyjmy _call_gemini jeśli mamy klucz, lub fallback.
    
    api_key = config.get("api_key")
    if not api_key:
        print("Skipping - NO API KEY")
        return []

    try:
        response_text = llm._call_gemini(api_key, prompt)
        
        # Clean JSON
        cleaned = response_text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0]
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0]
            
        data = json.loads(cleaned)
        return data
    except Exception as e:
        print(f"Error generating for {spec_name}: {e}")
        return []

def save_to_db(procedures: List[Dict], spec_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Ensure spec exists
    # (Zakładamy że init_db stworzył 1,2,3... ale dodamy resztę)
    spec_name = [s[0] for s in SPECIALIZATIONS if s[1] == spec_id][0]
    slug = spec_name.lower().replace(" ", "_")
    c.execute("INSERT OR IGNORE INTO specializations (id, name, slug) VALUES (?, ?, ?)", (spec_id, spec_name, slug))
    
    count = 0
    for p in procedures:
        try:
            c.execute('''
                INSERT OR REPLACE INTO procedures (code, name, category, specialization_id)
                VALUES (?, ?, ?, ?)
            ''', (p['code'], p['name'], p.get('category', 'Inne'), spec_id))
            count += 1
        except Exception:
            pass
            
    conn.commit()
    conn.close()
    print(f"Saved {count} procedures for {spec_name}.")

async def main():
    config_mgr = ConfigManager()
    config = config_mgr.config
    
    # Convert dataclass to dict if needed, or access attributes
    # ConfigManager.config is AppConfig object.
    # LLMService expects dict usually or object. Let's pass config object but _call_gemini takes api_key string.
    
    # We need API key.
    api_key = config.api_key
    if not api_key:
        print("ERROR: API Key is missing in config.json. Please configure the app first.")
        return

    llm = LLMService()
    
    # Konwersja config na dict dla funkcji (jeśli potrzebne)
    conf_dict = {"api_key": api_key}

    for name, spec_id in SPECIALIZATIONS:
        procs = await generate_procedures(llm, conf_dict, name)
        if procs:
            save_to_db(procs, spec_id)
        # Mały delay żeby nie uderzyć w rate limit
        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())
