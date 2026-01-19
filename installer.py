import os
import sys
import subprocess
import urllib.request
import zipfile
import shutil
import time
import json
from pathlib import Path
from datetime import datetime

# Konfiguracja
REPO_URL = "https://github.com/guziczak/wywiady/archive/refs/heads/main.zip"
REPO_API_COMMIT = "https://api.github.com/repos/guziczak/wywiady/commits/main"
APP_NAME = "AsystentMedyczny"
MAIN_SCRIPT = "stomatolog_nicegui.py"
ICON_REL_PATH = os.path.join("extension", "icon.png")
STATE_FILE = ".install_state.json"

def print_step(msg):
    print(f"\n[*] {msg}")

def print_error(msg):
    print(f"\n[!] BLAD: {msg}")
    input("Nacisnij ENTER aby zakonczyc...")
    sys.exit(1)

def get_remote_commit():
    try:
        req = urllib.request.Request(
            REPO_API_COMMIT,
            headers={"User-Agent": f"{APP_NAME}-installer"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("sha")
    except Exception:
        return None

def read_state(path):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def write_state(path, state):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass

def write_build_info(path, info):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2)
    except Exception:
        pass

def ensure_pdf_fonts(install_dir):
    fonts_dir = os.path.join(install_dir, "assets", "fonts")
    os.makedirs(fonts_dir, exist_ok=True)
    font_urls = {
        "DejaVuSans.ttf": "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/version-2.37/ttf/DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf": "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/version-2.37/ttf/DejaVuSans-Bold.ttf",
    }
    fallback_fonts = {
        "DejaVuSans.ttf": os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "arial.ttf"),
        "DejaVuSans-Bold.ttf": os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "arialbd.ttf"),
    }

    for fname, url in font_urls.items():
        fpath = os.path.join(fonts_dir, fname)
        try:
            if os.path.exists(fpath) and os.path.getsize(fpath) > 100_000:
                continue
        except OSError:
            pass
        print(f"    [WARN] Brak czcionki {fname} - pobieram...")
        try:
            urllib.request.urlretrieve(url, fpath)
            continue
        except Exception:
            print(f"    [WARN] Nie udalo sie pobrac {fname}.")
        # Fallback to Windows Arial if available
        fallback = fallback_fonts.get(fname)
        if fallback and os.path.exists(fallback):
            try:
                shutil.copy(fallback, fpath)
                print(f"    [WARN] Uzywam fallback fontu z systemu Windows dla {fname}.")
            except Exception:
                pass

def _human_bytes(num):
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024

def _write_progress(line):
    last_len = getattr(_write_progress, "_last_len", 0)
    pad = " " * max(0, last_len - len(line))
    # Write + clear tail + rewrite to keep cursor at end
    sys.stdout.write("\r" + line + pad + "\r" + line)
    sys.stdout.flush()
    _write_progress._last_len = max(len(line), last_len)

def print_progress(prefix, current, total, width=30):
    if total and total > 0:
        ratio = min(max(current / total, 0), 1)
        filled = int(width * ratio)
        bar = "#" * filled + "-" * (width - filled)
        percent = int(ratio * 100)
        _write_progress(
            f"{prefix} [{bar}] {percent}% ({_human_bytes(current)}/{_human_bytes(total)})"
        )
    else:
        spinner = "|/-\\"
        idx = getattr(print_progress, "_spin", 0)
        print_progress._spin = (idx + 1) % len(spinner)
        _write_progress(f"{prefix} {spinner[idx]} {_human_bytes(current)}")

def run_with_spinner(cmd, label):
    spinner = "|/-\\"
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    idx = 0
    while True:
        try:
            out, _ = proc.communicate(timeout=0.1)
            break
        except subprocess.TimeoutExpired:
            sys.stdout.write(f"\r{label} {spinner[idx % len(spinner)]}")
            sys.stdout.flush()
            idx += 1
    sys.stdout.write(f"\r{label} OK\n")
    sys.stdout.flush()
    if proc.returncode != 0:
        details = out.strip() if out else "Brak szczegolow."
        print_error(f"{label} nieudane:\n{details}")


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
    state_path = os.path.join(install_dir, STATE_FILE)
    state = read_state(state_path)
    remote_commit = get_remote_commit()
    if remote_commit:
        print_step(f"Wersja zdalna: {remote_commit[:7]}")
    else:
        print_step("Nie udalo sie pobrac wersji zdalnej (API)")
    skip_download = False
    if remote_commit and state.get("commit") == remote_commit and os.path.exists(MAIN_SCRIPT):
        print_step("Wersja jest aktualna. Pomijam pobieranie.")
        skip_download = True

    zip_path = "repo.zip"
    try:
        if not skip_download:
            print_step("Pobieranie najnowszej wersji aplikacji...")
            def _download_hook(block_num, block_size, total_size):
                downloaded = block_num * block_size
                print_progress("    Pobieranie", downloaded, total_size)

            urllib.request.urlretrieve(REPO_URL, zip_path, reporthook=_download_hook)
            print()  # newline after progress
    except Exception as e:
        print_error(f"Nie udalo sie pobrac plikow: {e}")

    # 4. Rozpakowywanie
    try:
        if not skip_download:
            print_step("Rozpakowywanie...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                members = zip_ref.infolist()
                total = len(members)
                for i, member in enumerate(members, 1):
                    zip_ref.extract(member, ".")
                    print_progress("    Rozpakowywanie", i, total)
                print()  # newline after progress
            
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
            ensure_pdf_fonts(install_dir)
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
    need_install = (not os.path.exists("venv")) or (not skip_download)
    if need_install:
        print_step("Instalowanie bibliotek (moze to potrwac)...")
        venv_python = os.path.join("venv", "Scripts", "python.exe")
        try:
            # Uzyj python -m pip, zeby nie probowac nadpisac uruchomionego pip.exe
            run_with_spinner([venv_python, "-m", "pip", "install", "--upgrade", "pip"], "    Aktualizacja pip")
            run_with_spinner([venv_python, "-m", "pip", "install", "-r", "requirements.txt"], "    Instalacja bibliotek")
        except Exception as e:
            print_error(f"Blad instalacji bibliotek: {e}")

    # 6b. Fonty PDF (polskie znaki) - zawsze sprawdz
    print_step("Sprawdzanie czcionek PDF...")
    ensure_pdf_fonts(install_dir)

    # 7. Tworzenie skrotu (run_app.bat i Pulpit)
    print_step("Konfiguracja skrotow...")
    
    # run_app.bat
    run_bat_path = os.path.join(install_dir, "run_app.bat")
    with open(run_bat_path, "w") as f:
        f.write("@echo off\n")
        f.write(f"cd /d \"{install_dir}\"\n")
        f.write("call venv\\Scripts\\activate.bat\n")
        f.write("set WYWIAD_OPEN_LANDING=1\n")
        f.write("set WYWIAD_AUTO_OPEN=1\n")
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

    if remote_commit and not skip_download:
        write_state(state_path, {"commit": remote_commit})

    version_commit = remote_commit or state.get("commit") or "unknown"
    build_info_path = os.path.join(install_dir, "build_info.json")
    write_build_info(build_info_path, {
        "commit": version_commit,
        "downloaded_at": datetime.utcnow().isoformat() + "Z",
        "source": "github/main",
    })

    print("\n========================================================")
    print("   INSTALACJA ZAKONCZONA SUKCESEM!")
    print("========================================================")
    print(f"Wersja: {version_commit[:7] if version_commit else 'unknown'}")
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
