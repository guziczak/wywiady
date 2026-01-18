"""
Model Loader.
Klasa zarzadzajaca ladowaniem modeli w osobnym procesie
ORAZ skrypt workera uruchamiany przez ten proces.
"""
import sys
import json
import traceback
import subprocess
import threading
import time
from typing import Optional, Callable

# === CZĘŚĆ SKRYPTU WORKERA (Uruchamiana w subprocess) ===

def run_worker_process():
    """Główna funkcja procesu workera."""
    print(f"[LOADER] Started with args: {sys.argv}", flush=True)

    if len(sys.argv) != 3:
        result = {"success": False, "error": "Usage: model_loader.py <model_path> <device>"}
        print(f"RESULT:{json.dumps(result)}", flush=True)
        sys.exit(1)

    model_path = sys.argv[1]
    device = sys.argv[2]

    try:
        print(f"[LOADER] Importing openvino_genai...", flush=True)
        import openvino_genai as ov_genai

        print(f"[LOADER] Loading model: {model_path}", flush=True)
        print(f"[LOADER] Device: {device}", flush=True)
        print(f"[LOADER] Creating WhisperPipeline...", flush=True)

        # Ta operacja moze trwac 1-2 minuty i blokuje GIL, dlatego osobny proces
        pipeline = ov_genai.WhisperPipeline(model_path, device)

        print("[LOADER] Model loaded successfully!", flush=True)
        result = {"success": True, "error": None}

    except Exception as e:
        print(f"[LOADER] Error: {e}", flush=True)
        print(f"[LOADER] Traceback: {traceback.format_exc()}", flush=True)
        result = {"success": False, "error": str(e)}

    # Wypisz JSON na stdout (komunikacja z procesem-matką)
    print(f"RESULT:{json.dumps(result)}", flush=True)
    sys.exit(0 if result["success"] else 1)


# === CZĘŚĆ MODUŁU (Klasa ModelLoader) ===

class ModelLoader:
    """
    Zarządza ładowaniem modelu w osobnym procesie.
    Pozwala na anulowanie ładowania (kill process).
    """
    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._is_loading = False

    def load_model_subprocess(self, model_path: str, device: str, on_complete: Optional[Callable] = None) -> bool:
        """
        Uruchamia ładowanie w podprocesie.
        Blokuje dopóki proces nie zwróci wyniku lub nie zostanie zabity.
        """
        self._is_loading = True
        
        # Ścieżka do tego samego pliku
        script_path = __file__
        
        cmd = [sys.executable, script_path, model_path, device]
        print(f"[LOADER] Starting subprocess: {cmd}", flush=True)

        try:
            # Start process
            # Używamy CREATE_NO_WINDOW na Windows żeby nie wyskakiwało okno konsoli
            creationflags = 0
            if sys.platform == 'win32':
                creationflags = subprocess.CREATE_NO_WINDOW

            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                creationflags=creationflags
            )

            # Czekaj na wynik (czytamy stdout linia po linii)
            result_json = None
            while True:
                if self._process.poll() is not None:
                    break # Proces padł
                
                line = self._process.stdout.readline()
                if not line:
                    break
                
                line = line.strip()
                if line:
                    print(f"[SUBPROCESS] {line}", flush=True)
                    if line.startswith("RESULT:"):
                        try:
                            json_str = line[7:]
                            result_json = json.loads(json_str)
                        except:
                            pass

            self._process.wait()
            
            if result_json and result_json.get("success"):
                print("[LOADER] Subprocess success.", flush=True)
                if on_complete: on_complete(True)
                return True
            else:
                print(f"[LOADER] Subprocess failed or no result.", flush=True)
                if on_complete: on_complete(False)
                return False

        except Exception as e:
            print(f"[LOADER] Subprocess error: {e}", flush=True)
            if on_complete: on_complete(False)
            return False
        finally:
            self._is_loading = False
            self._process = None

    def cancel(self):
        """Anuluje ładowanie (zabija proces)."""
        if self._process and self._is_loading:
            print("[LOADER] Killing subprocess...", flush=True)
            try:
                self._process.kill()
                self._process.wait(timeout=2)
            except:
                pass
            self._is_loading = False
            self._process = None


if __name__ == "__main__":
    # Jeśli uruchomiony jako skrypt -> działaj jako worker
    run_worker_process()