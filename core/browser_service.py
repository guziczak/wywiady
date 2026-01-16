import os
import sys
import json
import time
import shutil
import tempfile
import subprocess
import base64
import sqlite3
import winreg
from pathlib import Path
from typing import Optional, List, Dict

# Importy zaleznosci (Selenium, Cryptography)
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    from webdriver_manager.firefox import GeckoDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    import browser_cookie3
    BROWSER_COOKIE3_AVAILABLE = True
except ImportError:
    BROWSER_COOKIE3_AVAILABLE = False

try:
    from Crypto.Cipher import AES
    import win32crypt
    DECRYPTION_AVAILABLE = True
except ImportError:
    DECRYPTION_AVAILABLE = False


class BrowserService:
    def __init__(self):
        pass

    def get_default_browser(self) -> Optional[str]:
        """Wykrywa domyślną przeglądarkę z rejestru Windows."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice") as key:
                prog_id = winreg.QueryValueEx(key, "ProgId")[0].lower()
                if "chrome" in prog_id: return "chrome"
                elif "firefox" in prog_id: return "firefox"
                elif "edge" in prog_id or "msedge" in prog_id: return "edge"
                elif "opera" in prog_id: return "opera"
                elif "brave" in prog_id: return "brave"
        except Exception as e:
            print(f"[BROWSER] Nie mozna wykryc domyslnej przegladarki: {e}", flush=True)
        return None

    def get_browser_profile_path(self, browser: str) -> Optional[str]:
        """Zwraca ścieżkę do profilu użytkownika dla danej przeglądarki."""
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        app_data = os.environ.get("APPDATA", "")

        paths = {
            "chrome": os.path.join(local_app_data, "Google", "Chrome", "User Data"),
            "edge": os.path.join(local_app_data, "Microsoft", "Edge", "User Data"),
            "brave": os.path.join(local_app_data, "BraveSoftware", "Brave-Browser", "User Data"),
            "opera": os.path.join(app_data, "Opera Software", "Opera Stable"),
            "firefox": os.path.join(app_data, "Mozilla", "Firefox", "Profiles"),
        }

        profile_path = paths.get(browser)
        if profile_path and os.path.exists(profile_path):
            return profile_path
        return None

    def launch_edge_with_extension(self, extension_path: str, target_url: str, app_url: str):
        """
        Uruchamia Edge z załadowanym rozszerzeniem (metoda --load-extension).
        Zamyka inne instancje Edge przed uruchomieniem.
        """
        print("[BROWSER] Restartuję Edge...", flush=True)
        
        # 1. Zabij Edge
        try:
            subprocess.run(["taskkill", "/F", "/IM", "msedge.exe"], 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL)
            time.sleep(2)
        except Exception:
            pass

        # 2. Uruchom Edge z flagą
        try:
            cmd = [
                "start", "msedge",
                f"--load-extension={extension_path}",
                target_url,
                app_url
            ]
            # shell=True pozwala na uzycie "start"
            subprocess.Popen(cmd, shell=True)
            print("[BROWSER] Otwarto Edge z rozszerzeniem.", flush=True)
        except Exception as e:
            print(f"[BROWSER] Błąd uruchamiania Edge: {e}", flush=True)
            raise e

    # --- Sekcja Cookies & Decryption (dla starszych metod, jeśli potrzebne) ---

    def _get_edge_encryption_key(self) -> Optional[bytes]:
        """Pobiera klucz szyfrowania cookies z Local State Edge."""
        if not DECRYPTION_AVAILABLE:
            return None
        
        try:
            local_state_path = os.path.join(
                os.environ.get("LOCALAPPDATA", ""),
                "Microsoft", "Edge", "User Data", "Local State"
            )
            
            if not os.path.exists(local_state_path):
                return None

            with open(local_state_path, "r", encoding="utf-8") as f:
                local_state = json.load(f)
            
            encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
            encrypted_key = encrypted_key[5:] # Remove DPAPI prefix
            
            return win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        except Exception as e:
            print(f"[BROWSER] Blad klucza szyfrowania: {e}", flush=True)
            return None

    def _decrypt_cookie_value(self, encrypted_value: bytes, key: bytes) -> Optional[str]:
        """Odszyfrowuje wartość ciasteczka (AES-GCM)."""
        if not DECRYPTION_AVAILABLE:
            return None
            
        try:
            nonce = encrypted_value[3:15]
            ciphertext = encrypted_value[15:]
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            decrypted = cipher.decrypt_and_verify(ciphertext[:-16], ciphertext[-16:])
            return decrypted.decode('utf-8')
        except Exception:
            return None

    def extract_claude_session_key_from_cookies(self) -> Optional[str]:
        """
        Próbuje wyciągnąć sessionKey z ciasteczek Edge (metoda bezpośrednia).
        Wymaga zamkniętego Edge.
        """
        if not DECRYPTION_AVAILABLE:
            print("[BROWSER] Brak bibliotek do deszyfrowania cookies", flush=True)
            return None

        print("[BROWSER] Próba odczytu cookies (Direct)...", flush=True)
        
        cookies_path = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Microsoft", "Edge", "User Data", "Default", "Network", "Cookies"
        )
        
        if not os.path.exists(cookies_path):
            # Starsza sciezka
            cookies_path = os.path.join(
                os.environ.get("LOCALAPPDATA", ""),
                "Microsoft", "Edge", "User Data", "Default", "Cookies"
            )

        if not os.path.exists(cookies_path):
            return None

        key = self._get_edge_encryption_key()
        if not key:
            return None

        # Kopiuj do temp
        temp_cookies = os.path.join(tempfile.gettempdir(), f"edge_cookies_{os.getpid()}")
        try:
            shutil.copy2(cookies_path, temp_cookies)
        except Exception:
            return None

        conn = None
        session_key = None
        try:
            conn = sqlite3.connect(temp_cookies, timeout=5)
            cursor = conn.cursor()
            
            # Query
            cursor.execute(
                "SELECT encrypted_value FROM cookies WHERE host_key LIKE '%claude.ai%' AND name='sessionKey'"
            )
            row = cursor.fetchone()
            
            if row:
                encrypted_value = row[0]
                session_key = self._decrypt_cookie_value(encrypted_value, key)
        except Exception as e:
            print(f"[BROWSER] Blad SQL: {e}", flush=True)
        finally:
            if conn: conn.close()
            try:
                os.unlink(temp_cookies)
            except: pass
            
        return session_key
