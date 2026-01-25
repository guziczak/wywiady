import os
import sys
import json
import time
import asyncio
import io
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List

# Core imports
from core.knowledge_manager import KnowledgeManager
from core.log_utils import log

# Specialization Manager (opcjonalny import)
try:
    from core.specialization_manager import get_specialization_manager
    SPEC_MANAGER_AVAILABLE = True
except ImportError:
    SPEC_MANAGER_AVAILABLE = False

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

ANTHROPIC_AVAILABLE = Anthropic is not None

# Obsluga Proxy dla Claude (lokalny moduł w repo)
ROOT_DIR = Path(__file__).parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from proxy import start_proxy_server, get_proxy_base_url
    PROXY_AVAILABLE = True
except ImportError:
    PROXY_AVAILABLE = False

CLAUDE_AVAILABLE = PROXY_AVAILABLE and ANTHROPIC_AVAILABLE


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
            raise RuntimeError("ModuĹ‚ proxy nie jest dostÄ™pny")
        if Anthropic is None:
            raise RuntimeError("Brak biblioteki anthropic (pip install anthropic)")
            
        if not auth_token:
            raise ValueError("Brak tokena Claude!")

        # Przechwytywanie stdout zeby proxy nie smiecilo
        if not self.proxy_started:
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                success, port = start_proxy_server(auth_token, port=8765)
                proxy_log = sys.stdout.getvalue()
            finally:
                sys.stdout = old_stdout

            if success:
                self.proxy_started = True
                self.proxy_port = port
                os.environ["ANTHROPIC_BASE_URL"] = get_proxy_base_url(port)
                time.sleep(2)
            else:
                detail = (proxy_log or "").strip()
                if detail:
                    raise Exception(f"Nie udalo sie uruchomic proxy: {detail}")
                raise Exception("Nie udalo sie uruchomic proxy")

        client = Anthropic(api_key=auth_token)
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
        primary_model = "gemini-2.5-flash"
        fallback_model = "gemini-2.0-flash"
        try:
            response = client.models.generate_content(
                model=primary_model,
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            log(f"[LLM] Gemini {primary_model} error ({e}); fallback to {fallback_model}")
            response = client.models.generate_content(
                model=fallback_model,
                contents=prompt
            )
            return response.text.strip()

    def _call_with_retry(self, func, *args, max_retries=3, initial_delay=1.0):
        """WywoĹ‚uje funkcjÄ™ z mechanizmem retry (exponential backoff)."""
        delay = initial_delay
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                return func(*args)
            except Exception as e:
                error_msg = str(e)
                # Retry tylko dla bĹ‚Ä™dĂłw serwera (5xx) lub Rate Limit (429)
                if "500" in error_msg or "503" in error_msg or "429" in error_msg or "Overloaded" in error_msg:
                    print(f"[LLM] Error: {e}. Retrying in {delay}s... ({attempt+1}/{max_retries})", flush=True)
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                    last_exception = e
                else:
                    raise e # Inne bĹ‚Ä™dy (np. auth) rzucamy od razu
        
        raise last_exception

    async def generate_description(
        self,
        transcript: str,
        icd10_codes: Dict, # Deprecated, kept for compat but unused
        config: Dict,
        spec_id: int = None,  # Backward compat - pojedyncza specjalizacja
        spec_ids: list = None  # Multi-select - lista specjalizacji
    ) -> Tuple[Dict[str, Any], str]:
        """
        Główna metoda generująca opis.
        Używa dynamicznych promptów ze SpecializationManager jeśli dostępny.
        Obsługuje multi-select specjalizacji (spec_ids ma priorytet nad spec_id).
        """

        # Ustal listę specjalizacji
        if spec_ids is not None:
            active_spec_ids = spec_ids
        elif spec_id is not None:
            active_spec_ids = [spec_id]
        elif SPEC_MANAGER_AVAILABLE:
            spec_manager = get_specialization_manager()
            active_spec_ids = spec_manager.get_active_ids()
        else:
            active_spec_ids = [1]  # Fallback do stomatologii

        # 1. Pobierz wiedzę z bazy (merge jeśli multi-select)
        km = KnowledgeManager()
        if len(active_spec_ids) == 1:
            context_data = km.get_context_for_specialization(active_spec_ids[0])
        else:
            context_data = km.get_context_for_specializations(active_spec_ids)

        # Ogranicz kontekst dla promptu
        icd10_list = context_data.get("icd10", [])[:300]
        icd9_list = context_data.get("icd9", [])[:300]

        icd_context = json.dumps(icd10_list, indent=2, ensure_ascii=False)
        proc_context = json.dumps(icd9_list, indent=2, ensure_ascii=False)

        # 2. Buduj prompt
        if SPEC_MANAGER_AVAILABLE:
            spec_manager = get_specialization_manager()
            prompt = spec_manager.build_description_prompt(
                transcript=transcript,
                icd_context=icd_context,
                proc_context=proc_context,
                spec_ids=active_spec_ids
            )
        else:
            # Fallback
            prompt = f"""JesteĹ› asystentem do automatyzacji dokumentacji medycznej.
Analizujesz transkrypcjÄ™ wizyty lekarskiej i wyciÄ…gasz z niej wykonane procedury oraz diagnozy.

Dostepne sĹ‚owniki (BAZA WIEDZY):
--- ICD-10 (Diagnozy) ---
{icd_context}
...

--- ICD-9 PL (Procedury) ---
{proc_context}
...

INSTRUKCJA:
1. Przeanalizuj tekst i zidentyfikuj WSZYSTKIE wykonane czynnoĹ›ci oraz postawione diagnozy.
2. Dla kaĹĽdej pozycji znajdĹş NAJLEPIEJ pasujÄ…cy kod z powyĹĽszych list.
3. Wyekstrahuj LOKALIZACJÄ.
4. JeĹ›li procedury/kodu nie ma na liĹ›cie, uĹĽyj najbardziej zbliĹĽonego lub ogĂłlnego.

Format wyjĹ›ciowy JSON:
{{
  "diagnozy": [
    {{ "kod": "...", "nazwa": "...", "opis_tekstowy": "...", "zab": "..." }}
  ],
  "procedury": [
    {{ "kod": "...", "nazwa": "...", "opis_tekstowy": "...", "zab": "..." }}
  ]
}}

Transkrypcja wywiadu:
{transcript}

Odpowiedz TYLKO poprawnym kodem JSON."""

        # 3. Pobranie kluczy i preferencji
        gemini_key = config.get("api_key", "")
        session_key = config.get("session_key", "")
        claude_token = self._load_claude_token()
        preferred_model = config.get("generation_model", "Auto")

        has_session_key = bool(session_key and session_key.startswith("sk-") and CLAUDE_AVAILABLE)
        has_gemini_key = bool(gemini_key and GENAI_AVAILABLE)
        has_oauth_token = bool(claude_token and CLAUDE_AVAILABLE)
        
        model_type = None
        model_name = "Nieznany"

        # A. Wymuszone przez uĹĽytkownika
        if preferred_model == "Gemini" and has_gemini_key:
            model_type = "gemini"
            model_name = "Gemini 2.5 Flash"
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
                model_name = "Gemini 2.5 Flash"
            elif has_oauth_token:
                model_type = "claude"
                model_name = "Claude (OAuth)"

        if not model_type:
            # Nie rzucamy bĹ‚edu, prĂłbujemy zwrĂłciÄ‡ pusty wynik z info
            print("[LLM] Brak kluczy API. Generowanie niemoĹĽliwe.", flush=True)
            return {"diagnozy": [], "procedury": []}, "Brak API"

        # 4. Wykonanie
        loop = asyncio.get_event_loop()
        result_text = None
        used_model = model_name

        async def run_claude():
            auth_key = session_key if session_key and session_key.startswith("sk-") else claude_token
            return await loop.run_in_executor(None, lambda: self._call_with_retry(self._call_claude, auth_key, prompt))

        async def run_gemini():
            return await loop.run_in_executor(None, lambda: self._call_with_retry(self._call_gemini, gemini_key, prompt))

        if model_type == "claude":
            try:
                print(f"[LLM] PrĂłba uĹĽycia: {model_name}", flush=True)
                result_text = await run_claude()
            except Exception as e:
                if preferred_model == "Auto" and has_gemini_key:
                    print(f"[LLM] Claude error ({e}), fallback to Gemini...", flush=True)
                    used_model = "Gemini Flash (Fallback)"
                    result_text = await run_gemini()
                else:
                    raise e
        else:
            print(f"[LLM] PrĂłba uĹĽycia: {model_name}", flush=True)
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
            print(f"[LLM] JSON Error: {e}", flush=True)
            # PrĂłba naprawy prostego JSONA
            return {"diagnozy": [], "procedury": []}, f"BĹ‚Ä…d JSON ({used_model})"


    async def generate_soap(
        self,
        transcript: str,
        config: Dict,
        diagnoses: Optional[List[Dict]] = None,
        procedures: Optional[List[Dict]] = None
    ) -> Tuple[Dict[str, Any], str]:
        """Generate SOAP summary from transcript."""
        transcript = transcript or ""
        if not transcript.strip():
            return {}, "No transcript"

        diag_context = json.dumps(diagnoses or [], ensure_ascii=False, indent=2)
        proc_context = json.dumps(procedures or [], ensure_ascii=False, indent=2)

        prompt = f"""Jestes lekarzem. Na podstawie transkrypcji przygotuj podsumowanie SOAP.
Nie wymyslaj faktow. Jesli brak informacji, zwroc pusty string.

Transkrypcja:
{transcript}

Rozpoznania (opcjonalnie):
{diag_context}

Procedury (opcjonalnie):
{proc_context}

Zwroc TYLKO poprawny JSON z kluczami:
{{
  \"subjective\": \"\",
  \"objective\": \"\",
  \"assessment\": \"\",
  \"plan\": \"\",
  \"recommendations\": \"\",
  \"medications\": \"\",
  \"tests_ordered\": \"\",
  \"tests_results\": \"\",
  \"referrals\": \"\",
  \"certificates\": \"\",
  \"additional_notes\": \"\"
}}
"""

        gemini_key = config.get("api_key", "")
        session_key = config.get("session_key", "")
        claude_token = self._load_claude_token()
        preferred_model = config.get("generation_model", "Auto")

        has_session_key = bool(session_key and session_key.startswith("sk-") and CLAUDE_AVAILABLE)
        has_gemini_key = bool(gemini_key and GENAI_AVAILABLE)
        has_oauth_token = bool(claude_token and CLAUDE_AVAILABLE)

        model_type = None
        model_name = "Unknown"

        if preferred_model == "Gemini" and has_gemini_key:
            model_type = "gemini"
            model_name = "Gemini 2.5 Flash"
        elif preferred_model == "Claude" and (has_session_key or has_oauth_token):
            model_type = "claude"
            model_name = "Claude (Session Key)" if has_session_key else "Claude (OAuth)"

        if not model_type:
            if has_session_key and PROXY_AVAILABLE:
                model_type = "claude"
                model_name = "Claude (Session Key)"
            elif has_gemini_key:
                model_type = "gemini"
                model_name = "Gemini 2.5 Flash"
            elif has_oauth_token:
                model_type = "claude"
                model_name = "Claude (OAuth)"

        if not model_type:
            log("[LLM] No API keys available. SOAP generation skipped.")
            return {}, "No API"

        loop = asyncio.get_event_loop()
        result_text = None
        used_model = model_name

        async def run_claude():
            auth_key = session_key if session_key and session_key.startswith("sk-") else claude_token
            return await loop.run_in_executor(None, lambda: self._call_with_retry(self._call_claude, auth_key, prompt))

        async def run_gemini():
            return await loop.run_in_executor(None, lambda: self._call_with_retry(self._call_gemini, gemini_key, prompt))

        if model_type == "claude":
            try:
                log(f"[LLM] SOAP: using {model_name}")
                result_text = await run_claude()
            except Exception as e:
                if preferred_model == "Auto" and has_gemini_key:
                    log(f"[LLM] SOAP Claude error ({e}), fallback to Gemini")
                    used_model = "Gemini 2.5 Flash (Fallback)"
                    result_text = await run_gemini()
                else:
                    raise e
        else:
            log(f"[LLM] SOAP: using {model_name}")
            result_text = await run_gemini()

        cleaned = result_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned), used_model
        except json.JSONDecodeError as e:
            log(f"[LLM] SOAP JSON error: {e}")
            return {}, f"JSON error ({used_model})"

    async def generate_suggestions(
        self,
        transcript: str,
        config: Dict,
        exclude_questions: Optional[List[str]] = None,
        spec_id: int = None,
        spec_ids: list = None
    ) -> List[str]:
        """
        Generuje sugestie pytań uzupełniających.
        Obsługuje multi-select specjalizacji (spec_ids ma priorytet nad spec_id).
        """

        # Ustal listę specjalizacji
        if spec_ids is not None:
            active_spec_ids = spec_ids
        elif spec_id is not None:
            active_spec_ids = [spec_id]
        elif SPEC_MANAGER_AVAILABLE:
            spec_manager = get_specialization_manager()
            active_spec_ids = spec_manager.get_active_ids()
        else:
            active_spec_ids = [1]

        if SPEC_MANAGER_AVAILABLE:
            spec_manager = get_specialization_manager()
            prompt = spec_manager.build_suggestions_prompt(
                transcript=transcript,
                exclude_questions=exclude_questions,
                spec_ids=active_spec_ids
            )
        else:
            exclude_section = ""
            if exclude_questions:
                exclude_list = "\n".join([f"- {q}" for q in exclude_questions])
                exclude_section = f"PYTANIA JUĹ» ZADANE:\n{exclude_list}"

            prompt = f"""JesteĹ› doĹ›wiadczonym lekarzem. Zasugeruj 3 pytania dla pacjenta.
Kontekst:
{transcript}
{exclude_section}
Format JSON: ["Pytanie 1?", "Pytanie 2?", "Pytanie 3?"]"""

        gemini_key = config.get("api_key", "")
        loop = asyncio.get_event_loop()
        
        try:
            if gemini_key and GENAI_AVAILABLE:
                response = await loop.run_in_executor(None, lambda: self._call_with_retry(self._call_gemini, gemini_key, prompt))
            else:
                # Fallback to Claude logic
                session_key = config.get("session_key", "")
                claude_token = self._load_claude_token()
                
                if (session_key or claude_token) and CLAUDE_AVAILABLE:
                    auth_key = session_key if session_key and session_key.startswith("sk-") else claude_token
                    response = await loop.run_in_executor(None, lambda: self._call_with_retry(self._call_claude, auth_key, prompt))
                else:
                    return []

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

    async def generate_patient_answers(
        self,
        question: str,
        config: Dict,
        spec_id: int = None,
        spec_ids: list = None
    ) -> List[str]:
        """Generuje 3 przykładowe odpowiedzi pacjenta do pytania lekarza."""
        if not question:
            return []

        # Ustal listę specjalizacji
        if spec_ids is not None:
            active_spec_ids = spec_ids
        elif spec_id is not None:
            active_spec_ids = [spec_id]
        elif SPEC_MANAGER_AVAILABLE:
            spec_manager = get_specialization_manager()
            active_spec_ids = spec_manager.get_active_ids()
        else:
            active_spec_ids = [1]

        spec_label = ""
        if SPEC_MANAGER_AVAILABLE:
            spec_manager = get_specialization_manager()
            names = []
            for sid in active_spec_ids:
                spec = spec_manager.get_by_id(sid)
                if spec:
                    names.append(spec.name)
            
            if names:
                spec_label = f"Specjalizacja: {', '.join(names)}"

        prompt = f"""Jesteś pacjentem w gabinecie lekarskim.
{spec_label}
Lekarz pyta: "{question}"

Podaj DOKŁADNIE 3 krótkie, realistyczne odpowiedzi pacjenta w języku polskim (1 zdanie każda).
Zwróć WYŁĄCZNIE poprawny JSON w formacie:
["Odpowiedź 1", "Odpowiedź 2", "Odpowiedź 3"]
"""

        gemini_key = config.get("api_key", "")
        loop = asyncio.get_event_loop()

        try:
            if gemini_key and GENAI_AVAILABLE:
                response = await loop.run_in_executor(
                    None, lambda: self._call_with_retry(self._call_gemini, gemini_key, prompt)
                )
            else:
                session_key = config.get("session_key", "")
                claude_token = self._load_claude_token()
                if (session_key or claude_token) and CLAUDE_AVAILABLE:
                    auth_key = session_key if session_key and session_key.startswith("sk-") else claude_token
                    response = await loop.run_in_executor(
                        None, lambda: self._call_with_retry(self._call_claude, auth_key, prompt)
                    )
                else:
                    return []

            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.strip()

            parsed = json.loads(cleaned)
            if not isinstance(parsed, list):
                return []

            answers: List[str] = []
            for item in parsed:
                if isinstance(item, str):
                    text = item.strip()
                    if text and text not in answers:
                        answers.append(text)
            return answers[:3]

        except Exception as e:
            print(f"[LLM] Patient answers error: {e}", flush=True)
            return []

    async def validate_segment(self, segment: str, context: str, suggested_questions: List[str], config: Dict) -> Dict:
        """Waliduje segment transkrypcji przez AI (interpunkcja)."""

        prompt = f"""Popraw interpunkcjÄ™ w tym segmencie transkrypcji medycznej. NIE ZMIENIAJ SĹĂ“W.
Kontekst: {context}
Segment: "{segment}"
JSON: {{"corrected_text": "...", "needs_newline": true/false}}"""

        gemini_key = config.get("api_key", "")
        loop = asyncio.get_event_loop()

        try:
            if gemini_key and GENAI_AVAILABLE:
                response = await loop.run_in_executor(None, lambda: self._call_with_retry(self._call_gemini, gemini_key, prompt))
            else:
                session_key = config.get("session_key", "")
                claude_token = self._load_claude_token()
                if (session_key or claude_token) and CLAUDE_AVAILABLE:
                    auth_key = session_key if session_key and session_key.startswith("sk-") else claude_token
                    response = await loop.run_in_executor(None, lambda: self._call_with_retry(self._call_claude, auth_key, prompt))
                else:
                    return {"corrected_text": segment, "needs_newline": False}

            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.strip()

            return json.loads(cleaned)

        except Exception as e:
            print(f"[LLM] Validation error: {e}", flush=True)
            return {"corrected_text": segment, "needs_newline": False}

