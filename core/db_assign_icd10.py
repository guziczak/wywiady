import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "medical_knowledge.db"

def assign_icd10_to_specs():
    print("Assigning ICD-10 codes to specializations...")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Mapowanie zakresów ICD-10 do ID specjalizacji
    # 1: Stomatologia (K00-K14) - już częściowo jest, ale uzupełnimy
    # 2: Kardiologia (I00-I99)
    # 3: Okulistyka (H00-H59)
    # 4: Ortopedia (M00-M99)
    # 5: Chirurgia Ogólna (szeroki zakres, np. K, L)
    # 6: Ginekologia (N70-N98, O00-O99)
    # 7: Laryngologia (J00-J39, H60-H95)
    # 8: Neurologia (G00-G99)
    # 9: Urologia (N00-N39)
    # 10: Dermatologia (L00-L99)
    # 11: Psychiatria (F00-F99)
    # 12: Onkologia (C00-D48) - dodamy nową spec.

    mappings = [
        (1, ["K00", "K01", "K02", "K03", "K04", "K05", "K06", "K07", "K08", "K09", "K10", "K11", "K12", "K13", "K14"]),
        (2, ["I"]),
        (3, ["H0", "H1", "H2", "H3", "H4", "H5"]),
        (4, ["M"]),
        (6, ["N7", "N8", "N9", "O"]),
        (7, ["J0", "J1", "J2", "J3", "H6", "H7", "H8", "H9"]),
        (8, ["G"]),
        (9, ["N0", "N1", "N2", "N3"]),
        (10, ["L"]),
        (11, ["F"]),
    ]

    for spec_id, prefixes in mappings:
        for prefix in prefixes:
            # SQL LIKE 'I%'
            query_prefix = prefix + "%"
            c.execute("UPDATE icd10_codes SET specialization_id = ? WHERE code LIKE ?", (spec_id, query_prefix))
            if c.rowcount > 0:
                # print(f"Assigned {c.rowcount} codes starting with {prefix} to spec {spec_id}")
                pass

    conn.commit()
    
    # Check stats
    c.execute("SELECT specialization_id, COUNT(*) FROM icd10_codes GROUP BY specialization_id")
    stats = c.fetchall()
    print("\nStats (Spec ID -> Count):")
    for spec_id, count in stats:
        name = "Ogólne"
        if spec_id:
            c.execute("SELECT name FROM specializations WHERE id=?", (spec_id,))
            res = c.fetchone()
            if res: name = res[0]
        print(f"{name}: {count}")

    conn.close()

if __name__ == "__main__":
    assign_icd10_to_specs()
