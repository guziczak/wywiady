import os
import sys
import json
import time
import asyncio
import io
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

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
