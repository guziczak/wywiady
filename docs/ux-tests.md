# UX manual checks (LIVE)

Krotka lista kontrolna do recznego sprawdzenia jakosci UX po zmianach.

## 1. Dock i nagrywanie
- START/STOP dziala tylko w docku; prompter pokazuje wylacznie status.
- Status w docku: GOTOWY / NAGRYWANIE (bez READY/LIVE).

## 2. Transkrypcja
- Provisional nie dubluje segmentow (brak powtorzen tego samego zdania).
- Final/validated zachowuje plynnosc tekstu.

## 3. Q+A i powiadomienia
- Klikniecie karty pytania -> tylko jeden toast "Zebrano pare Q+A!".
- Edycja/usuniecie pary dziala i aktualizuje licznik.

## 4. Overlaye (mobile <900px)
- Otwarcie transkryptu zamyka sufler i pipeline.
- Otwarcie suflera zamyka transkrypt i pipeline.
- Otwarcie pipeline zamyka transkrypt i sufler.

## 5. Spojnosc copy
- Dock: Transkrypt / Sufler / Przeplyw / Skupienie.
- QA: "Zebrane Q+A (Biurko 3D)".
- 3D status: "Laduje biurko 3D..." oraz "3D niedostepne - tryb 2D".

## 6. Cleanup
- Zamkniecie karty Live nie zostawia bledow w konsoli.
- Timery i panele zwalniaja sie po rozlaczeniu.
\n- Dla trybu poradniczego pojawia sie Checklista (badge Check x/y).\n
