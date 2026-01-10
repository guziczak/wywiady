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


class StomatologApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Wywiad Stomatologiczny")
        self.root.geometry("700x800")
        self.root.resizable(True, True)

        # Stan nagrywania
        self.is_recording = False
        self.audio_data = []
        self.sample_rate = 16000

        self._create_widgets()
        self._load_config()

        # Zapisz config przy zamknięciu
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_config(self):
        """Ładuje zapisaną konfigurację."""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                    self.api_key_var.set(config.get("api_key", ""))
        except:
            pass

    def _save_config(self):
        """Zapisuje konfigurację."""
        try:
            config = {"api_key": self.api_key_var.get()}
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f)
        except:
            pass

    def _on_close(self):
        """Obsługuje zamknięcie okna."""
        self._save_config()
        self.root.destroy()

    def _create_widgets(self):
        # Główny kontener z paddingiem
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # === SEKCJA API KEY ===
        api_frame = ttk.LabelFrame(main_frame, text="Konfiguracja API", padding="5")
        api_frame.pack(fill=tk.X, pady=(0, 10))

        # Link do API keys
        link_label = ttk.Label(
            api_frame,
            text="Pobierz API key z Google AI Studio",
            foreground="blue",
            cursor="hand2"
        )
        link_label.pack(anchor=tk.W)
        link_label.bind("<Button-1>", lambda e: webbrowser.open("https://aistudio.google.com/app/apikey?hl=pl"))

        # Pole na API key
        key_row = ttk.Frame(api_frame)
        key_row.pack(fill=tk.X, pady=(5, 0))

        ttk.Label(key_row, text="API Key:").pack(side=tk.LEFT)
        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(key_row, textvariable=self.api_key_var, width=50, show="*")
        self.api_key_entry.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)

        # Checkbox do pokazania klucza
        self.show_key_var = tk.BooleanVar()
        ttk.Checkbutton(
            key_row,
            text="Pokaż",
            variable=self.show_key_var,
            command=self._toggle_key_visibility
        ).pack(side=tk.LEFT, padx=(5, 0))

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

        ttk.Button(
            trans_btn_row,
            text="📋 Kopiuj",
            command=lambda: self._copy_to_clipboard(self.transcript_text)
        ).pack(side=tk.RIGHT)

        ttk.Button(
            trans_btn_row,
            text="🗑️ Wyczyść",
            command=lambda: self.transcript_text.delete("1.0", tk.END)
        ).pack(side=tk.RIGHT, padx=(0, 5))

        self.transcript_text = tk.Text(trans_frame, height=6, wrap=tk.WORD)
        self.transcript_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        # === PRZYCISK GENEROWANIA ===
        ttk.Button(
            main_frame,
            text="⚡ Generuj opis",
            command=self._generate_description
        ).pack(pady=10)

        # === DEBUG - RAW OUTPUT ===
        debug_frame = ttk.LabelFrame(main_frame, text="Debug - Raw output z Gemini", padding="5")
        debug_frame.pack(fill=tk.X, pady=(0, 10))

        debug_btn_row = ttk.Frame(debug_frame)
        debug_btn_row.pack(fill=tk.X)

        ttk.Button(
            debug_btn_row,
            text="📋 Kopiuj",
            command=lambda: self._copy_to_clipboard(self.debug_text)
        ).pack(side=tk.RIGHT)

        self.debug_text = tk.Text(debug_frame, height=4, wrap=tk.WORD, bg="#f0f0f0")
        self.debug_text.pack(fill=tk.X, pady=(5, 0))

        # === SEKCJA WYNIKÓW ===
        results_frame = ttk.LabelFrame(main_frame, text="Wygenerowany opis", padding="5")
        results_frame.pack(fill=tk.BOTH, expand=True)

        # Rozpoznanie
        self._create_result_field(results_frame, "Rozpoznanie:", "recognition")

        # Świadczenie
        self._create_result_field(results_frame, "Świadczenie:", "service")

        # Procedura
        self._create_result_field(results_frame, "Procedura:", "procedure")

    def _create_result_field(self, parent, label_text, attr_name):
        """Tworzy pole wynikowe z etykietą i przyciskiem kopiowania."""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        header = ttk.Frame(frame)
        header.pack(fill=tk.X)

        ttk.Label(header, text=label_text, font=("", 9, "bold")).pack(side=tk.LEFT)

        text_widget = tk.Text(frame, height=3, wrap=tk.WORD)
        text_widget.pack(fill=tk.BOTH, expand=True, pady=(2, 0))

        ttk.Button(
            header,
            text="📋 Kopiuj",
            command=lambda: self._copy_to_clipboard(text_widget)
        ).pack(side=tk.RIGHT)

        setattr(self, f"{attr_name}_text", text_widget)

    def _toggle_key_visibility(self):
        """Przełącza widoczność klucza API."""
        self.api_key_entry.config(show="" if self.show_key_var.get() else "*")

    def _copy_to_clipboard(self, text_widget):
        """Kopiuje zawartość pola tekstowego do schowka."""
        content = text_widget.get("1.0", tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            messagebox.showinfo("Sukces", "Skopiowano do schowka!")

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
        """Wysyła audio do Gemini i otrzymuje transkrypcję."""
        api_key = self.api_key_var.get().strip()

        if not api_key:
            self._update_status("Status: Brak API key!")
            return

        if genai is None:
            self._update_status("Status: Brak biblioteki google-genai!")
            return

        try:
            client = genai.Client(api_key=api_key)

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

            # Aktualizuj UI
            self.root.after(0, lambda: self._set_transcript(transcript))
            self._update_status("Status: Gotowy")

        except Exception as e:
            self._update_status(f"Status: Błąd - {str(e)[:50]}")
        finally:
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
        api_key = self.api_key_var.get().strip()
        transcript = self.transcript_text.get("1.0", tk.END).strip()

        if not api_key:
            messagebox.showerror("Błąd", "Wprowadź API key!")
            return

        if not transcript:
            messagebox.showerror("Błąd", "Brak transkrypcji do przetworzenia!")
            return

        if genai is None:
            messagebox.showerror("Błąd", "Brak biblioteki google-genai!\nZainstaluj: pip install google-genai")
            return

        # Przetwarzaj w tle
        threading.Thread(
            target=self._process_transcript,
            args=(api_key, transcript),
            daemon=True
        ).start()

    def _process_transcript(self, api_key, transcript):
        """Przetwarza transkrypcję na opis medyczny."""
        try:
            client = genai.Client(api_key=api_key)

            prompt = f"""Jesteś asystentem do formatowania dokumentacji stomatologicznej.
Twoim zadaniem jest przekształcenie surowych notatek z wywiadu z pacjentem na sformatowany tekst dokumentacji.

NIE udzielasz porad medycznych - jedynie formatujesz i porządkujesz informacje podane przez stomatologa.

Na podstawie poniższej transkrypcji wywiadu, wyodrębnij i sformatuj:

1. ROZPOZNANIE - diagnoza/problem stomatologiczny
2. ŚWIADCZENIE - wykonane lub planowane zabiegi
3. PROCEDURA - szczegółowy opis procedury/postępowania

Transkrypcja wywiadu:
{transcript}

Odpowiedz w formacie JSON:
{{"rozpoznanie": "...", "swiadczenie": "...", "procedura": "..."}}

Jeśli jakieś pole nie wynika z wywiadu, wpisz "-".
Odpowiedz TYLKO JSON-em, bez dodatkowego tekstu."""

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            result_text = response.text.strip()

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
            import json
            result = json.loads(cleaned_text)

            # Aktualizuj UI
            self.root.after(0, lambda: self._set_results(result))

        except json.JSONDecodeError as e:
            self.root.after(0, lambda: messagebox.showerror("Błąd", f"JSON parse error: {str(e)}"))
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda em=error_msg: self._set_debug(f"ERROR: {em}"))
            self.root.after(0, lambda em=error_msg: messagebox.showerror("Błąd", f"Błąd: {em}"))

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
