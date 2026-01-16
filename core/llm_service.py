import os
import sys
import json
import time
import asyncio
import io
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List

# Importy opcjonalne (zaleznosci)
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

# Obsluga Proxy dla Claude (zakladajac ze sciezka jest ustawiona lub wzgledna)
# W glownej aplikacji dodajemy sciezke do tools, tutaj robimy to samo dla bezpieczenstwa
TOOLS_DIR = Path(__file__).parent.parent / "tools"
PROXY_PATH = TOOLS_DIR / "claude-code-py" / "src"
if str(PROXY_PATH) not in sys.path:
    sys.path.insert(0, str(PROXY_PATH))

try:
    from proxy import start_proxy_server, get_proxy_base_url
    PROXY_AVAILABLE = True
except ImportError:
    PROXY_AVAILABLE = False

class LLMService:
    def __init__(self):
        self.proxy_started = False
        self.proxy_port = None

    def _load_claude_token(self) -> Optional[str]:
        """Pobiera token OAuth z pliku konfiguracyjnego claude-code."""
        creds_path = Path.home() / ".claude" / ".credentials.json"
        if not creds_path.exists():
            return None
        try:
            creds = json.loads(creds_path.read_text())
            oauth_data = creds.get("claudeAiOauth", {})
            expires_at_ms = oauth_data.get("expiresAt", 0)
            if expires_at_ms:
                if datetime.now() >= datetime.fromtimestamp(expires_at_ms / 1000.0):
                    return None
            return oauth_data.get("accessToken")
        except Exception:
            return None

    def _call_claude(self, auth_token: str, prompt: str) -> str:
        """Wywoluje Claude API przez proxy."""
        if not PROXY_AVAILABLE:
            raise RuntimeError("Moduł proxy nie jest dostępny")
            
        if not auth_token:
            raise ValueError("Brak tokena Claude!")

        # Przechwytywanie stdout zeby proxy nie smiecilo
        if not self.proxy_started:
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                success, port = start_proxy_server(auth_token, port=8765)
            finally:
                sys.stdout = old_stdout

            if success:
                self.proxy_started = True
                self.proxy_port = port
                os.environ["ANTHROPIC_BASE_URL"] = get_proxy_base_url(port)
                time.sleep(2)
            else:
                raise Exception("Nie udalo sie uruchomic proxy")

        client = Anthropic(api_key=auth_token)
        # Uzywamy streamingu dla responsywnosci (choc tutaj zbieramy calosc)
        stream = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            stream=True
        )

        full_text = ""
        for event in stream:
            if event.type == "content_block_delta":
                if hasattr(event, 'delta') and hasattr(event.delta, 'text'):
                    full_text += event.delta.text or ""

        return full_text.strip()

    def _call_gemini(self, api_key: str, prompt: str) -> str:
        """Wywoluje Gemini API."""
        if not GENAI_AVAILABLE:
            raise RuntimeError("Biblioteka Google GenAI nie jest zainstalowana")
            
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt
        )
        return response.text.strip()

    async def generate_description(
        self, 
        transcript: str, 
        icd10_codes: Dict, 
        config: Dict
    ) -> Tuple[Dict[str, Any], str]:
        """
        Główna metoda generująca opis.
        Zwraca krotkę: (wynik_json, nazwa_uzytego_modelu)
        """
        
        # 1. Przygotowanie Promptu
        icd_context = json.dumps(icd10_codes, indent=2, ensure_ascii=False)
        prompt = f"""Jestes asystentem do formatowania dokumentacji stomatologicznej.
Twoim zadaniem jest przeksztalcenie surowych notatek z wywiadu stomatologa na sformatowany tekst dokumentacji.

Dostepne kody ICD-10 (Baza wiedzy):
{icd_context}

INSTRUKCJA:
1. Przeanalizuj tekst i wybierz NAJLEPIEJ pasujacy kod z powyzszej listy.
2. JEŚLI transkrypcja nie zawiera wystarczających danych medycznych (np. tylko powitanie, szum, pusta rozmowa), wpisz "-" w polach rozpoznania i kodu. NIE ZMYŚLAJ DIAGNOZY.
3. Sformatuj wynik w JSON.

Wymagane pola JSON:
- "rozpoznanie": tekst diagnozy (lub "-" gdy brak danych)
- "icd10": kod z listy (lub "-" gdy brak danych)
- "swiadczenie": wykonane zabiegi (lub "-" gdy brak danych)
- "procedura": szczegolowy opis (lub "-" gdy brak danych)

Transkrypcja wywiadu:
{transcript}

Odpowiedz TYLKO poprawnym kodem JSON:
{{"rozpoznanie": "...", "icd10": "...", "swiadczenie": "...", "procedura": "..."}}"""

        # 2. Pobranie kluczy i preferencji
        gemini_key = config.get("api_key", "")
        session_key = config.get("session_key", "")
        claude_token = self._load_claude_token()
        preferred_model = config.get("generation_model", "Auto")

        # 3. Smart Selection Logic
        has_session_key = bool(session_key and session_key.startswith("sk-"))
        has_gemini_key = bool(gemini_key and GENAI_AVAILABLE)
        has_oauth_token = bool(claude_token and PROXY_AVAILABLE)
        
        model_type = None
        model_name = "Nieznany"

        # A. Wymuszone przez użytkownika
        if preferred_model == "Gemini" and has_gemini_key:
            model_type = "gemini"
            model_name = "Gemini 3 Flash (Preview)"
        elif preferred_model == "Claude" and (has_session_key or has_oauth_token):
            model_type = "claude"
            model_name = "Claude (Session Key)" if has_session_key else "Claude (OAuth)"
        
        # B. Tryb AUTO
        if not model_type:
            if has_session_key and PROXY_AVAILABLE:
                model_type = "claude"
                model_name = "Claude (Session Key)"
            elif has_gemini_key:
                model_type = "gemini"
                model_name = "Gemini 3 Flash (Preview)"
            elif has_oauth_token:
                model_type = "claude"
                model_name = "Claude (OAuth)"

        if not model_type:
            raise ValueError("Brak dostępnego klucza API (skonfiguruj Claude lub Gemini)")

        # 4. Wykonanie (z asynchronicznością i fallbackiem)
        loop = asyncio.get_event_loop()
        result_text = None
        used_model = model_name

        async def run_claude():
            auth_key = session_key if session_key and session_key.startswith("sk-") else claude_token
            return await loop.run_in_executor(None, lambda: self._call_claude(auth_key, prompt))

        async def run_gemini():
            return await loop.run_in_executor(None, lambda: self._call_gemini(gemini_key, prompt))

        if model_type == "claude":
            try:
                print(f"[LLM] Próba użycia: {model_name}", flush=True)
                result_text = await run_claude()
            except Exception as e:
                # Fallback logic
                if preferred_model == "Auto" and has_gemini_key:
                    print(f"[LLM] Claude error ({e}), fallback to Gemini...", flush=True)
                    used_model = "Gemini Flash (Fallback)"
                    result_text = await run_gemini()
                else:
                    raise e # Re-raise to be handled by UI
        else:
            print(f"[LLM] Próba użycia: {model_name}", flush=True)
            result_text = await run_gemini()

        # 5. Parsowanie JSON
        print(f"[LLM] Raw result: {result_text!r}", flush=True)
        cleaned = result_text
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()

        try:
            result_json = json.loads(cleaned)
            return result_json, used_model
        except json.JSONDecodeError as e:
            raise ValueError(f"Model zwrócił niepoprawny JSON: {e}")

    def _call_with_retry(self, func, *args, max_retries=3, initial_delay=1.0):
        """Wywołuje funkcję z mechanizmem retry (exponential backoff)."""
        delay = initial_delay
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                return func(*args)
            except Exception as e:
                error_msg = str(e)
                # Retry tylko dla błędów serwera (5xx) lub Rate Limit (429 - czasem warto poczekać)
                if "500" in error_msg or "503" in error_msg or "429" in error_msg or "Overloaded" in error_msg:
                    print(f"[LLM] Error: {e}. Retrying in {delay}s... ({attempt+1}/{max_retries})", flush=True)
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                    last_exception = e
                else:
                    raise e # Inne błędy (np. auth) rzucamy od razu
        
        raise last_exception

    async def generate_suggestions(self, transcript: str, config: Dict) -> List[str]:
        """Generuje sugestie pytań uzupełniających."""
        
        # ... (prompt definition) ...
        icd_context = "" # Not needed for suggestions
        prompt = f"""Jesteś doświadczonym stomatologiem przeprowadzającym wywiad.
Twoim celem jest postawienie precyzyjnej diagnozy (ICD-10) oraz zaplanowanie leczenia.

Oto dotychczasowy przebieg rozmowy:
---
{transcript}
---

Zadanie:
Zasugeruj DOKŁADNIE 3 krótkie, konkretne pytania, które warto teraz zadać pacjentowi, aby:
1. Doprecyzować objawy (np. rodzaj bólu, czynniki wyzwalające).
2. Wykluczyć inne schorzenia.
3. Uzyskać brakujące informacje medyczne.

Jeśli wywiad jest kompletny, zasugeruj: ["Wywiad kompletny - można przejść do badania", "Czy ma Pan/Pani inne dolegliwości?", "Czy przyjmuje Pan/Pani leki na stałe?"].
Jeśli brak danych, zasugeruj 3 pytania ogólne.

Odpowiedź zwróć TYLKO jako listę JSON stringów, np.:
["Czy ból nasila się w nocy?", "Czy ząb reaguje na ciepło?", "Czy występuje obrzęk?"]
"""
        # Wybór modelu (analogicznie jak w generate_description, ale uproszczone dla szybkosci)
        gemini_key = config.get("api_key", "")
        # Preferujemy Gemini bo jest szybkie i tanie (Flash)
        
        loop = asyncio.get_event_loop()
        
        try:
            if gemini_key and GENAI_AVAILABLE:
                # Używamy retry
                response = await loop.run_in_executor(None, lambda: self._call_with_retry(self._call_gemini, gemini_key, prompt))
            else:
                # Fallback to Claude logic if needed, or simplified
                session_key = config.get("session_key", "")
                claude_token = self._load_claude_token()
                
                if (session_key or claude_token) and PROXY_AVAILABLE:
                    auth_key = session_key if session_key and session_key.startswith("sk-") else claude_token
                    # Używamy retry
                    response = await loop.run_in_executor(None, lambda: self._call_with_retry(self._call_claude, auth_key, prompt))
                else:
                    return ["Brak konfiguracji AI"]

            # Parse JSON
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.strip()
            
            return json.loads(cleaned)
            
        except Exception as e:
            print(f"[LLM] Suggestion error: {e}", flush=True)
            return []

    async def validate_segment(self, segment: str, context: str, suggested_questions: List[str], config: Dict) -> Dict:
        """
        Waliduje segment transkrypcji przez AI.

        Args:
            segment: Fragment tekstu do walidacji
            context: Poprzedni sfinalizowany tekst (kontekst rozmowy)
            suggested_questions: Aktualnie sugerowane pytania
            config: Konfiguracja z kluczami API

        Returns:
            {
                "is_complete": bool,  # Czy to kompletna myśl/zdanie
                "corrected_text": str,  # Poprawiony tekst z interpunkcją
                "needs_newline": bool,  # Czy dodać nową linię przed tym segmentem
                "confidence": float  # 0.0-1.0
            }
        """

        questions_str = "\n".join([f"- {q}" for q in suggested_questions]) if suggested_questions else "(brak)"

        prompt = f"""Jesteś asystentem do walidacji transkrypcji mowy w gabinecie stomatologicznym.

KONTEKST ROZMOWY (wcześniejsze wypowiedzi):
{context if context else "(początek rozmowy)"}

SUGEROWANE PYTANIA LEKARZA (referencja):
{questions_str}

NOWY SEGMENT DO WALIDACJI:
"{segment}"

ZADANIE - ROZPOZNAJ KTO MÓWI:

1. LEKARZ zadaje PYTANIA:
   - Zaczyna od "Czy", "Jak", "Kiedy", "Gdzie", "Od kiedy", "Co"
   - Często pasuje do jednego z sugerowanych pytań
   - Whisper może transkrybować "Czy" jako "Te", "To", "Ty" - wtedy POPRAW
   - Kończy się znakiem zapytania

2. PACJENT daje ODPOWIEDZI:
   - To STWIERDZENIA, NIE pytania!
   - Np. "Boli mnie górna czwórka", "Tak, reaguje na zimne", "Od tygodnia"
   - NIE zamieniaj odpowiedzi pacjenta na pytania!
   - Kończy się kropką

WSKAZÓWKI ROZPOZNAWANIA:
- Jeśli poprzednia wypowiedź to PYTANIE → nowa to prawdopodobnie ODPOWIEDŹ pacjenta
- Jeśli poprzednia wypowiedź to ODPOWIEDŹ → nowa to prawdopodobnie PYTANIE lekarza
- Krótkie "tak", "nie", "mhm" → to odpowiedzi pacjenta
- Opisy objawów ("boli", "reaguje", "od X dni") → odpowiedzi pacjenta

ZASADY OGÓLNE:
- is_complete = false tylko gdy zdanie jest URWANE w połowie
- needs_newline = true gdy zmiana mówiącego (lekarz↔pacjent) lub nowy temat
- Popraw błędy transkrypcji, ale ZACHOWAJ sens i typ wypowiedzi

Odpowiedz TYLKO w formacie JSON:
{{"is_complete": true/false, "corrected_text": "...", "needs_newline": true/false, "confidence": 0.0-1.0}}"""

        gemini_key = config.get("api_key", "")
        loop = asyncio.get_event_loop()

        try:
            if gemini_key and GENAI_AVAILABLE:
                response = await loop.run_in_executor(
                    None,
                    lambda: self._call_with_retry(self._call_gemini, gemini_key, prompt)
                )
            else:
                # Fallback
                session_key = config.get("session_key", "")
                claude_token = self._load_claude_token()

                if (session_key or claude_token) and PROXY_AVAILABLE:
                    auth_key = session_key if session_key and session_key.startswith("sk-") else claude_token
                    response = await loop.run_in_executor(
                        None,
                        lambda: self._call_with_retry(self._call_claude, auth_key, prompt)
                    )
                else:
                    return {"is_complete": True, "corrected_text": segment, "needs_newline": False, "confidence": 0.5}

            # Parse JSON
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.strip()

            result = json.loads(cleaned)
            print(f"[LLM] Validation result: {result}", flush=True)
            return result

        except Exception as e:
            print(f"[LLM] Validation error: {e}", flush=True)
            # Fallback - zakładamy że kompletne
            return {"is_complete": True, "corrected_text": segment, "needs_newline": False, "confidence": 0.5}
