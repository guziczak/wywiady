import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "medical_knowledge.db"
ICD10_JSON_PATH = Path(__file__).parent.parent / "icd10.json"

def init_db():
    print(f"Initializing database at {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. Specializations
    c.execute('''
        CREATE TABLE IF NOT EXISTS specializations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL
        )
    ''')

    # 2. ICD-10 Codes
    c.execute('''
        CREATE TABLE IF NOT EXISTS icd10_codes (
            code TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            specialization_id INTEGER,
            FOREIGN KEY(specialization_id) REFERENCES specializations(id)
        )
    ''')

    # 3. Procedures (NFZ/Medical)
    c.execute('''
        CREATE TABLE IF NOT EXISTS procedures (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            specialization_id INTEGER,
            FOREIGN KEY(specialization_id) REFERENCES specializations(id)
        )
    ''')

    # Seed Specializations
    specializations = [
        (1, "Stomatologia", "stomatolog"),
        (2, "Kardiologia", "kardiolog"),
        (3, "Okulistyka", "okulista")
    ]
    c.executemany('INSERT OR IGNORE INTO specializations (id, name, slug) VALUES (?, ?, ?)', specializations)

    # Seed ICD-10 from existing JSON (Dental)
    if ICD10_JSON_PATH.exists():
        with open(ICD10_JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            codes = [(code, desc, 1) for code, desc in data.items()] # 1 = Stomatologia
            c.executemany('INSERT OR REPLACE INTO icd10_codes (code, description, specialization_id) VALUES (?, ?, ?)', codes)
            print(f"Imported {len(codes)} ICD-10 codes for Stomatology.")

    # Seed Procedures (Manual robust list for Stomatology based on Lex.pl/NFZ)
    dental_procedures = [
        ("ST-01", "Badanie lekarskie stomatologiczne (przegląd)", "Diagnostyka", 1),
        ("ST-02", "Badanie kontrolne", "Diagnostyka", 1),
        ("ST-03", "Konsultacja specjalistyczna", "Diagnostyka", 1),
        ("ST-04", "Zdjęcie RTG wewnątrzustne (punktowe)", "Diagnostyka", 1),
        ("ST-05", "Znieczulenie miejscowe powierzchniowe", "Znieczulenie", 1),
        ("ST-06", "Znieczulenie miejscowe nasiękowe", "Znieczulenie", 1),
        ("ST-07", "Znieczulenie przewodowe", "Znieczulenie", 1),
        ("ST-10", "Wypełnienie ubytku kl. I (jedna powierzchnia)", "Zachowawcze", 1),
        ("ST-11", "Wypełnienie ubytku kl. II (dwie powierzchnie)", "Zachowawcze", 1),
        ("ST-12", "Wypełnienie ubytku kl. III/IV (zęby przednie)", "Zachowawcze", 1),
        ("ST-13", "Wypełnienie ubytku kl. V (szyjkowe)", "Zachowawcze", 1),
        ("ST-14", "Odbudowa kąta zęba", "Zachowawcze", 1),
        ("ST-15", "Opatrunek leczniczy w zębie stałym (tlenek cynku)", "Zachowawcze", 1),
        ("ST-20", "Ekstirpacja miazgi (dewitalizacja)", "Endodoncja", 1),
        ("ST-21", "Czasowe wypełnienie kanału", "Endodoncja", 1),
        ("ST-22", "Ostateczne wypełnienie kanału (1 kanał)", "Endodoncja", 1),
        ("ST-23", "Ostateczne wypełnienie kanału (2 kanały)", "Endodoncja", 1),
        ("ST-24", "Ostateczne wypełnienie kanału (3 kanały)", "Endodoncja", 1),
        ("ST-30", "Usunięcie złogów nazębnych (skaling)", "Profilaktyka", 1),
        ("ST-31", "Lakierowanie zębów (fluoryzacja)", "Profilaktyka", 1),
        ("ST-32", "Lakowanie bruzd", "Profilaktyka", 1),
        ("ST-40", "Ekstrakcja zęba jednokorzeniowego", "Chirurgia", 1),
        ("ST-41", "Ekstrakcja zęba wielokorzeniowego", "Chirurgia", 1),
        ("ST-42", "Chirurgiczne usunięcie zęba (dłutowanie)", "Chirurgia", 1),
        ("ST-43", "Nacięcie ropnia", "Chirurgia", 1),
        ("ST-44", "Szycie rany w jamie ustnej", "Chirurgia", 1),
        ("ST-50", "Proteza akrylowa częściowa", "Protetyka", 1),
        ("ST-51", "Proteza akrylowa całkowita", "Protetyka", 1),
        ("ST-52", "Naprawa protezy (sklejenie)", "Protetyka", 1),
        ("ST-53", "Podścielenie protezy", "Protetyka", 1)
    ]
    c.executemany('INSERT OR REPLACE INTO procedures (code, name, category, specialization_id) VALUES (?, ?, ?, ?)', dental_procedures)
    print(f"Imported {len(dental_procedures)} procedures for Stomatology.")

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == "__main__":
    init_db()
