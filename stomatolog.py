"""
Wywiad+ - Nowoczesne GUI do generowania opisów stomatologicznych z wywiadu głosowego.
Używa Gemini Flash do speech-to-text i Claude/Gemini do przetwarzania tekstu.
"""

import flet as ft
import threading
import tempfile
import wave
import os
import json
import time
from pathlib import Path
from datetime import datetime

# Ścieżki konfiguracji
CONFIG_FILE = Path(__file__).parent / "config.json"
ICD_FILE = Path(__file__).parent / "icd10.json"

# Zewnętrzne zależności
try:
    import sounddevice as sd
    import numpy as np
    AUDIO_AVAILABLE = True
except ImportError:
    sd = None
    np = None
    AUDIO_AVAILABLE = False

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    types = None
    GENAI_AVAILABLE = False

# Import proxy z claude-code-py
import sys
sys.path.insert(0, r"C:\Users\guzic\Documents\GitHub\tools\claude-code-py\src")
try:
    from proxy import start_proxy_server, get_proxy_base_url
    from anthropic import Anthropic
    try:
        from utils.auto_session_extractor import extract_session_key_auto
        AUTO_EXTRACTOR_AVAILABLE = True
    except ImportError:
        AUTO_EXTRACTOR_AVAILABLE = False
    PROXY_AVAILABLE = True
except ImportError:
    PROXY_AVAILABLE = False
    AUTO_EXTRACTOR_AVAILABLE = False
    Anthropic = None


def load_config():
    """Ładuje konfigurację z pliku."""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"api_key": "", "session_key": ""}


def save_config(config):
    """Zapisuje konfigurację do pliku."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)
    except Exception:
        pass


def load_icd10():
    """Ładuje kody ICD-10 z pliku JSON."""
    try:
        if ICD_FILE.exists():
            with open(ICD_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def load_claude_token():
    """Ładuje token OAuth z Claude Code."""
    creds_path = Path.home() / ".claude" / ".credentials.json"
    if not creds_path.exists():
        return None
    try:
        with open(creds_path, "r") as f:
            creds = json.load(f)
        oauth_data = creds.get("claudeAiOauth", {})
        expires_at_ms = oauth_data.get("expiresAt", 0)
        if expires_at_ms:
            expires_at = datetime.fromtimestamp(expires_at_ms / 1000.0)
            if datetime.now() >= expires_at:
                return None
        return oauth_data.get("accessToken")
    except Exception:
        return None


# ========== GŁÓWNA APLIKACJA ==========

def main(page: ft.Page):
    # === KONFIGURACJA STRONY ===
    page.title = "Wywiad+"
    page.window.width = 800
    page.window.height = 900
    page.window.min_width = 600
    page.window.min_height = 700
    page.padding = 0
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(
        color_scheme_seed=ft.Colors.BLUE,
        font_family="Segoe UI",
    )

    # === STAN APLIKACJI ===
    config = load_config()
    icd10_codes = load_icd10()

    is_recording = {"value": False}
    audio_data = []
    sample_rate = 16000
    stream_ref = {"stream": None}
    proxy_state = {"started": False, "port": None}

    # === KOMPONENTY UI ===

    # Snackbar do powiadomień
    def show_snackbar(message, color=ft.Colors.GREEN_700):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(message, color=ft.Colors.WHITE),
            bgcolor=color,
            duration=3000,
        )
        page.snack_bar.open = True
        page.update()

    # --- Pola konfiguracji ---
    gemini_key_field = ft.TextField(
        label="Gemini API Key",
        value=config.get("api_key", ""),
        password=True,
        can_reveal_password=True,
        prefix_icon=ft.Icons.KEY,
        hint_text="Pobierz z aistudio.google.com",
        expand=True,
    )

    session_key_field = ft.TextField(
        label="Claude Session Key",
        value=config.get("session_key", ""),
        password=True,
        can_reveal_password=True,
        prefix_icon=ft.Icons.LOCK,
        hint_text="sk-ant-sid01-...",
        expand=True,
    )

    claude_status_text = ft.Text("", size=12)

    def update_claude_status():
        oauth_token = load_claude_token()
        session_key = session_key_field.value.strip() if session_key_field.value else ""

        if session_key and session_key.startswith("sk-ant-sid01-") and PROXY_AVAILABLE:
            claude_status_text.value = "Session Key aktywny"
            claude_status_text.color = ft.Colors.GREEN_700
        elif oauth_token and PROXY_AVAILABLE:
            claude_status_text.value = "OAuth Token dostępny"
            claude_status_text.color = ft.Colors.ORANGE_700
        elif not PROXY_AVAILABLE:
            claude_status_text.value = "Brak modułu Proxy"
            claude_status_text.color = ft.Colors.GREY_500
        else:
            claude_status_text.value = "Tylko Gemini"
            claude_status_text.color = ft.Colors.GREY_500
        page.update()

    def save_settings(e):
        config["api_key"] = gemini_key_field.value or ""
        config["session_key"] = session_key_field.value or ""
        save_config(config)
        update_claude_status()
        show_snackbar("Ustawienia zapisane")

    def clear_session_key(e):
        session_key_field.value = ""
        config["session_key"] = ""
        save_config(config)
        update_claude_status()
        show_snackbar("Session Key usunięty", ft.Colors.ORANGE_700)

    # --- Nagrywanie ---
    record_button = ft.Button(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.MIC, size=28),
                ft.Text("Rozpocznij nagrywanie", size=16, weight=ft.FontWeight.W_500),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=10,
        ),
        style=ft.ButtonStyle(
            padding=ft.Padding(left=32, right=32, top=20, bottom=20),
            shape=ft.RoundedRectangleBorder(radius=12),
            bgcolor=ft.Colors.BLUE_600,
            color=ft.Colors.WHITE,
        ),
        width=280,
        height=64,
    )

    record_status = ft.Text("Gotowy do nagrywania", size=14, color=ft.Colors.GREY_600)
    recording_indicator = ft.ProgressRing(visible=False, width=20, height=20, stroke_width=2)

    transcript_field = ft.TextField(
        label="Transkrypcja wywiadu",
        multiline=True,
        min_lines=4,
        max_lines=8,
        expand=True,
        hint_text="Tutaj pojawi się transkrypcja nagrania...",
    )

    def start_recording():
        if not AUDIO_AVAILABLE:
            show_snackbar("Brak biblioteki audio (sounddevice)", ft.Colors.RED_700)
            return

        is_recording["value"] = True
        audio_data.clear()

        record_button.style.bgcolor = ft.Colors.RED_600
        record_button.content.controls[0].name = ft.Icons.STOP
        record_button.content.controls[1].value = "Zatrzymaj"
        record_status.value = "Nagrywanie..."
        record_status.color = ft.Colors.RED_600
        recording_indicator.visible = True
        page.update()

        def audio_callback(indata, frames, time_info, status):
            if is_recording["value"]:
                audio_data.append(indata.copy())

        stream_ref["stream"] = sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype=np.int16,
            callback=audio_callback
        )
        stream_ref["stream"].start()

    def stop_recording():
        is_recording["value"] = False
        if stream_ref["stream"]:
            stream_ref["stream"].stop()
            stream_ref["stream"].close()

        record_button.style.bgcolor = ft.Colors.BLUE_600
        record_button.content.controls[0].name = ft.Icons.MIC
        record_button.content.controls[1].value = "Rozpocznij nagrywanie"
        record_status.value = "Przetwarzanie..."
        record_status.color = ft.Colors.ORANGE_700
        recording_indicator.visible = True
        page.update()

        if audio_data:
            audio_array = np.concatenate(audio_data, axis=0)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = f.name
                with wave.open(f.name, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes(audio_array.tobytes())

            threading.Thread(target=transcribe_audio, args=(temp_path,), daemon=True).start()
        else:
            record_status.value = "Brak nagrania"
            record_status.color = ft.Colors.GREY_600
            recording_indicator.visible = False
            page.update()

    def toggle_recording(e):
        if not is_recording["value"]:
            start_recording()
        else:
            stop_recording()

    record_button.on_click = toggle_recording

    def transcribe_audio(audio_path):
        api_key = gemini_key_field.value.strip() if gemini_key_field.value else ""

        if not api_key:
            page.run_thread(lambda: update_after_transcription("Brak API key!", None))
            return

        if not GENAI_AVAILABLE:
            page.run_thread(lambda: update_after_transcription("Brak biblioteki google-genai!", None))
            return

        try:
            client = genai.Client(api_key=api_key)
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[
                    "Przetranscybuj poniższe nagranie audio na tekst. "
                    "Zwróć tylko transkrypcję, bez żadnych dodatkowych komentarzy.",
                    types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")
                ]
            )
            transcript = response.text.strip()
            page.run_thread(lambda: update_after_transcription(None, transcript))
        except Exception as ex:
            page.run_thread(lambda: update_after_transcription(str(ex)[:100], None))
        finally:
            try:
                os.unlink(audio_path)
            except Exception:
                pass

    def update_after_transcription(error, transcript):
        recording_indicator.visible = False
        if error:
            record_status.value = f"Błąd: {error}"
            record_status.color = ft.Colors.RED_700
            show_snackbar(f"Błąd transkrypcji: {error}", ft.Colors.RED_700)
        else:
            record_status.value = "Gotowy"
            record_status.color = ft.Colors.GREEN_700
            current = transcript_field.value or ""
            if current.strip():
                transcript_field.value = current + "\n" + transcript
            else:
                transcript_field.value = transcript
            show_snackbar("Transkrypcja zakończona")
        page.update()

    # --- Generowanie opisu ---
    generate_button = ft.Button(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.AUTO_AWESOME, size=24),
                ft.Text("Generuj opis", size=16, weight=ft.FontWeight.W_500),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=8,
        ),
        style=ft.ButtonStyle(
            padding=ft.Padding(left=24, right=24, top=16, bottom=16),
            shape=ft.RoundedRectangleBorder(radius=10),
            bgcolor=ft.Colors.GREEN_600,
            color=ft.Colors.WHITE,
        ),
    )

    generate_progress = ft.ProgressRing(visible=False, width=24, height=24, stroke_width=3)
    model_indicator = ft.Text("", size=12, color=ft.Colors.GREY_600)

    # Pola wyników
    recognition_field = ft.TextField(
        label="Rozpoznanie (z kodem ICD-10)",
        multiline=True,
        min_lines=2,
        max_lines=4,
        read_only=False,
        expand=True,
    )

    service_field = ft.TextField(
        label="Świadczenie",
        multiline=True,
        min_lines=2,
        max_lines=4,
        read_only=False,
        expand=True,
    )

    procedure_field = ft.TextField(
        label="Procedura",
        multiline=True,
        min_lines=4,
        max_lines=8,
        read_only=False,
        expand=True,
    )

    debug_field = ft.TextField(
        label="Debug (raw output)",
        multiline=True,
        min_lines=3,
        max_lines=6,
        read_only=True,
        visible=False,
    )

    def copy_to_clipboard(field, label):
        def do_copy(e):
            if field.value:
                page.set_clipboard(field.value)
                show_snackbar(f"Skopiowano: {label}")
        return do_copy

    def generate_description(e):
        gemini_key = gemini_key_field.value.strip() if gemini_key_field.value else ""
        session_key = session_key_field.value.strip() if session_key_field.value else ""
        claude_token = load_claude_token()
        transcript = transcript_field.value.strip() if transcript_field.value else ""

        if not transcript:
            show_snackbar("Brak transkrypcji do przetworzenia!", ft.Colors.RED_700)
            return

        # Wybierz model
        if session_key and session_key.startswith("sk-ant-sid01-") and PROXY_AVAILABLE:
            model_type = "claude"
            model_indicator.value = "Claude (Session Key)"
            model_indicator.color = ft.Colors.GREEN_700
        elif claude_token and PROXY_AVAILABLE:
            model_type = "claude"
            model_indicator.value = "Claude (OAuth)"
            model_indicator.color = ft.Colors.PURPLE_700
        elif gemini_key and GENAI_AVAILABLE:
            model_type = "gemini"
            model_indicator.value = "Gemini Flash"
            model_indicator.color = ft.Colors.BLUE_700
        else:
            show_snackbar("Brak klucza API!", ft.Colors.RED_700)
            return

        # UI loading state
        generate_button.disabled = True
        generate_progress.visible = True
        recognition_field.value = "Generowanie..."
        service_field.value = "Generowanie..."
        procedure_field.value = "Generowanie..."
        page.update()

        threading.Thread(
            target=process_transcript,
            args=(gemini_key, session_key, claude_token, transcript, model_type),
            daemon=True
        ).start()

    generate_button.on_click = generate_description

    def process_transcript(gemini_key, session_key, claude_token, transcript, model_type):
        icd_context = json.dumps(icd10_codes, indent=2, ensure_ascii=False)

        prompt = f"""Jesteś asystentem do formatowania dokumentacji stomatologicznej.
Twoim zadaniem jest przekształcenie surowych notatek z wywiadu stomatologa na sformatowany tekst dokumentacji.

Dostępne kody ICD-10 (Baza wiedzy):
{icd_context}

INSTRUKCJA:
1. Przeanalizuj tekst i wybierz NAJLEPIEJ pasujący kod z powyższej listy. Jeśli żaden nie pasuje idealnie, wybierz "Inne" (np. K08.8).
2. Sformatuj wynik w JSON.

Wymagane pola JSON:
- "rozpoznanie": tekst diagnozy (np. "Caries profunda dentis 16")
- "icd10": kod z listy (np. "K02.1")
- "swiadczenie": wykonane zabiegi
- "procedura": szczegółowy opis

Transkrypcja wywiadu:
{transcript}

Odpowiedz TYLKO poprawnym kodem JSON:
{{"rozpoznanie": "...", "icd10": "...", "swiadczenie": "...", "procedura": "..."}}"""

        try:
            if model_type == "claude":
                auth_key = session_key if session_key and session_key.startswith("sk-ant-sid01-") else claude_token
                result_text = call_claude(auth_key, prompt, proxy_state)
            else:
                result_text = call_gemini(gemini_key, prompt)

            page.run_thread(lambda: set_debug(result_text))

            # Parse JSON
            cleaned = result_text
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.strip()

            result = json.loads(cleaned)

            icd_code = result.get("icd10", "")
            diagnosis = result.get("rozpoznanie", "-")
            if icd_code and icd_code != "-":
                final_diagnosis = f"[{icd_code}] {diagnosis}"
            else:
                final_diagnosis = diagnosis

            page.run_thread(lambda: set_results(final_diagnosis, result.get("swiadczenie", "-"), result.get("procedura", "-")))

        except json.JSONDecodeError as je:
            page.run_thread(lambda: show_error(f"JSON parse error: {je}"))
        except Exception as ex:
            page.run_thread(lambda: show_error(str(ex)))
        finally:
            page.run_thread(finish_generation)

    def call_claude(auth_token, prompt, proxy_state):
        import io
        import sys as system_module

        if not auth_token:
            raise ValueError("Brak tokena Claude!")

        if not proxy_state["started"]:
            old_stdout = system_module.stdout
            system_module.stdout = io.StringIO()
            try:
                success, port = start_proxy_server(auth_token, port=8765)
            finally:
                system_module.stdout = old_stdout

            if success:
                proxy_state["started"] = True
                proxy_state["port"] = port
                os.environ["ANTHROPIC_BASE_URL"] = get_proxy_base_url(port)
                time.sleep(2)
            else:
                raise Exception("Nie udało się uruchomić proxy")

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
                    text_chunk = event.delta.text
                    if text_chunk:
                        full_text += text_chunk

        return full_text.strip()

    def call_gemini(api_key, prompt):
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        return response.text.strip()

    def set_debug(text):
        debug_field.value = text
        page.update()

    def set_results(recognition, service, procedure):
        recognition_field.value = recognition
        service_field.value = service
        procedure_field.value = procedure
        show_snackbar("Opis wygenerowany!")
        page.update()

    def show_error(msg):
        show_snackbar(f"Błąd: {msg}", ft.Colors.RED_700)
        recognition_field.value = ""
        service_field.value = ""
        procedure_field.value = ""
        page.update()

    def finish_generation():
        generate_button.disabled = False
        generate_progress.visible = False
        page.update()

    def toggle_debug(e):
        debug_field.visible = not debug_field.visible
        e.control.text = "Ukryj Debug" if debug_field.visible else "Pokaż Debug"
        page.update()

    # === LAYOUT ===
    update_claude_status()

    # Header
    header = ft.Container(
        content=ft.Row(
            [
                ft.Row([
                    ft.Icon(ft.Icons.MEDICAL_SERVICES, size=32, color=ft.Colors.WHITE),
                    ft.Text("Wywiad+", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ], spacing=12),
                ft.Row([
                    claude_status_text,
                ]),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        bgcolor=ft.Colors.BLUE_700,
        padding=ft.Padding(left=24, right=24, top=16, bottom=16),
    )

    # Sekcja nagrywania
    recording_section = ft.Card(
        content=ft.Container(
            content=ft.Column([
                ft.Text("Nagrywanie wywiadu", size=18, weight=ft.FontWeight.W_600),
                ft.Divider(height=1),
                ft.Container(
                    content=ft.Column([
                        record_button,
                        ft.Row([recording_indicator, record_status], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                    padding=ft.Padding(left=0, right=0, top=16, bottom=16),
                ),
                transcript_field,
                ft.Row([
                    ft.TextButton("Wyczyść", icon=ft.Icons.DELETE_OUTLINE,
                                  on_click=lambda e: setattr(transcript_field, 'value', '') or page.update()),
                    ft.TextButton("Kopiuj", icon=ft.Icons.COPY, on_click=copy_to_clipboard(transcript_field, "Transkrypcja")),
                ], alignment=ft.MainAxisAlignment.END),
            ], spacing=12),
            padding=20,
        ),
        elevation=2,
    )

    # Sekcja generowania
    generate_section = ft.Container(
        content=ft.Row([
            generate_button,
            generate_progress,
            model_indicator,
        ], spacing=16, alignment=ft.MainAxisAlignment.CENTER),
        padding=ft.Padding(left=0, right=0, top=8, bottom=8),
    )

    # Sekcja wyników
    def result_card(field, label):
        return ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text(label, size=14, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_700),
                        ft.IconButton(ft.Icons.COPY, icon_size=18, tooltip="Kopiuj",
                                      on_click=copy_to_clipboard(field, label)),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    field,
                ], spacing=4),
                padding=16,
            ),
            elevation=1,
        )

    results_section = ft.Column([
        ft.Text("Wygenerowany opis", size=18, weight=ft.FontWeight.W_600),
        result_card(recognition_field, "Rozpoznanie"),
        result_card(service_field, "Świadczenie"),
        result_card(procedure_field, "Procedura"),
        ft.Row([
            ft.TextButton("Pokaż Debug", icon=ft.Icons.BUG_REPORT, on_click=toggle_debug),
        ], alignment=ft.MainAxisAlignment.END),
        debug_field,
    ], spacing=12)

    # Sekcja ustawień (w ExpansionTile)
    settings_section = ft.ExpansionTile(
        title=ft.Text("Ustawienia API", weight=ft.FontWeight.W_500),
        leading=ft.Icon(ft.Icons.SETTINGS),
        expanded=False,
        controls=[
            ft.Container(
                content=ft.Column([
                    gemini_key_field,
                    ft.Row([
                        session_key_field,
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Usuń klucz", on_click=clear_session_key),
                    ]),
                    ft.Row([
                        ft.Button("Zapisz ustawienia", icon=ft.Icons.SAVE, on_click=save_settings),
                    ], alignment=ft.MainAxisAlignment.END),
                ], spacing=16),
                padding=ft.Padding(left=16, right=16, top=0, bottom=16),
            ),
        ],
    )

    # Główny layout
    content = ft.Column([
        header,
        ft.Container(
            content=ft.Column([
                settings_section,
                recording_section,
                generate_section,
                results_section,
            ], spacing=16, scroll=ft.ScrollMode.AUTO),
            padding=20,
            expand=True,
        ),
    ], spacing=0, expand=True)

    page.add(content)


if __name__ == "__main__":
    ft.run(main)
