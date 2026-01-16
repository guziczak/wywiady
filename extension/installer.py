"""
Automatyczny instalator rozszerzenia Wywiad+ przez Windows Registry Policy.
Uruchom jako Administrator!
"""
import os
import sys
import json
import zipfile
import hashlib
import struct
import subprocess
import threading
import time
import winreg
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# Konfiguracja
EXTENSION_ID = "wywiadplusclaudeconnector"  # Zostanie obliczony z klucza
SERVER_PORT = 8090  # Port dla serwera rozszerzenia (aplikacja uzywa 8089)
REGISTRY_PATH = r"SOFTWARE\Policies\Microsoft\Edge\ExtensionInstallForcelist"

class ExtensionInstaller:
    def __init__(self):
        self.extension_dir = Path(__file__).parent
        self.crx_path = self.extension_dir / "wywiad_plus.crx"
        self.manifest_path = self.extension_dir / "update_manifest.xml"
        self.server = None
        self.server_thread = None

    def create_crx(self):
        """Pakuje rozszerzenie do formatu CRX3."""
        print("[1/5] Pakuje rozszerzenie do .crx...")

        # Stworz ZIP z plikami rozszerzenia
        zip_path = self.extension_dir / "extension.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file in ['manifest.json', 'background.js', 'content.js', 'icon.png']:
                file_path = self.extension_dir / file
                if file_path.exists():
                    zf.write(file_path, file)

        # Dla uproszczenia - uzyj niezpodpisanego CRX (Edge przyjmie przez policy)
        # W produkcji nalezy podpisac kluczem RSA
        with open(zip_path, 'rb') as f:
            zip_data = f.read()

        # CRX3 header (uproszczony - bez podpisu)
        # Edge z policy zaakceptuje nawet niepodpisane rozszerzenie
        crx_header = b'Cr24'  # Magic
        crx_header += struct.pack('<I', 3)  # Version 3
        crx_header += struct.pack('<I', 0)  # Header length (no signed data)

        with open(self.crx_path, 'wb') as f:
            f.write(crx_header)
            f.write(zip_data)

        # Cleanup
        zip_path.unlink()

        # Oblicz ID rozszerzenia (hash pierwszych 16 bajtow klucza publicznego)
        # Dla unpacked extension uzywamy hash sciezki
        hash_input = str(self.extension_dir).lower().encode('utf-8')
        hash_bytes = hashlib.sha256(hash_input).digest()[:16]
        extension_id = ''.join(chr(ord('a') + (b % 26)) for b in hash_bytes)

        print(f"    Extension ID: {extension_id}")
        return extension_id

    def create_update_manifest(self, extension_id):
        """Tworzy plik XML manifest dla Edge policy."""
        print("[2/5] Tworze update manifest...")

        xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<gupdate xmlns="http://www.google.com/update2/response" protocol="2.0">
  <app appid="{extension_id}">
    <updatecheck codebase="http://localhost:{SERVER_PORT}/wywiad_plus.crx" version="1.1"/>
  </app>
</gupdate>'''

        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)

    def start_server(self):
        """Uruchamia lokalny HTTP server do serwowania rozszerzenia."""
        print(f"[3/5] Uruchamiam serwer na porcie {SERVER_PORT}...")

        os.chdir(self.extension_dir)

        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Cisza

        self.server = HTTPServer(('localhost', SERVER_PORT), QuietHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

    def stop_server(self):
        """Zatrzymuje serwer."""
        if self.server:
            self.server.shutdown()

    def add_registry(self, extension_id):
        """Dodaje wpis do registry wymuszajacy instalacje rozszerzenia."""
        print("[4/5] Dodaje wpis do Registry (wymaga Admin)...")

        update_url = f"http://localhost:{SERVER_PORT}/update_manifest.xml"
        value = f"{extension_id};{update_url}"

        try:
            # Stworz klucz jesli nie istnieje
            key = winreg.CreateKeyEx(
                winreg.HKEY_LOCAL_MACHINE,
                REGISTRY_PATH,
                0,
                winreg.KEY_ALL_ACCESS
            )

            # Znajdz pierwszy wolny numer
            i = 1
            while True:
                try:
                    winreg.QueryValueEx(key, str(i))
                    i += 1
                except FileNotFoundError:
                    break

            winreg.SetValueEx(key, str(i), 0, winreg.REG_SZ, value)
            winreg.CloseKey(key)

            self.registry_value_name = str(i)
            print(f"    Dodano: {REGISTRY_PATH}\\{i}")
            return True

        except PermissionError:
            print("    BLAD: Brak uprawnien! Uruchom jako Administrator.")
            return False
        except Exception as e:
            print(f"    BLAD: {e}")
            return False

    def remove_registry(self):
        """Usuwa wpis z registry."""
        print("[CLEANUP] Usuwam wpis z Registry...")

        try:
            key = winreg.OpenKeyEx(
                winreg.HKEY_LOCAL_MACHINE,
                REGISTRY_PATH,
                0,
                winreg.KEY_ALL_ACCESS
            )
            winreg.DeleteValue(key, self.registry_value_name)
            winreg.CloseKey(key)
            print("    Usunieto.")
        except Exception as e:
            print(f"    Blad: {e}")

    def open_edge(self):
        """Otwiera Edge (rozszerzenie zainstaluje sie automatycznie)."""
        print("[5/5] Otwieram Edge...")
        subprocess.Popen(['start', 'msedge', 'https://claude.ai/'], shell=True)

    def wait_for_success(self, timeout=120):
        """Czeka az rozszerzenie wysle klucz do aplikacji."""
        print("\nCzekam na pobranie klucza (max 2 minuty)...")
        print("Zaloguj sie na claude.ai jesli nie jestes zalogowany.\n")

        # Sprawdzaj config.json co 2 sekundy
        config_path = self.extension_dir.parent / "config.json"
        start_time = time.time()
        initial_key = None

        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    initial_key = json.load(f).get('session_key', '')
            except:
                pass

        while time.time() - start_time < timeout:
            time.sleep(2)
            try:
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        current_key = json.load(f).get('session_key', '')
                    if current_key and current_key != initial_key:
                        return True
            except:
                pass

            # Pokaz progress
            elapsed = int(time.time() - start_time)
            print(f"\r    Oczekiwanie... {elapsed}s", end='', flush=True)

        print()
        return False

    def run(self):
        """Glowna funkcja instalatora."""
        print("=" * 50)
        print("  WYWIAD+ - INSTALATOR ROZSZERZENIA")
        print("=" * 50)
        print()

        # Sprawdz uprawnienia admin
        try:
            is_admin = os.getuid() == 0
        except AttributeError:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0

        if not is_admin:
            print("UWAGA: Potrzebne uprawnienia Administratora!")
            print("Uruchamiam ponownie z elevacja...\n")

            # Re-run jako admin
            import ctypes
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, f'"{__file__}"', None, 1
            )
            return

        try:
            extension_id = self.create_crx()
            self.create_update_manifest(extension_id)
            self.start_server()

            if not self.add_registry(extension_id):
                return

            self.open_edge()

            success = self.wait_for_success()

            if success:
                print("\n" + "=" * 50)
                print("  SUKCES! Klucz zostal pobrany.")
                print("=" * 50)
            else:
                print("\n" + "=" * 50)
                print("  TIMEOUT - nie udalo sie pobrac klucza.")
                print("  Sprawdz czy aplikacja Wywiad+ jest uruchomiona.")
                print("=" * 50)

        finally:
            self.remove_registry()
            self.stop_server()

            # Cleanup plikow
            try:
                self.crx_path.unlink()
                self.manifest_path.unlink()
            except:
                pass

        input("\nNacisnij Enter aby zamknac...")

if __name__ == "__main__":
    installer = ExtensionInstaller()
    installer.run()
