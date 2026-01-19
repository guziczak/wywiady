import os
import sys
import subprocess
import urllib.request
import zipfile
import shutil
import time
from pathlib import Path

# Konfiguracja
REPO_URL = "https://github.com/guziczak/wywiady/archive/refs/heads/main.zip"
APP_NAME = "AsystentMedyczny"
MAIN_SCRIPT = "stomatolog_nicegui.py"
ICON_REL_PATH = os.path.join("extension", "icon.png")

def print_step(msg):
    print(f"\n[*] {msg}")

def print_error(msg):
    print(f"\n[!] BLAD: {msg}")
    input("Nacisnij ENTER aby zakonczyc...")
    sys.exit(1)

def check_python():
    print_step("Sprawdzanie instalacji Python w systemie...")
    try:
        # Sprawdzamy czy python jest w PATH
        subprocess.check_call(["python", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("    Python znaleziony.")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error("Nie znaleziono Pythona!\n"                    "Prosze zainstalowac Python 3.10+ ze strony python.org.\n"                    "PAMIETAJ aby zaznaczyc opcje 'Add Python to PATH' podczas instalacji.")

def main():
    print("========================================================")
    print(f"   INSTALATOR {APP_NAME.upper()}")
    print("========================================================")

    # 1. Sprawdz Pythona (tego systemowego, ktory bedzie uruchamial apke)
    check_python()

    # 2. Ustal sciezki
    app_data = os.environ.get("LOCALAPPDATA")
    install_dir = os.path.join(app_data, APP_NAME)
    
    print_step(f"Katalog instalacyjny: {install_dir}")
    
    if not os.path.exists(install_dir):
        os.makedirs(install_dir)
    
    os.chdir(install_dir)

    # 3. Pobieranie
    print_step("Pobieranie najnowszej wersji aplikacji...")
    zip_path = "repo.zip"
    try:
        urllib.request.urlretrieve(REPO_URL, zip_path)
    except Exception as e:
        print_error(f"Nie udalo sie pobrac plikow: {e}")

    # 4. Rozpakowywanie
    print_step("Rozpakowywanie...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(".")
        
        # Przenoszenie z podkatalogu wywiady-main
        extracted_folder = "wywiady-main"
        if os.path.exists(extracted_folder):
            for item in os.listdir(extracted_folder):
                s = os.path.join(extracted_folder, item)
                d = os.path.join(".", item)
                if os.path.exists(d):
                    if os.path.isdir(d):
                        shutil.rmtree(d)
                    else:
                        os.remove(d)
                shutil.move(s, d)
            os.rmdir(extracted_folder)
        
        os.remove(zip_path)
    except Exception as e:
        print_error(f"Blad podczas rozpakowywania: {e}")

    # 5. Venv
    if not os.path.exists("venv"):
        print_step("Tworzenie wirtualnego srodowiska (venv)...")
        try:
            subprocess.check_call(["python", "-m", "venv", "venv"])
        except Exception as e:
            print_error(f"Nie udalo sie stworzyc venv: {e}")

    # 6. Instalacja zaleznosci
    print_step("Instalowanie bibliotek (moze to potrwac)...")
    pip_exe = os.path.join("venv", "Scripts", "pip")
    try:
        subprocess.check_call([pip_exe, "install", "--upgrade", "pip"])
        subprocess.check_call([pip_exe, "install", "-r", "requirements.txt"])
    except Exception as e:
        print_error(f"Blad instalacji bibliotek: {e}")

    # 7. Tworzenie skrotu (run_app.bat i Pulpit)
    print_step("Konfiguracja skrotow...")
    
    # run_app.bat
    run_bat_path = os.path.join(install_dir, "run_app.bat")
    with open(run_bat_path, "w") as f:
        f.write("@echo off\n")
        f.write(f"cd /d \"{install_dir}\"\n")
        f.write("call venv\\Scripts\\activate.bat\n")
        f.write(f"python {MAIN_SCRIPT}\n")
        f.write("pause\n")

    # Skrót na pulpicie (za pomoca PowerShell, zeby nie zalezec od win32com w instalatorze)
    desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
    shortcut_path = os.path.join(desktop, "Asystent Medyczny.lnk")
    icon_path = os.path.join(install_dir, ICON_REL_PATH)
    
    ps_script = f"""
    $s=(New-Object -COM WScript.Shell).CreateShortcut('{shortcut_path}');
    $s.TargetPath='{run_bat_path}';
    $s.WorkingDirectory='{install_dir}';
    $s.IconLocation='{icon_path}';
    $s.Save()
    """
    subprocess.run(["powershell", "-Command", ps_script], capture_output=True)

    print("\n========================================================")
    print("   INSTALACJA ZAKONCZONA SUKCESEM!")
    print("========================================================")
    print(f"Skrot utworzony na pulpicie: {shortcut_path}")
    print("Uruchamianie aplikacji za 3 sekundy...")
    time.sleep(3)
    
    subprocess.Popen([run_bat_path], shell=True)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit()
    except Exception as e:
        print_error(f"Wystapil nieoczekiwany blad: {e}")
