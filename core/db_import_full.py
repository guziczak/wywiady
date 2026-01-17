import sqlite3
import csv
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "medical_knowledge.db"
CSV_PATH = Path(__file__).parent.parent / "data" / "icd10.csv"

def import_full_icd10():
    print(f"Importing FULL ICD-10 from {CSV_PATH}...")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Modyfikacja tabeli (dodanie description_en jeśli nie ma)
    try:
        c.execute("ALTER TABLE icd10_codes ADD COLUMN description_en TEXT")
    except sqlite3.OperationalError:
        pass # Już istnieje

    # Czytanie CSV
    # Format: Chapter;Classifications;Code;...;Subcategory code;subcategory
    # Interesuje nas: Code (A00.0) i Description (subcategory)
    
    count = 0
    with open(CSV_PATH, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f, delimiter=';')
        next(reader) # Skip header
        
        for row in reader:
            try:
                # Szukamy najbardziej szczegółowego kodu
                # Struktura jest dziwna, Code jest czasem zakresem (A00-B99)
                # Szukamy kolumny 'Subcategory code' (index 11) i 'subcategory' (index 12)
                # Albo 'Category code' (9) i 'Category' (10)
                
                code = ""
                desc = ""
                
                if len(row) > 12 and row[11]: # Subcategory (A00.0)
                    code = row[11]
                    desc = row[12]
                elif len(row) > 10 and row[9]: # Category (A00)
                    code = row[9]
                    desc = row[10]
                
                if code and desc:
                    # Sprawdź czy to kod (nie zakres)
                    if '-' not in code:
                        # Wstawiamy jako EN, PL zostawiamy puste (lub kopiujemy EN jako fallback)
                        c.execute('''
                            INSERT INTO icd10_codes (code, description, description_en, specialization_id) 
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(code) DO UPDATE SET description_en=excluded.description_en
                        ''', (code, desc, desc, None)) # None specialization = ogólne
                        count += 1
                        
            except Exception as e:
                continue

    conn.commit()
    conn.close()
    print(f"Successfully imported {count} ICD-10 codes into database.")

if __name__ == "__main__":
    import_full_icd10()
