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

# Import modułu transkrypcji
try:
    from core.transcriber import TranscriberManager, TranscriberType
    TRANSCRIBER_MANAGER_AVAILABLE = True
except ImportError:
    TranscriberManager = None
    TranscriberType = None
    TRANSCRIBER_MANAGER_AVAILABLE = False

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


# ========== DEBUG LOG ==========
DEBUG_LOG = Path(__file__).parent / "debug.log"

def debug_log(msg):
    """Zapisuje debug do pliku."""
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"{msg}\n")

# Wyczyść log przy starcie
if DEBUG_LOG.exists():
    DEBUG_LOG.unlink()

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

    # Inicjalizacja managera transkrypcji
    transcriber_manager = TranscriberManager() if TRANSCRIBER_MANAGER_AVAILABLE else None
    if transcriber_manager:
        # Ustaw API key z config
        transcriber_manager.set_gemini_api_key(config.get("api_key", ""))
        # Przywróć poprzednio wybrany backend
        saved_backend = config.get("transcriber_backend", "gemini_cloud")
        try:
            transcriber_manager.set_current_backend(TranscriberType(saved_backend))
        except (ValueError, KeyError):
            pass
        # Przywróć wybrany model
        saved_model = config.get("transcriber_model", "small")
        current_backend = transcriber_manager.get_current_backend()
        current_backend.set_model(saved_model)

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
        # Użyj TranscriberManager jeśli dostępny
        if transcriber_manager:
            # Zaktualizuj API key
            api_key = gemini_key_field.value.strip() if gemini_key_field.value else ""
            transcriber_manager.set_gemini_api_key(api_key)

            try:
                transcript = transcriber_manager.transcribe(audio_path, language="pl")
                page.run_thread(lambda: update_after_transcription(None, transcript))
            except Exception as ex:
                page.run_thread(lambda: update_after_transcription(str(ex)[:150], None))
            finally:
                try:
                    os.unlink(audio_path)
                except Exception:
                    pass
            return

        # Fallback do starej metody (Gemini)
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

    # === UI WYBORU BACKENDU TRANSKRYPCJI ===
    # UWAGA: on_change musi być funkcja zdefiniowana PRZED dropdown
    def on_backend_change(e):
        """Zmiana backendu transkrypcji."""
        selected_value = e.control.value if e else backend_radio.value
        debug_log(f"[DEBUG] on_backend_change CALLED! value={selected_value}")
        show_snackbar(f"Wybrano: {selected_value}", ft.Colors.BLUE_700)

        if not transcriber_manager:
            show_snackbar("Brak managera transkrypcji!", ft.Colors.RED_700)
            return

        try:
            refresh_backends_info()
            debug_log(f"[DEBUG] Selected: {selected_value}")

            # Znajdź info
            info = None
            for b in backends_info["data"]:
                if b.type.value == selected_value:
                    info = b
                    break

            if not info:
                show_snackbar(f"Nie znaleziono: {selected_value}", ft.Colors.RED_700)
                return

            debug_log(f"[DEBUG] Backend: {info.name}, installed: {info.is_installed}")

            if not info.is_installed:
                # Dialog instalacji
                def close_dlg(ev):
                    dlg.open = False
                    page.update()

                def do_install(ev):
                    dlg.open = False
                    page.update()
                    on_install_click(None)

                dlg = ft.AlertDialog(
                    modal=True,
                    title=ft.Text(f"Instalacja: {info.name}"),
                    content=ft.Text(
                        f"Pakiet '{info.pip_package}' nie jest zainstalowany.\n\n"
                        f"Kliknij 'Zainstaluj' aby pobrać automatycznie.\n"
                        f"(może potrwać 1-3 minuty)"
                    ),
                    actions=[
                        ft.TextButton("Anuluj", on_click=close_dlg),
                        ft.ElevatedButton("Zainstaluj", on_click=do_install),
                    ],
                )
                page.overlay.append(dlg)
                dlg.open = True
                page.update()
                debug_log("[DEBUG] Dialog shown!")

            elif info.is_available:
                new_type = TranscriberType(selected_value)
                transcriber_manager.set_current_backend(new_type)
                config["transcriber_backend"] = new_type.value
                save_config(config)
                show_snackbar(f"Wybrano: {info.name}", ft.Colors.GREEN_700)

            update_ui_for_current_backend()

        except Exception as ex:
            debug_log(f"[DEBUG] ERROR: {ex}")
            show_snackbar(f"Błąd: {str(ex)[:80]}", ft.Colors.RED_700)

    def on_model_dropdown_change(e):
        """Zmiana modelu."""
        debug_log(f"[DEBUG] on_model_dropdown_change: {e.control.value if e else 'None'}")
        if not transcriber_manager:
            return
        try:
            backend = transcriber_manager.get_current_backend()
            model_name = model_dropdown.value
            if backend.set_model(model_name):
                config["transcriber_model"] = model_name
                save_config(config)
                update_model_status()
        except Exception:
            pass

    # RadioGroup zamiast Dropdown (bo Dropdown w Flet 0.70+ ma problemy z on_change)
    backend_radio = ft.RadioGroup(
        content=ft.Column([
            ft.Radio(value="gemini_cloud", label="Gemini Cloud (online)"),
            ft.Radio(value="faster_whisper", label="Faster Whisper (offline) - REKOMENDOWANY"),
            ft.Radio(value="openai_whisper", label="OpenAI Whisper (offline)"),
        ], spacing=5),
        value="gemini_cloud",
        on_change=lambda e: on_backend_change(e),
    )

    model_dropdown = ft.Dropdown(
        label="Model",
        width=200,
        visible=False,
    )

    # Alias dla kompatybilności
    backend_dropdown = backend_radio

    # Statusy i przyciski
    backend_status_text = ft.Text("", size=13, weight=ft.FontWeight.W_500)
    install_button = ft.Button("Zainstaluj silnik", icon=ft.Icons.DOWNLOAD, visible=False)
    download_model_button = ft.Button("Pobierz model", icon=ft.Icons.DOWNLOAD, visible=False)
    action_progress = ft.ProgressRing(visible=False, width=24, height=24, stroke_width=3, color=ft.Colors.BLUE_600)

    # Cache info o backendach
    backends_info = {"data": []}

    def refresh_backends_info():
        """Odświeża informacje o backendach."""
        if transcriber_manager:
            backends_info["data"] = transcriber_manager.get_available_backends()

    def populate_backend_options():
        """Wypełnia dropdown backendami."""
        debug_log("[DEBUG] populate_backend_options called")
        if not transcriber_manager:
            debug_log("[DEBUG] No transcriber_manager in populate!")
            return

        refresh_backends_info()
        backends = backends_info["data"]
        print(f"[DEBUG] Found {len(backends)} backends")

        options = []
        for b in backends:
            print(f"[DEBUG] Adding option: {b.name}, installed: {b.is_installed}")
            # Status w zależności od instalacji
            if not b.is_installed:
                status = " (wymaga instalacji)"
            elif not b.is_available:
                status = f" ({b.unavailable_reason})"
            else:
                status = ""

            options.append(ft.dropdown.Option(
                key=b.type.value,
                text=f"{b.name}{status}",
            ))

        backend_dropdown.options = options
        backend_radio.value = transcriber_manager.get_current_type().value
        update_ui_for_current_backend()

    def get_current_backend_info():
        """Zwraca info o aktualnie wybranym backendzie."""
        current_type = backend_radio.value
        for b in backends_info["data"]:
            if b.type.value == current_type:
                return b
        return None

    def update_ui_for_current_backend():
        """Aktualizuje UI w zależności od wybranego backendu."""
        if not transcriber_manager:
            return

        info = get_current_backend_info()
        if not info:
            backend_status_text.value = "Błąd ładowania informacji o backendzie"
            backend_status_text.color = ft.Colors.RED_700
            page.update()
            return

        # Reset widoczności
        install_button.visible = False
        download_model_button.visible = False
        model_dropdown.visible = False
        action_progress.visible = False

        if not info.is_installed:
            # Backend nie zainstalowany - pokaż przycisk instalacji
            backend_status_text.value = f"Kliknij 'Zainstaluj silnik' aby pobrać: {info.pip_package}"
            backend_status_text.color = ft.Colors.ORANGE_700
            install_button.visible = True
            install_button.disabled = False
        elif info.type == TranscriberType.GEMINI_CLOUD:
            # Gemini Cloud - nie wymaga modeli lokalnych
            if info.is_available:
                backend_status_text.value = "Cloud API - gotowy do użycia"
                backend_status_text.color = ft.Colors.GREEN_700
            else:
                backend_status_text.value = "Wprowadź Gemini API Key i kliknij 'Zapisz ustawienia'"
                backend_status_text.color = ft.Colors.ORANGE_700
        else:
            # Offline backend - pokaż wybór modelu
            model_dropdown.visible = True
            update_model_options()

        page.update()

    def update_model_options():
        """Aktualizuje opcje modeli dla wybranego backendu offline."""
        if not transcriber_manager:
            return

        try:
            backend = transcriber_manager.get_current_backend()
        except Exception:
            return

        models = backend.get_models()

        options = []
        for m in models:
            size_str = f" - {m.size_mb}MB" if m.size_mb > 0 else ""
            status = " [gotowy]" if m.is_downloaded else ""
            options.append(ft.dropdown.Option(
                key=m.name,
                text=f"{m.name}{size_str}{status}"
            ))

        model_dropdown.options = options
        current_model = backend.get_current_model()
        if current_model:
            model_dropdown.value = current_model

        update_model_status()

    def update_model_status():
        """Aktualizuje status modelu (pobrany/do pobrania)."""
        if not transcriber_manager:
            return

        try:
            backend = transcriber_manager.get_current_backend()
            models = backend.get_models()
            current_model_name = model_dropdown.value

            for m in models:
                if m.name == current_model_name:
                    if m.is_downloaded:
                        download_model_button.visible = False
                        backend_status_text.value = f"Model '{m.name}' gotowy"
                        backend_status_text.color = ft.Colors.GREEN_700
                    else:
                        download_model_button.visible = True
                        backend_status_text.value = f"Model '{m.name}' wymaga pobrania ({m.size_mb}MB)"
                        backend_status_text.color = ft.Colors.ORANGE_700
                    break
        except Exception:
            pass

        page.update()

    def on_install_click(e):
        """Instalacja pakietu backendu."""
        if not transcriber_manager:
            return

        info = get_current_backend_info()
        if not info or not info.pip_package:
            return

        # Wyraźny feedback
        install_button.visible = False
        action_progress.visible = True
        backend_status_text.value = f"Instaluję {info.pip_package}... (może potrwać 1-3 min)"
        backend_status_text.color = ft.Colors.BLUE_700
        show_snackbar(f"Rozpoczynam instalację {info.pip_package}...", ft.Colors.BLUE_700)
        page.update()

        def do_install():
            def progress_cb(msg):
                def update_ui():
                    backend_status_text.value = msg
                    page.update()
                page.run_thread(update_ui)

            success, message = transcriber_manager.install_backend(
                TranscriberType(backend_radio.value),
                progress_cb
            )
            page.run_thread(lambda: finish_install(success, message))

        threading.Thread(target=do_install, daemon=True).start()

    def finish_install(success, message):
        action_progress.visible = False

        if success:
            show_snackbar("Zainstalowano! Uruchom ponownie aplikację.", ft.Colors.GREEN_700)
            backend_status_text.value = "ZAINSTALOWANO! Zamknij i uruchom aplikację ponownie."
            backend_status_text.color = ft.Colors.GREEN_700
            install_button.visible = False
        else:
            show_snackbar(f"Błąd: {message}", ft.Colors.RED_700)
            backend_status_text.value = f"Błąd instalacji: {message[:80]}"
            backend_status_text.color = ft.Colors.RED_700
            install_button.visible = True
            install_button.disabled = False

        page.update()

    def on_download_model_click(e):
        """Pobieranie modelu."""
        if not transcriber_manager:
            return

        model_name = model_dropdown.value
        download_model_button.visible = False
        action_progress.visible = True
        backend_status_text.value = f"Pobieram model '{model_name}'... (może potrwać kilka minut)"
        backend_status_text.color = ft.Colors.BLUE_700
        show_snackbar(f"Rozpoczynam pobieranie modelu {model_name}...", ft.Colors.BLUE_700)
        page.update()

        def do_download():
            def progress_cb(p):
                def update_ui():
                    backend_status_text.value = f"Pobieranie '{model_name}': {int(p*100)}%"
                    page.update()
                page.run_thread(update_ui)

            try:
                backend = transcriber_manager.get_current_backend()
                success = backend.download_model(model_name, progress_cb)
                page.run_thread(lambda: finish_model_download(success))
            except Exception as ex:
                page.run_thread(lambda: finish_model_download(False))

        threading.Thread(target=do_download, daemon=True).start()

    def finish_model_download(success):
        action_progress.visible = False

        if success:
            show_snackbar("Model pobrany! Gotowy do użycia.", ft.Colors.GREEN_700)
            backend_status_text.value = "Model pobrany - gotowy do transkrypcji!"
            backend_status_text.color = ft.Colors.GREEN_700
            download_model_button.visible = False
            refresh_backends_info()
            update_model_options()
        else:
            show_snackbar("Błąd pobierania modelu", ft.Colors.RED_700)
            backend_status_text.value = "Błąd pobierania - spróbuj ponownie"
            backend_status_text.color = ft.Colors.RED_700
            download_model_button.visible = True
            download_model_button.disabled = False

        page.update()

    # Przypisz handlery (dropdown on_change już przypisane w konstruktorze)
    install_button.on_click = on_install_click
    download_model_button.on_click = on_download_model_click

    # Wypełnij opcje przy starcie
    if transcriber_manager:
        populate_backend_options()

    # Sekcja ustawień (w ExpansionTile)
    settings_section = ft.ExpansionTile(
        title=ft.Text("Ustawienia", weight=ft.FontWeight.W_500),
        leading=ft.Icon(ft.Icons.SETTINGS),
        expanded=False,
        controls=[
            ft.Container(
                content=ft.Column([
                    ft.Text("Transkrypcja (Speech-to-Text)", weight=ft.FontWeight.W_600, size=14),
                    backend_radio,
                    model_dropdown,
                    ft.Row([
                        backend_status_text,
                        action_progress,
                        install_button,
                        download_model_button,
                    ], spacing=8, wrap=True),
                    ft.Divider(height=20),
                    ft.Text("Klucze API", weight=ft.FontWeight.W_600, size=14),
                    gemini_key_field,
                    ft.Row([
                        session_key_field,
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Usuń klucz", on_click=clear_session_key),
                    ]),
                    ft.Row([
                        ft.Button("Zapisz ustawienia", icon=ft.Icons.SAVE, on_click=save_settings),
                    ], alignment=ft.MainAxisAlignment.END),
                ], spacing=12),
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
