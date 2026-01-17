import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "medical_knowledge.db"

def seed_icd9_procedures():
    print("Seeding ICD-9 Procedures (General)...")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Struktura: Kod, Nazwa, Kategoria (Rozdział), Specjalizacja (ID - opcjonalnie, zmapujemy potem)
    # Baza wiedzy ogólnej ICD-9 PL (Top Procedury)
    
    procedures = [
        # UKŁAD NERWOWY (01-05) - Neurologia/Neurochirurgia (ID 4 - stworzymy)
        ("01.2", "Kraniotomia", "Układ nerwowy", None),
        ("03.31", "Nakłucie lędźwiowe", "Układ nerwowy", None),
        
        # OCZY (08-16) - Okulistyka (ID 3)
        ("13.41", "Usunięcie zaćmy metodą fakoemulsyfikacji", "Oczy", 3),
        ("10.3", "Nacięcie spojówki", "Oczy", 3),
        ("95.02", "Badanie ogólne oka", "Oczy", 3),
        ("95.04", "Badanie dna oka", "Oczy", 3),

        # USZY, NOS, GARDŁO (18-29) - Laryngologia (ID 5) / Stomatologia (ID 1)
        ("23.0", "Ekstrakcja zęba (niechirurgiczna)", "Stomatologia", 1),
        ("23.1", "Chirurgiczna ekstrakcja zęba", "Stomatologia", 1),
        ("23.2", "Przywrócenie zęba metodą wypełnienia", "Stomatologia", 1),
        ("23.7", "Leczenie kanałowe", "Stomatologia", 1),
        ("24.1", "Diagnostyka stomatologiczna", "Stomatologia", 1),
        ("96.54", "Płukanie jamy ustnej", "Stomatologia", 1),

        # UKŁAD ODDECHOWY (30-34) - Pulmonologia (ID 6)
        ("33.24", "Bronchoskopia", "Układ oddechowy", None),
        ("89.52", "Spirometria", "Układ oddechowy", None),

        # UKŁAD KRĄŻENIA (35-39) - Kardiologia (ID 2)
        ("89.52", "Elektrokardiogram (EKG)", "Układ krążenia", 2),
        ("88.72", "Echokardiografia (Echo serca)", "Układ krążenia", 2),
        ("36.1", "Pomostowanie aortalno-wieńcowe (By-pass)", "Układ krążenia", 2),
        ("37.22", "Wszczepienie stymulatora serca", "Układ krążenia", 2),
        ("89.41", "Test wysiłkowy kardiologiczny", "Układ krążenia", 2),

        # UKŁAD POKARMOWY (42-54) - Gastrologia (ID 7)
        ("45.13", "Gastroskopia", "Układ pokarmowy", None),
        ("45.23", "Kolonoskopia", "Układ pokarmowy", None),
        ("47.0", "Wycięcie wyrostka robaczkowego", "Układ pokarmowy", None),

        # UKŁAD MOCZOWY (55-59) - Urologia (ID 8)
        ("57.32", "Cystoskopia", "Układ moczowy", None),

        # UKŁAD MIĘŚNIOWO-SZKIELETOWY (76-84) - Ortopedia (ID 9)
        ("81.54", "Całkowita endoprotezoplastyka kolana", "Ortopedia", None),
        ("81.51", "Całkowita endoprotezoplastyka biodra", "Ortopedia", None),
        ("79.3", "Otwarte nastawienie złamania z wewnętrzną stabilizacją", "Ortopedia", None),
        ("88.2", "RTG kości i stawów", "Ortopedia", None),
        ("93.5", "Fizykoterapia", "Rehabilitacja", None),

        # INNE DIAGNOSTYCZNE
        ("90.5", "Badanie morfologiczne krwi", "Laboratorium", None),
        ("91.4", "Badanie moczu", "Laboratorium", None),
        ("88.7", "USG diagnostyczne", "Diagnostyka", None),
        ("87.03", "Tomografia komputerowa (CT)", "Diagnostyka", None),
        ("88.91", "Rezonans magnetyczny (MRI)", "Diagnostyka", None)
    ]

    # Insert
    count = 0
    for code, name, cat, spec_id in procedures:
        try:
            # Nadpisz istniejące (żeby zaktualizować) lub dodaj nowe
            c.execute('''
                INSERT INTO procedures (code, name, category, specialization_id) 
                VALUES (?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET name=excluded.name, category=excluded.category, specialization_id=excluded.specialization_id
            ''', (code, name, cat, spec_id))
            count += 1
        except Exception as e:
            print(f"Error seeding {code}: {e}")

    conn.commit()
    conn.close()
    print(f"Seeded {count} general ICD-9 procedures.")

if __name__ == "__main__":
    seed_icd9_procedures()
