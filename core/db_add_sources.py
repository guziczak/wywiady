from core.knowledge_manager import KnowledgeManager

def add_sources():
    km = KnowledgeManager()
    
    # Utwórz tabelę (wywoła się lazy migration w export_to_json, ale wywołajmy to ręcznie)
    km.export_to_json() # To przy okazji utworzy tabelę
    
    print("Adding sources...")
    km.add_source(
        "ICD-10", 
        "https://api.dane.gov.pl/resources/10566,miedzynarodowa-statystyczna-klasyfikacja-chorob-i-problemow-zdrowotnych-icd-10-eng-/file",
        "Oficjalna klasyfikacja ICD-10 (szkielet z dane.gov.pl)"
    )
    km.add_source(
        "ICD-9 PL",
        "https://api.dane.gov.pl/resources/55555,slownik-icd-9-pl-wersja-5-81/file",
        "Słownik procedur medycznych NFZ (wersja 5.34/5.81)"
    )
    km.add_source(
        "Stomatologia",
        "https://sip.lex.pl/akty-prawne/dzu-dziennik-ustaw/wykaz-podstawowych-swiadczen-zdrowotnych-lekarza-stomatologa-16883339/par-1",
        "Wykaz podstawowych świadczeń stomatologicznych (Dz.U.)"
    )
    
    # Re-export to include new data
    km.export_to_json()

if __name__ == "__main__":
    add_sources()
