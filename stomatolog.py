"""
Minimalistyczne GUI do generowania opisów stomatologicznych z wywiadu głosowego.
Używa Gemini Flash do speech-to-text i przetwarzania tekstu.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import tempfile
import wave
import os
import webbrowser
import base64
import json

# Ścieżka do pliku konfiguracyjnego
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
ICD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icd10.json")

# Zewnętrzne zależności
try:
    import sounddevice as sd
    import numpy as np
except ImportError:
    sd = None
    np = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

try:
    import requests as req_lib
except ImportError:
    req_lib = None

try:
    import cloudscraper
except ImportError:
    cloudscraper = None

# Import lokalnego proxy
try:
    from proxy_server import start_proxy_server, get_proxy_base_url
    PROXY_AVAILABLE = True
except ImportError:
    PROXY_AVAILABLE = False

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

# Import auto-extractora z zewnętrznego narzędzia (opcjonalne)
try:
    import sys
    sys.path.insert(0, r"C:\Users\guzic\Documents\GitHub\tools\claude-code-py\src")
    from utils.auto_session_extractor import extract_session_key_auto
    AUTO_EXTRACTOR_AVAILABLE = True
except ImportError:
    AUTO_EXTRACTOR_AVAILABLE = False

def load_claude_token():
    """Ładuje token z Claude Code (~/.claude/.credentials.json)."""
    from pathlib import Path
    from datetime import datetime

    # Nowa lokalizacja w Claude Code
    creds_path = Path.home() / ".claude" / ".credentials.json"

    if not creds_path.exists():
        return None

    try:
        with open(creds_path, "r") as f:
            creds = json.load(f)

        # Token jest w claudeAiOauth
        oauth_data = creds.get("claudeAiOauth", {})

        # Sprawdź czy token nie wygasł
        expires_at_ms = oauth_data.get("expiresAt", 0)
        if expires_at_ms:
            expires_at = datetime.fromtimestamp(expires_at_ms / 1000.0)
            if datetime.now() >= expires_at:
                return None

        return oauth_data.get("accessToken")
    except Exception:
        return None


class StomatologApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Wywiad Stomatologiczny")
        self.root.geometry("700x850")  # Zwiększono wysokość
        self.root.resizable(True, True)

        # Stan nagrywania
        self.is_recording = False
        self.audio_data = []
        self.sample_rate = 16000
        self.api_key_var = tk.StringVar()
        self.session_key_var = tk.StringVar()
        self.icd10_codes = {}
        self.chat_uuid = None

        self._create_widgets()
        self._load_config()
        self._load_icd10()

        # Zapisz config przy zamknięciu
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_icd10(self):
        """Ładuje kody ICD-10 z pliku JSON."""
        try:
            if os.path.exists(ICD_FILE):
                with open(ICD_FILE, "r", encoding="utf-8") as f:
                    self.icd10_codes = json.load(f)
        except Exception as e:
            print(f"Błąd ładowania ICD-10: {e}")

    def _load_config(self):
        """Ładuje zapisaną konfigurację."""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                    self.api_key_var.set(config.get("api_key", ""))
                    self.session_key_var.set(config.get("session_key", ""))
                    self.chat_uuid = config.get("chat_uuid", None)
            
            self._update_claude_status()
        except:
            pass

    def _save_config(self):
        """Zapisuje konfigurację."""
        try:
            config = {
                "api_key": self.api_key_var.get(),
                "session_key": self.session_key_var.get(),
                "chat_uuid": getattr(self, "chat_uuid", None)
            }
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f)
        except:
            pass

    def _update_claude_status(self):
        """Aktualizuje status tokena Claude."""
        oauth_token = load_claude_token()
        session_key = self.session_key_var.get().strip()

        if session_key and session_key.startswith("sk-ant-sid01-") and PROXY_AVAILABLE:
            self.claude_status.config(
                text="✓ Session Key aktywny - pełny dostęp do claude.ai",
                foreground="green"
            )
        elif oauth_token and PROXY_AVAILABLE:
            self.claude_status.config(
                text="✓ Token OAuth dostępny (może wymagać Session Key)",
                foreground="orange"
            )
        elif not PROXY_AVAILABLE:
            self.claude_status.config(
                text="Brak modułu Proxy - tylko Gemini",
                foreground="gray"
            )
        else:
            self.claude_status.config(
                text="Brak tokena Claude - używam Gemini Flash",
                foreground="gray"
            )

    def _on_close(self):
        """Obsługuje zamknięcie okna."""
        self._save_config()
        self.root.destroy()

    def _create_widgets(self):
        # Główny kontener z paddingiem
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # === SEKCJA API KEY & CONFIG ===
        api_frame = ttk.LabelFrame(main_frame, text="Konfiguracja AI", padding="5")
        api_frame.pack(fill=tk.X, pady=(0, 10))

        # --- Google Gemini ---
        gemini_row = ttk.Frame(api_frame)
        gemini_row.pack(fill=tk.X, pady=(0, 5))
        
        link_label = ttk.Label(gemini_row, text="Gemini API Key:", cursor="hand2", foreground="blue")
        link_label.pack(side=tk.LEFT)
        link_label.bind("<Button-1>", lambda e: webbrowser.open("https://aistudio.google.com/app/apikey"))
        
        self.api_key_entry = ttk.Entry(gemini_row, textvariable=self.api_key_var, width=40, show="*")
        self.api_key_entry.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)

        # --- Claude Session Key ---
        claude_row = ttk.Frame(api_frame)
        claude_row.pack(fill=tk.X, pady=(5, 0))

        ttk.Label(claude_row, text="Claude Session Key:").pack(side=tk.LEFT)
        self.session_key_entry = ttk.Entry(claude_row, textvariable=self.session_key_var, width=40, show="*")
        self.session_key_entry.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)

        # Przycisk czyszczenia klucza
        ttk.Button(
            claude_row,
            text="🗑️",
            width=3,
            command=self._clear_session_key
        ).pack(side=tk.LEFT, padx=(2, 0))
        
        # Przycisk Auto-Login
        if AUTO_EXTRACTOR_AVAILABLE:
            self.auto_login_btn = ttk.Button(
                claude_row, 
                text="🔑 Auto-login (Selenium)", 
                command=self._start_auto_login
            )
            self.auto_login_btn.pack(side=tk.LEFT, padx=(5, 0))

        # Checkbox do pokazania kluczy
        self.show_key_var = tk.BooleanVar()
        ttk.Checkbutton(
            api_frame,
            text="Pokaż klucze",
            variable=self.show_key_var,
            command=self._toggle_key_visibility
        ).pack(anchor=tk.W, pady=(5, 0))

        # Info o Claude
        self.claude_status = ttk.Label(api_frame, text="", foreground="gray")
        self.claude_status.pack(anchor=tk.W, pady=(5, 0))
        
        # === SEKCJA NAGRYWANIA ===
        record_frame = ttk.LabelFrame(main_frame, text="Nagrywanie", padding="5")
        record_frame.pack(fill=tk.X, pady=(0, 10))
        self.record_btn = ttk.Button(
            record_frame,
            text="🎤 Rozpocznij nagrywanie",
            command=self._toggle_recording
        )
        self.record_btn.pack(pady=5)

        self.record_status = ttk.Label(record_frame, text="Status: Gotowy")
        self.record_status.pack()

        # === SEKCJA TRANSKRYPCJI ===
        trans_frame = ttk.LabelFrame(main_frame, text="Transkrypcja wywiadu", padding="5")
        trans_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        trans_btn_row = ttk.Frame(trans_frame)
        trans_btn_row.pack(fill=tk.X)

        trans_copy_btn = ttk.Button(trans_btn_row, text="📋 Kopiuj")
        trans_copy_btn.config(command=lambda: self._copy_to_clipboard(self.transcript_text, trans_copy_btn))
        trans_copy_btn.pack(side=tk.RIGHT)

        ttk.Button(
            trans_btn_row,
            text="🗑️ Wyczyść",
            command=lambda: self.transcript_text.delete("1.0", tk.END)
        ).pack(side=tk.RIGHT, padx=(0, 5))

        self.transcript_text = tk.Text(trans_frame, height=6, wrap=tk.WORD)
        self.transcript_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        # === PRZYCISK GENEROWANIA ===
        gen_frame = ttk.Frame(main_frame)
        gen_frame.pack(pady=10)

        self.gen_btn = ttk.Button(
            gen_frame,
            text="⚡ Generuj opis",
            command=self._generate_description
        )
        self.gen_btn.pack(side=tk.LEFT)

        ttk.Button(
            gen_frame,
            text="🗑️ Czat",
            width=8,
            command=self._reset_chat
        ).pack(side=tk.LEFT, padx=(5, 0))

        self.progress = ttk.Progressbar(gen_frame, mode='indeterminate', length=200)
        # Progress pakujemy dynamicznie w _set_loading_state

        self.model_indicator = ttk.Label(gen_frame, text="", foreground="gray")
        self.model_indicator.pack(side=tk.LEFT, padx=(10, 0))

        # === SEKCJA WYNIKÓW (GŁÓWNA) ===
        # Używamy PanedWindow dla elastyczności lub po prostu frame z expand
        results_frame = ttk.LabelFrame(main_frame, text="Wygenerowany opis", padding="5")
        results_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Kontener na pola wyników
        self.results_container = ttk.Frame(results_frame)
        self.results_container.pack(fill=tk.BOTH, expand=True)

        # Rozpoznanie
        self._create_result_field(self.results_container, "Rozpoznanie:", "recognition", height=4)

        # Świadczenie
        self._create_result_field(self.results_container, "Świadczenie:", "service", height=4)

        # Procedura - to pole często jest najdłuższe
        self._create_result_field(self.results_container, "Procedura:", "procedure", height=8)

        # === DEBUG (ZWIJANY) ===
        debug_ctrl_frame = ttk.Frame(main_frame)
        debug_ctrl_frame.pack(fill=tk.X, pady=(5, 0))

        self.debug_visible = False
        self.debug_toggle_btn = ttk.Button(
            debug_ctrl_frame, 
            text="🐞 Pokaż Debug", 
            command=self._toggle_debug_section
        )
        self.debug_toggle_btn.pack(side=tk.LEFT)

        # Ramka debuga (domyślnie nie spakowana)
        self.debug_frame = ttk.LabelFrame(main_frame, text="Raw output z Gemini/Claude", padding="5")
        
        debug_btn_row = ttk.Frame(self.debug_frame)
        debug_btn_row.pack(fill=tk.X)

        debug_copy_btn = ttk.Button(debug_btn_row, text="📋 Kopiuj")
        debug_copy_btn.config(command=lambda: self._copy_to_clipboard(self.debug_text, debug_copy_btn))
        debug_copy_btn.pack(side=tk.RIGHT)

        self.debug_text = tk.Text(self.debug_frame, height=10, wrap=tk.WORD, bg="#f0f0f0")
        self.debug_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

    def _set_loading_state(self, is_loading):
        """Zarządza stanem ładowania UI."""
        if is_loading:
            self.gen_btn.config(state="disabled", text="⏳ Przetwarzanie...")
            self.progress.pack(side=tk.LEFT, padx=10)
            self.progress.start(15)
            
            # Placeholdery
            for field in [self.recognition_text, self.service_text, self.procedure_text]:
                field.delete("1.0", tk.END)
                field.insert("1.0", "Generowanie...")
                field.config(foreground="gray")
        else:
            self.gen_btn.config(state="normal", text="⚡ Generuj opis")
            self.progress.stop()
            self.progress.pack_forget()
            
            # Przywróć kolor tekstu (jeśli był zmieniony)
            for field in [self.recognition_text, self.service_text, self.procedure_text]:
                field.config(foreground="black")

    def _toggle_debug_section(self):
        """Pokazuje/ukrywa sekcję debugowania."""
        if self.debug_visible:
            self.debug_frame.pack_forget()
            self.debug_toggle_btn.config(text="🐞 Pokaż Debug")
            self.debug_visible = False
        else:
            self.debug_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 10))
            self.debug_toggle_btn.config(text="🐞 Ukryj Debug")
            self.debug_visible = True
            # Scroll na dół żeby pokazać debug
            self.root.after(100, lambda: self.debug_text.see(tk.END))

    def _create_result_field(self, parent, label_text, attr_name, height=3):
        """Tworzy pole wynikowe z etykietą i przyciskiem kopiowania."""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        header = ttk.Frame(frame)
        header.pack(fill=tk.X)

        ttk.Label(header, text=label_text, font=("", 9, "bold")).pack(side=tk.LEFT)

        text_widget = tk.Text(frame, height=height, wrap=tk.WORD)
        text_widget.pack(fill=tk.BOTH, expand=True, pady=(2, 0))

        copy_btn = ttk.Button(header, text="📋 Kopiuj")
        copy_btn.config(command=lambda tw=text_widget, cb=copy_btn: self._copy_to_clipboard(tw, cb))
        copy_btn.pack(side=tk.RIGHT)

        setattr(self, f"{attr_name}_text", text_widget)

    def _clear_session_key(self):
        """Czyści zapisany klucz sesji."""
        self.session_key_var.set("")
        self._save_config()
        self._update_claude_status()
        messagebox.showinfo("Info", "Klucz sesji został usunięty.")

    def _toggle_key_visibility(self):
        """Przełącza widoczność kluczy API."""
        show_char = "" if self.show_key_var.get() else "*"
        self.api_key_entry.config(show=show_char)
        self.session_key_entry.config(show=show_char)

    def _start_auto_login(self):
        """Uruchamia auto-login w tle."""
        if not AUTO_EXTRACTOR_AVAILABLE:
            messagebox.showerror("Błąd", "Brak modułu Selenium/WebDriver!")
            return
            
        self.claude_status.config(text="⏳ Otwieram przeglądarkę... Zaloguj się!", foreground="blue")
        threading.Thread(target=self._process_auto_login, daemon=True).start()

    def _process_auto_login(self):
        """Logika auto-logowania."""
        try:
            key = extract_session_key_auto()
            if key:
                self.root.after(0, lambda: self.session_key_var.set(key))
                self.root.after(0, lambda: self._save_config())
                self.root.after(0, lambda: self._update_claude_status())
                self.root.after(0, lambda: messagebox.showinfo("Sukces", "Pobrano Session Key!"))
            else:
                self.root.after(0, lambda: self.claude_status.config(text="❌ Nie udało się pobrać klucza", foreground="red"))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Błąd", f"Błąd logowania: {e}"))
            self.root.after(0, lambda: self.claude_status.config(text="❌ Błąd logowania", foreground="red"))

    def _copy_to_clipboard(self, text_widget, btn=None):
        """Kopiuje zawartość pola tekstowego do schowka."""
        content = text_widget.get("1.0", tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            # Krótki feedback wizualny na przycisku
            if btn:
                original = btn.cget("text")
                btn.config(text="✓ OK")
                self.root.after(800, lambda: btn.config(text=original))

    def _toggle_recording(self):
        """Rozpoczyna lub kończy nagrywanie."""
        if sd is None:
            messagebox.showerror("Błąd", "Brak biblioteki sounddevice!\nZainstaluj: pip install sounddevice numpy")
            return

        if not self.is_recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        """Rozpoczyna nagrywanie z mikrofonu."""
        self.is_recording = True
        self.audio_data = []
        self.record_btn.config(text="⏹️ Zatrzymaj nagrywanie")
        self.record_status.config(text="Status: Nagrywanie...")

        def audio_callback(indata, frames, time, status):
            if self.is_recording:
                self.audio_data.append(indata.copy())

        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype=np.int16,
            callback=audio_callback
        )
        self.stream.start()

    def _stop_recording(self):
        """Zatrzymuje nagrywanie i wysyła do transkrypcji."""
        self.is_recording = False
        self.stream.stop()
        self.stream.close()

        self.record_btn.config(text="🎤 Rozpocznij nagrywanie")
        self.record_status.config(text="Status: Przetwarzanie...")

        # Zapisz audio do pliku tymczasowego
        if self.audio_data:
            audio_array = np.concatenate(self.audio_data, axis=0)

            # Zapisz jako WAV
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = f.name
                with wave.open(f.name, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(audio_array.tobytes())

            # Transkrybuj w tle
            threading.Thread(
                target=self._transcribe_audio,
                args=(temp_path,),
                daemon=True
            ).start()
        else:
            self.record_status.config(text="Status: Brak nagrania")

    def _transcribe_audio(self, audio_path):
        """Wysyła audio do Claude (proxy) lub Gemini i otrzymuje transkrypcję."""
        gemini_key = self.api_key_var.get().strip()
        session_key = self.session_key_var.get().strip()
        
        transcript = None
        used_model = "None"

        # 1. Próba użycia Claude (jeśli mamy session key)
        if session_key and session_key.startswith("sk-ant-sid01-") and PROXY_AVAILABLE:
            try:
                # Upewnij się, że proxy działa
                if not hasattr(self, '_proxy_started') or not self._proxy_started:
                    success, port = start_proxy_server(session_key, port=8765, conversation_uuid=self.chat_uuid)
                    if success:
                        self._proxy_started = True
                        self._proxy_port = port
                
                port = getattr(self, "_proxy_port", 8765)
                
                # Wyślij plik do proxy
                import requests
                with open(audio_path, 'rb') as f:
                    files = {'file': (os.path.basename(audio_path), f, 'audio/wav')}
                    self._update_status("Status: Przetwarzanie (Claude Audio)...")
                    response = requests.post(f"http://127.0.0.1:{port}/convert", files=files, timeout=120)
                
                if response.status_code == 200:
                    data = response.json()
                    transcript = data.get("text")
                    if transcript:
                        used_model = "Claude"
            except Exception as e:
                print(f"Claude Audio fail: {e}")
                # Fallback do Gemini

        # 2. Fallback do Gemini (jeśli Claude zawiódł lub brak klucza)
        if not transcript:
            if not gemini_key:
                self._update_status("Status: Brak API key Gemini i Claude!")
                return
            if genai is None:
                self._update_status("Status: Brak biblioteki google-genai!")
                return

            try:
                self._update_status("Status: Przetwarzanie (Gemini Flash)...")
                client = genai.Client(api_key=gemini_key)

                # Wczytaj plik audio
                with open(audio_path, "rb") as f:
                    audio_bytes = f.read()

                # Wyślij do Gemini
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[
                        "Przetranscybuj poniższe nagranie audio na tekst. "
                        "Zwróć tylko transkrypcję, bez żadnych dodatkowych komentarzy.",
                        types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")
                    ]
                )

                transcript = response.text.strip()
                used_model = "Gemini"

            except Exception as e:
                self._update_status(f"Status: Błąd - {str(e)[:50]}")
                # Usuń plik tymczasowy
                try:
                    os.unlink(audio_path)
                except:
                    pass
                return

        # Sukces
        self.root.after(0, lambda: self._set_transcript(transcript))
        self._update_status(f"Status: Gotowy ({used_model})")
        
        # Usuń plik tymczasowy
        try:
            os.unlink(audio_path)
        except:
            pass

    def _set_transcript(self, text):
        """Dopisuje tekst transkrypcji na końcu."""
        current = self.transcript_text.get("1.0", tk.END).strip()
        if current:
            # Dopisz z nową linią
            self.transcript_text.insert(tk.END, "\n" + text)
        else:
            # Pierwsze nagranie
            self.transcript_text.insert("1.0", text)

    def _update_status(self, status):
        """Aktualizuje status (thread-safe)."""
        self.root.after(0, lambda: self.record_status.config(text=status))

    def _generate_description(self):
        """Generuje opis medyczny na podstawie transkrypcji."""
        gemini_key = self.api_key_var.get().strip()
        session_key = self.session_key_var.get().strip()
        claude_token = load_claude_token()
        
        transcript = self.transcript_text.get("1.0", tk.END).strip()

        if not transcript:
            messagebox.showerror("Błąd", "Brak transkrypcji do przetworzenia!")
            return

        # Wybierz model - priorytet Session Key -> Token Claude -> Gemini
        if session_key and session_key.startswith("sk-ant-sid01-") and PROXY_AVAILABLE:
            model_type = "claude"
            self.model_indicator.config(text="→ claude.ai (Session Key)", foreground="green")
        elif claude_token and PROXY_AVAILABLE:
            model_type = "claude"
            self.model_indicator.config(text="→ claude.ai (OAuth Token)", foreground="purple")
        elif gemini_key and genai:
            model_type = "gemini"
            self.model_indicator.config(text="→ Gemini Flash", foreground="blue")
        else:
            messagebox.showerror("Błąd", "Brak Session Key/Tokena Claude ani Gemini API key!")
            return

        # Ustaw stan ładowania
        self._set_loading_state(True)

        # Przetwarzaj w tle
        threading.Thread(
            target=self._process_transcript,
            args=(gemini_key, session_key, claude_token, transcript, model_type),
            daemon=True
        ).start()

    def _process_transcript(self, gemini_key, session_key, claude_token, transcript, model_type):
        """Przetwarza transkrypcję na opis medyczny."""

        # Przygotuj listę kodów do promptu
        icd_context = json.dumps(self.icd10_codes, indent=2, ensure_ascii=False)

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
                # Użyj session_key jeśli jest, w przeciwnym razie tokena z pliku
                auth_key = session_key if session_key and session_key.startswith("sk-ant-sid01-") else claude_token
                result_text = self._call_claude(auth_key, prompt)
            else:
                result_text = self._call_gemini(gemini_key, prompt)

            # Pokaż raw output w debug
            self.root.after(0, lambda rt=result_text: self._set_debug(rt))

            # Wyczyść markdown jeśli jest
            cleaned_text = result_text
            if cleaned_text.startswith("```"):
                cleaned_text = cleaned_text.split("```")[1]
                if cleaned_text.startswith("json"):
                    cleaned_text = cleaned_text[4:]
            cleaned_text = cleaned_text.strip()

            # Parsuj JSON
            result = json.loads(cleaned_text)

            # Formatuj rozpoznanie z kodem ICD-10
            icd_code = result.get("icd10", "")
            diagnosis = result.get("rozpoznanie", "-")
            
            if icd_code and icd_code != "-":
                # Pobierz opis z bazy jeśli dostępny, lub użyj tego z JSON
                icd_desc = self.icd10_codes.get(icd_code, "")
                final_diagnosis = f"[{icd_code}] {diagnosis}"
            else:
                final_diagnosis = diagnosis

            # Nadpisz w obiekcie wynikowym dla UI
            result["rozpoznanie"] = final_diagnosis

            # Aktualizuj UI
            self.root.after(0, lambda: self._set_results(result))

        except json.JSONDecodeError as e:
            self.root.after(0, lambda: messagebox.showerror("Błąd", f"JSON parse error: {str(e)}"))
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda em=error_msg: self._set_debug(f"ERROR: {em}"))
            self.root.after(0, lambda em=error_msg: messagebox.showerror("Błąd", f"Błąd: {em}"))
        finally:
            # Zawsze przywróć stan UI
            self.root.after(0, lambda: self._set_loading_state(False))

    def _reset_chat(self):
        """Resetuje historię czatu w Claude."""
        if not PROXY_AVAILABLE:
            return
            
        try:
            # Wywołaj endpoint DELETE na proxy
            import requests
            port = getattr(self, "_proxy_port", 8765)
            url = f"http://127.0.0.1:{port}/uuid"
            requests.delete(url, timeout=2)
            
            self.chat_uuid = None
            self._save_config()
            messagebox.showinfo("Info", "Historia czatu została wyczyszczona.")
        except Exception as e:
            messagebox.showwarning("Błąd", f"Nie udało się zresetować czatu: {e}")

    def _fetch_current_uuid(self):
        """Pobiera aktualne UUID z proxy."""
        try:
            import requests
            port = getattr(self, "_proxy_port", 8765)
            url = f"http://127.0.0.1:{port}/uuid"
            resp = requests.get(url, timeout=1)
            if resp.status_code == 200:
                data = resp.json()
                new_uuid = data.get("uuid")
                if new_uuid and new_uuid != self.chat_uuid:
                    self.chat_uuid = new_uuid
                    self._save_config()
        except:
            pass

    def _call_claude(self, auth_token, prompt):
        """Wywołuje Claude przez proxy do claude.ai."""
        import os
        import time
        import io
        import sys

        if not auth_token:
             raise ValueError("Brak tokena/klucza Claude!")

        # Uruchom proxy jeśli jeszcze nie działa
        if not hasattr(self, '_proxy_started') or not self._proxy_started:
            # Wycisz printy z proxy (mają emoji które nie działają na Windows)
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                # Przekazujemy token - proxy samo rozpozna czy to sessionKey czy OAuth
                # Przekazujemy też chat_uuid z konfiguracji (resume session)
                success, port = start_proxy_server(auth_token, port=8765, conversation_uuid=self.chat_uuid)
            finally:
                sys.stdout = old_stdout

            if success:
                self._proxy_started = True
                self._proxy_port = port
                os.environ["ANTHROPIC_BASE_URL"] = get_proxy_base_url(port)
                time.sleep(2)  # Daj czas proxy
            else:
                raise Exception("Nie udalo sie uruchomic proxy")

        # Użyj Anthropic SDK przez proxy
        # Używamy auth_token jako api_key dla SDK (proxy go zignoruje, ale SDK wymaga)
        client = Anthropic(api_key=auth_token)

        # Proxy zawsze zwraca stream, więc musimy go obsłużyć
        stream = client.messages.create(
            model="claude-sonnet-4-20250514", # Model zostanie podmieniony przez claude.ai na webowy
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
        
        # Po zakończeniu generowania, pobierz aktualne UUID (bo proxy mogło utworzyć nowe)
        self._fetch_current_uuid()

        return full_text.strip()

    def _call_gemini(self, api_key, prompt):
        """Wywołuje Gemini API."""
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        return response.text.strip()

    def _set_debug(self, text):
        """Ustawia tekst w polu debug."""
        self.debug_text.delete("1.0", tk.END)
        self.debug_text.insert("1.0", text)

    def _set_results(self, result):
        """Ustawia wyniki w polach tekstowych."""
        self.recognition_text.delete("1.0", tk.END)
        self.recognition_text.insert("1.0", result.get("rozpoznanie", "-"))

        self.service_text.delete("1.0", tk.END)
        self.service_text.insert("1.0", result.get("swiadczenie", "-"))

        self.procedure_text.delete("1.0", tk.END)
        self.procedure_text.insert("1.0", result.get("procedura", "-"))


def main():
    root = tk.Tk()
    app = StomatologApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
