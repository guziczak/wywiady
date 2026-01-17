import pandas as pd
import sqlite3
import re
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "medical_knowledge.db"
XLS_PATH = Path(__file__).parent.parent / "data" / "icd9_official.xlsx"

# Mapowanie ID specjalizacji (z db_seed_procedures / db_init)
# 1: Stomatologia
# 2: Kardiologia
# 3: Okulistyka
# 4: Ortopedia
# 5: Chirurgia Ogólna
# 6: Ginekologia
# 7: Laryngologia
# 8: Neurologia
# 9: Urologia
# 10: Dermatologia
# 11: Psychiatria

def get_spec_id(code_str):
    """Zwraca ID specjalizacji na podstawie kodu ICD-9."""
    try:
        # Kod może być '01.23' lub '01.2'. Bierzemy część przed kropką (rozdział).
        # Czasem kod to tekst, usuwamy kropki do analizy numerycznej lub parsujemy prefix.
        
        # Oczyszczanie: 'A.12' -> ignoruj, '12.34' -> 12
        clean_code = re.sub(r'[^0-9.]', '', str(code_str))
        if not clean_code: return None
        
        parts = clean_code.split('.')
        chapter = int(parts[0])
        
        if 1 <= chapter <= 5: return 8 # Neurologia
        if 6 <= chapter <= 7: return 5 # Chirurgia (Dokrewny)
        if 8 <= chapter <= 16: return 3 # Okulistyka
        if 18 <= chapter <= 20: return 7 # Laryngologia (Uszy)
        if 21 <= chapter <= 29:
            # 23 i 24 to zęby
            if chapter in [23, 24]: return 1 # Stomatologia
            return 7 # Laryngologia (Nos, Gardło)
        if 30 <= chapter <= 34: return 5 # Chirurgia/Pulmo
        if 35 <= chapter <= 39: return 2 # Kardiologia
        if 40 <= chapter <= 41: return 5 # Chirurgia/Hemato
        if 42 <= chapter <= 54: return 5 # Chirurgia (Pokarmowy)
        if 55 <= chapter <= 59: return 9 # Urologia
        if 60 <= chapter <= 64: return 9 # Urologia (Męskie)
        if 65 <= chapter <= 71: return 6 # Ginekologia
        if 72 <= chapter <= 75: return 6 # Ginekologia (Położnictwo)
        if 76 <= chapter <= 84: return 4 # Ortopedia
        if 85 <= chapter <= 86: return 10 # Dermatologia/Chirurgia
        if 94 <= chapter <= 94: return 11 # Psychiatria (Terapie)
        
        return None # Inne / Diagnostyka
        
    except Exception:
        return None

def import_icd9():
    print(f"Reading {XLS_PATH}...")
    try:
        # Wczytaj bez nagłówka
        df = pd.read_excel(XLS_PATH, header=None)
        
        print("Importing to database...")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        count = 0
        # Start od wiersza 2 (pomijamy nagłówki)
        for i in range(2, len(df)):
            try:
                row = df.iloc[i]
                
                # Hierarchia: Najbardziej szczegółowy kod wygrywa
                code = None
                name = None
                
                # Kolumna 6 (Kategoria szczegółowa)
                if len(row) > 6 and pd.notna(row[6]):
                    code = str(row[6]).strip()
                    if len(row) > 7 and pd.notna(row[7]):
                        name = str(row[7]).strip()
                        
                # Kolumna 4 (Kategoria główna) - jeśli nie ma szczegółowego
                if not code and len(row) > 4 and pd.notna(row[4]):
                    code = str(row[4]).strip()
                    if len(row) > 5 and pd.notna(row[5]):
                        name = str(row[5]).strip()

                if not code or not name:
                    continue
                    
                # Ignoruj nagłówki rozdziałów tekstowe (AA, A, C) jeśli chcemy tylko numeryczne
                # Ale badania laboratoryjne mają kody literowe (A01), więc je bierzemy.
                
                spec_id = get_spec_id(code)
                category = "Procedura ICD-9"
                
                c.execute('''
                    INSERT INTO procedures (code, name, category, specialization_id) 
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(code) DO UPDATE SET name=excluded.name, specialization_id=excluded.specialization_id
                ''', (code, name, category, spec_id))
                count += 1
                
            except Exception as e:
                pass
                
        conn.commit()
        conn.close()
        print(f"Successfully imported {count} ICD-9 procedures.")
        
    except Exception as e:
        print(f"Import failed: {e}")

if __name__ == "__main__":
    import_icd9()
