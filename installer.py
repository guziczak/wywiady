import os
import sys
import subprocess
import urllib.request
import traceback
import zipfile
import shutil
import time
import json
from datetime import datetime

# Konfiguracja
REPO_URL = "https://github.com/guziczak/wywiady/archive/refs/heads/main.zip"
REPO_API_COMMIT = "https://api.github.com/repos/guziczak/wywiady/commits/main"
APP_NAME = "AsystentMedyczny"
MAIN_SCRIPT = "stomatolog_nicegui.py"
ICON_REL_PATH = os.path.join("extension", "icon.png")
STATE_FILE = ".install_state.json"

SINK = None
QUICK_RESET_REQUESTED = False


class InstallerAbort(Exception):
    pass


class InstallerExit(Exception):
    def __init__(self, code: int = 0):
        super().__init__(str(code))
        self.code = code


def set_sink(sink) -> None:
    global SINK
    SINK = sink


def _sink():
    if SINK is None:
        set_sink(ConsoleSink())
    return SINK


def print_step(msg):
    _sink().step(msg)


def print_error(msg):
    _sink().error(msg)


def log_info(msg):
    _sink().info(msg)


def log_warn(msg):
    _sink().warn(msg)


def print_progress(prefix, current, total, width=30):
    _sink().progress(prefix, current, total, width)


def progress_done():
    _sink().progress_done()


def run_with_spinner(cmd, label):
    _sink().run_with_spinner(cmd, label)


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
        log_warn(f"    [WARN] Brak czcionki {fname} - pobieram...")
        try:
            urllib.request.urlretrieve(url, fpath)
            continue
        except Exception:
            log_warn(f"    [WARN] Nie udalo sie pobrac {fname}.")
        fallback = fallback_fonts.get(fname)
        if fallback and os.path.exists(fallback):
            try:
                shutil.copy(fallback, fpath)
                log_warn(f"    [WARN] Uzywam fallback fontu z systemu Windows dla {fname}.")
            except Exception:
                pass


def _human_bytes(num):
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024


def check_python():
    print_step("Sprawdzanie instalacji Python w systemie...")
    try:
        subprocess.check_call(["python", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log_info("    Python znaleziony.")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error("Nie znaleziono Pythona!\n"
                    "Prosze zainstalowac Python 3.10+ ze strony python.org.\n"
                    "PAMIETAJ aby zaznaczyc opcje 'Add Python to PATH' podczas instalacji.")


def kill_running_app():
    try:
        ps = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -like '*stomatolog_nicegui.py*' -or $_.CommandLine -like '*AsystentMedyczny*' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
        )
        subprocess.run(["powershell", "-Command", ps], capture_output=True)
    except Exception:
        pass


def reset_installation(install_dir):
    print_step("TRYB RESET: usuniecie calego folderu aplikacji")
    log_info(f"    Folder: {install_dir}")
    if not _sink().confirm("Wpisz TAK aby potwierdzic usuniecie:"):
        log_info("    Anulowano.")
        raise InstallerExit(0)

    kill_running_app()

    if os.path.exists(install_dir):
        try:
            shutil.rmtree(install_dir)
        except Exception:
            try:
                subprocess.run(
                    ["powershell", "-Command", f"Remove-Item -LiteralPath '{install_dir}' -Recurse -Force"],
                    capture_output=True
                )
            except Exception:
                pass

    print_step("RESET ZAKONCZONY")
    log_info("    Uruchom instalator ponownie aby zainstalowac od nowa.")
    raise InstallerExit(0)


def prompt_quick_reset(timeout_sec: float = 2.0) -> bool:
    global QUICK_RESET_REQUESTED
    if QUICK_RESET_REQUESTED:
        return True

    if not isinstance(_sink(), ConsoleSink):
        return False

    try:
        import msvcrt
    except Exception:
        return False

    if not sys.stdin.isatty():
        return False

    log_info("    Szybki reset: wpisz 'rst' w ciagu 2 sekund aby wyczyscic instalacje...")
    start = time.time()
    buf = ""
    while (time.time() - start) < timeout_sec:
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                break
            if ch == "\b":
                buf = buf[:-1]
                continue
            buf += ch
            try:
                sys.stdout.write(ch)
                sys.stdout.flush()
            except Exception:
                pass
            if buf.lower().endswith("rst"):
                log_info("")
                return True
        time.sleep(0.05)
    log_info("")
    return False


def get_install_dir() -> str:
    app_data = os.environ.get("LOCALAPPDATA")
    if not app_data:
        app_data = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(app_data, APP_NAME)


def run_installer(auto_launch: bool = True, result: dict | None = None):
    log_info("========================================================")
    log_info(f"   INSTALATOR {APP_NAME.upper()}")
    log_info("========================================================")

    check_python()

    install_dir = get_install_dir()

    if any(arg.lower() in ("--reset", "--wipe", "/reset", "/wipe") for arg in sys.argv[1:]):
        reset_installation(install_dir)
    elif prompt_quick_reset():
        reset_installation(install_dir)

    print_step(f"Katalog instalacyjny: {install_dir}")

    if not os.path.exists(install_dir):
        os.makedirs(install_dir)

    try:
        if str(sys.argv[0]).lower().endswith(".exe"):
            shutil.copy2(sys.argv[0], os.path.join(install_dir, "AsystentSetup.exe"))
    except Exception:
        pass

    os.chdir(install_dir)

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
            progress_done()
    except Exception as e:
        print_error(f"Nie udalo sie pobrac plikow: {e}")

    try:
        if not skip_download:
            print_step("Rozpakowywanie...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                members = zip_ref.infolist()
                total = len(members)
                for i, member in enumerate(members, 1):
                    zip_ref.extract(member, ".")
                    print_progress("    Rozpakowywanie", i, total)
                progress_done()

            extracted_folder = "wywiady-main"
            if os.path.exists(extracted_folder):
                preserve = {"models", "venv", "config.json", "logs"}
                for item in os.listdir(extracted_folder):
                    s = os.path.join(extracted_folder, item)
                    d = os.path.join(".", item)
                    if item in preserve and os.path.exists(d):
                        if os.path.isdir(s):
                            shutil.rmtree(s)
                        else:
                            os.remove(s)
                        log_info(f"    Pomijam {item} (zachowuje lokalne dane)")
                        continue
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

    if not os.path.exists("venv"):
        print_step("Tworzenie wirtualnego srodowiska (venv)...")
        try:
            subprocess.check_call(["python", "-m", "venv", "venv"])
        except Exception as e:
            print_error(f"Nie udalo sie stworzyc venv: {e}")

    need_install = (not os.path.exists("venv")) or (not skip_download)
    if need_install:
        print_step("Instalowanie bibliotek (moze to potrwac)...")
        venv_python = os.path.join("venv", "Scripts", "python.exe")
        try:
            run_with_spinner([venv_python, "-m", "pip", "install", "--upgrade", "pip"], "    Aktualizacja pip")
            run_with_spinner([venv_python, "-m", "pip", "install", "-r", "requirements.txt"], "    Instalacja bibliotek")
        except Exception as e:
            print_error(f"Blad instalacji bibliotek: {e}")

    print_step("Sprawdzanie czcionek PDF...")
    ensure_pdf_fonts(install_dir)

    print_step("Konfiguracja skrotow...")

    run_bat_path = os.path.join(install_dir, "run_app.bat")
    with open(run_bat_path, "w") as f:
        f.write("@echo off\n")
        f.write(f"cd /d \"{install_dir}\"\n")
        f.write("call venv\\Scripts\\activate.bat\n")
        f.write("set WYWIAD_AUTO_OPEN=1\n")
        f.write(f"python {MAIN_SCRIPT}\n")
        f.write("pause\n")

    run_vbs_path = os.path.join(install_dir, "run_app.vbs")
    pythonw_path = os.path.join(install_dir, "venv", "Scripts", "pythonw.exe")
    if os.path.exists(pythonw_path):
        vbs_cmd = f"\"{pythonw_path}\" \"{MAIN_SCRIPT}\""
        vbs_cmd = vbs_cmd.replace("\"", "\"\"")
        try:
            with open(run_vbs_path, "w", encoding="utf-8") as f:
                f.write('Set WshShell = CreateObject("WScript.Shell")\n')
                f.write(f'WshShell.CurrentDirectory = "{install_dir}"\n')
                f.write('WshShell.Environment("Process")("WYWIAD_AUTO_OPEN") = "1"\n')
                f.write(f'WshShell.Run "{vbs_cmd}", 0, False\n')
        except Exception:
            run_vbs_path = run_bat_path
    else:
        run_vbs_path = run_bat_path

    desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
    shortcut_path = os.path.join(desktop, "Asystent Medyczny.lnk")
    icon_path = os.path.join(install_dir, ICON_REL_PATH)

    ps_script = f"""
    $s=(New-Object -COM WScript.Shell).CreateShortcut('{shortcut_path}');
    $s.TargetPath='{run_vbs_path}';
    $s.WorkingDirectory='{install_dir}';
    $s.IconLocation='{icon_path}';
    $s.Save()
    """
    subprocess.run(["powershell", "-Command", ps_script], capture_output=True)

    reset_shortcut = os.path.join(desktop, "Reset Asystent Medyczny.lnk")
    reset_target = os.path.join(install_dir, "AsystentSetup.exe")
    ps_reset = f"""
    $s=(New-Object -COM WScript.Shell).CreateShortcut('{reset_shortcut}');
    $s.TargetPath='{reset_target}';
    $s.Arguments='--reset';
    $s.WorkingDirectory='{install_dir}';
    $s.IconLocation='{icon_path}';
    $s.Save()
    """
    subprocess.run(["powershell", "-Command", ps_reset], capture_output=True)

    if remote_commit and not skip_download:
        write_state(state_path, {"commit": remote_commit})

    version_commit = remote_commit or state.get("commit") or "unknown"
    build_info_path = os.path.join(install_dir, "build_info.json")
    write_build_info(build_info_path, {
        "commit": version_commit,
        "downloaded_at": datetime.utcnow().isoformat() + "Z",
        "source": "github/main",
    })

    log_info("\n========================================================")
    log_info("   INSTALACJA ZAKONCZONA SUKCESEM!")
    log_info("========================================================")
    log_info(f"Wersja: {version_commit[:7] if version_commit else 'unknown'}")
    log_info(f"Skrot utworzony na pulpicie: {shortcut_path}")
    if result is not None:
        result["run_bat_path"] = run_bat_path
        result["run_vbs_path"] = run_vbs_path

    if auto_launch:
        log_info("Uruchamianie aplikacji za 3 sekundy...")
        time.sleep(3)
        try:
            subprocess.Popen([run_vbs_path], shell=True)
        except Exception:
            subprocess.Popen([run_bat_path], shell=True)


class ConsoleSink:
    def __init__(self):
        self._last_len = 0
        self._spin = 0

    def step(self, msg):
        print(f"\n[*] {msg}")

    def info(self, msg):
        print(msg)

    def warn(self, msg):
        print(msg)

    def error(self, msg):
        print(f"\n[!] BLAD: {msg}")
        input("Nacisnij ENTER aby zakonczyc...")
        raise InstallerAbort(msg)

    def confirm(self, prompt) -> bool:
        confirm = input(f"{prompt} ").strip().lower()
        return confirm in ("tak", "t", "yes", "y")

    def _write_progress(self, line):
        pad = " " * max(0, self._last_len - len(line))
        sys.stdout.write("\r" + line + pad + "\r" + line)
        sys.stdout.flush()
        self._last_len = max(len(line), self._last_len)

    def progress(self, prefix, current, total, width=30):
        if total and total > 0:
            ratio = min(max(current / total, 0), 1)
            filled = int(width * ratio)
            bar = "#" * filled + "-" * (width - filled)
            percent = int(ratio * 100)
            self._write_progress(
                f"{prefix} [{bar}] {percent}% ({_human_bytes(current)}/{_human_bytes(total)})"
            )
        else:
            spinner = "|/-\\"
            self._spin = (self._spin + 1) % len(spinner)
            self._write_progress(f"{prefix} {spinner[self._spin]} {_human_bytes(current)}")

    def progress_done(self):
        print()

    def run_with_spinner(self, cmd, label):
        spinner = "|/-\\"
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        idx = 0
        out = None
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
            self.error(f"{label} nieudane:\n{details}")


def run_console():
    set_sink(ConsoleSink())
    try:
        run_installer()
    except InstallerExit as e:
        sys.exit(e.code)
    except InstallerAbort:
        sys.exit(1)
    except Exception as e:
        try:
            print_error(f"Wystapil nieoczekiwany blad: {e}")
        except InstallerAbort:
            pass
        sys.exit(1)


def run_gui():
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", "")
        tcl_dir = os.path.join(base, "tcl", "tcl8.6")
        tk_dir = os.path.join(base, "tcl", "tk8.6")
        if os.path.isdir(tcl_dir):
            os.environ["TCL_LIBRARY"] = tcl_dir
        if os.path.isdir(tk_dir):
            os.environ["TK_LIBRARY"] = tk_dir
    else:
        os.environ.pop("TCL_LIBRARY", None)
        os.environ.pop("TK_LIBRARY", None)
    import threading
    import queue
    import tkinter as tk
    from tkinter import ttk, messagebox
    from tkinter.scrolledtext import ScrolledText
    import webbrowser

    root = tk.Tk()
    root.title(f"Instalator {APP_NAME}")
    root.geometry("560x360")
    root.minsize(520, 320)

    bg = "#f8fafc"
    fg = "#0f172a"
    muted = "#64748b"
    accent = "#2563eb"

    root.configure(bg=bg)

    queue_events = queue.Queue()
    installing = {"value": True}

    def set_status(text):
        status_label.config(text=text)

    def append_log(line):
        raw_text.config(state="normal")
        raw_text.insert("end", line + "\n")
        raw_text.see("end")
        raw_text.config(state="disabled")

    def set_progress(prefix, current, total):
        if total and total > 0:
            pct = min(max(current / total, 0), 1.0)
            progress_bar.config(mode="determinate")
            progress_var.set(pct * 100)
            progress_label.config(text=f"{prefix}  {int(pct * 100)}%  ({_human_bytes(current)}/{_human_bytes(total)})")
        else:
            progress_bar.config(mode="indeterminate")
            progress_bar.start(12)
            progress_label.config(text=f"{prefix}...")

    def set_indeterminate(active: bool):
        if active:
            progress_bar.config(mode="indeterminate")
            progress_bar.start(12)
        else:
            progress_bar.stop()
            progress_bar.config(mode="determinate")

    def enable_close():
        installing["value"] = False
        close_btn.config(state="normal")

    def process_queue():
        while True:
            try:
                event, payload = queue_events.get_nowait()
            except queue.Empty:
                break
            if event == "step":
                set_status(payload)
                append_log(f"[*] {payload}")
            elif event == "log":
                append_log(payload)
            elif event == "status":
                set_status(payload)
            elif event == "progress":
                prefix, current, total = payload
                set_progress(prefix, current, total)
            elif event == "progress_done":
                progress_label.config(text="")
            elif event == "indeterminate":
                set_indeterminate(payload)
            elif event == "error":
                set_status("Blad instalacji")
                append_log(f"[!] BLAD: {payload}")
                messagebox.showerror("Blad instalacji", payload)
                enable_close()
            elif event == "done":
                set_status("Gotowe")
                progress_var.set(100)
                if isinstance(payload, dict):
                    run_vbs = payload.get("run_vbs_path")
                    run_bat = payload.get("run_bat_path")
                    if run_vbs or run_bat:
                        def _launch():
                            try:
                                path = run_vbs or run_bat
                                if path:
                                    os.startfile(path)
                            except Exception:
                                messagebox.showwarning("Uruchomienie", "Nie udalo sie uruchomic aplikacji.")
                        launch_btn.config(state="normal", command=_launch)
                open_btn.config(
                    state="normal",
                    command=lambda: webbrowser.open("http://127.0.0.1:8089", new=1, autoraise=True)
                )
                hint_label.config(
                    text="Aplikacja uruchomiona. Jesli przegladarka sie nie otworzyla, kliknij „Otworz w przegladarce”.",
                    fg=muted
                )
                enable_close()
        root.after(50, process_queue)

    class GuiSink:
        def __init__(self, events_queue):
            self._queue = events_queue

        def _send(self, event, payload):
            self._queue.put((event, payload))

        def step(self, msg):
            self._send("step", msg)

        def info(self, msg):
            self._send("log", msg)

        def warn(self, msg):
            self._send("log", msg)

        def error(self, msg):
            self._send("error", msg)
            raise InstallerAbort(msg)

        def confirm(self, prompt) -> bool:
            result = {"value": False}
            done = threading.Event()

            def _open_confirm():
                dialog = tk.Toplevel(root)
                dialog.title("Potwierdz reset")
                dialog.configure(bg=bg)
                dialog.resizable(False, False)
                dialog.transient(root)
                dialog.grab_set()

                tk.Label(dialog, text=prompt, bg=bg, fg=fg, font=("Segoe UI", 10, "bold")).pack(padx=20, pady=(16, 6))
                tk.Label(dialog, text="Aby potwierdzic wpisz TAK", bg=bg, fg=muted, font=("Segoe UI", 9)).pack(padx=20, pady=(0, 8))

                entry = tk.Entry(dialog, width=24)
                entry.pack(padx=20, pady=(0, 12))
                entry.focus_set()

                button_frame = tk.Frame(dialog, bg=bg)
                button_frame.pack(padx=20, pady=(0, 16))

                def _on_ok():
                    value = entry.get().strip().lower()
                    result["value"] = value in ("tak", "t", "yes", "y")
                    dialog.destroy()
                    done.set()

                def _on_cancel():
                    result["value"] = False
                    dialog.destroy()
                    done.set()

                tk.Button(button_frame, text="Anuluj", command=_on_cancel).pack(side="left", padx=6)
                tk.Button(button_frame, text="Potwierdz", command=_on_ok).pack(side="left", padx=6)

            root.after(0, _open_confirm)
            done.wait()
            return result["value"]

        def progress(self, prefix, current, total, width=30):
            self._send("progress", (prefix, current, total))

        def progress_done(self):
            self._send("progress_done", None)

        def run_with_spinner(self, cmd, label):
            self._send("status", label)
            self._send("indeterminate", True)
            output = []
            proc = None
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                if proc.stdout:
                    for line in proc.stdout:
                        line = line.rstrip()
                        if line:
                            output.append(line)
                            self._send("log", line)
                proc.wait()
            finally:
                self._send("indeterminate", False)
            if proc is None:
                self.error(f"{label} nieudane: blad uruchomienia procesu.")
            if proc.returncode != 0:
                details = "\n".join(output[-20:]) if output else "Brak szczegolow."
                self.error(f"{label} nieudane:\n{details}")
            else:
                self._send("log", f"{label} OK")

    def toggle_raw():
        if raw_frame.winfo_ismapped():
            raw_frame.grid_remove()
            toggle_btn.config(text="Pokaz raw")
            root.geometry("560x360")
        else:
            raw_frame.grid()
            toggle_btn.config(text="Ukryj raw")
            root.geometry("560x560")

    def on_close():
        if installing["value"]:
            messagebox.showinfo("Instalacja", "Instalacja w toku. Zaczekaj na zakonczenie.")
        else:
            root.destroy()

    content = tk.Frame(root, bg=bg)
    content.pack(fill="both", expand=True, padx=20, pady=16)

    title_label = tk.Label(content, text=APP_NAME, font=("Segoe UI", 18, "bold"), bg=bg, fg=fg)
    title_label.grid(row=0, column=0, sticky="w")

    subtitle = tk.Label(content, text="Instalator", font=("Segoe UI", 10), bg=bg, fg=muted)
    subtitle.grid(row=1, column=0, sticky="w", pady=(0, 12))

    status_label = tk.Label(content, text="Przygotowywanie...", font=("Segoe UI", 12, "bold"), bg=bg, fg=fg)
    status_label.grid(row=2, column=0, sticky="w", pady=(0, 6))

    progress_var = tk.DoubleVar(value=0)
    progress_bar = ttk.Progressbar(content, variable=progress_var, maximum=100)
    progress_bar.grid(row=3, column=0, sticky="we", pady=(0, 4))

    progress_label = tk.Label(content, text="", font=("Segoe UI", 9), bg=bg, fg=muted)
    progress_label.grid(row=4, column=0, sticky="w", pady=(0, 8))

    hint_label = tk.Label(content, text="Szybki reset: wpisz 'rst' w ciagu 2 sekund", font=("Segoe UI", 9), bg=bg, fg=muted)
    hint_label.grid(row=5, column=0, sticky="w", pady=(0, 12))

    buttons = tk.Frame(content, bg=bg)
    buttons.grid(row=6, column=0, sticky="w", pady=(0, 10))

    toggle_btn = tk.Button(buttons, text="Pokaz raw", command=toggle_raw, fg=accent, bd=0, bg=bg, activebackground=bg, activeforeground=accent)
    toggle_btn.pack(side="left", padx=(0, 10))

    launch_btn = tk.Button(buttons, text="Uruchom aplikacje", state="disabled")
    launch_btn.pack(side="left", padx=(0, 10))

    open_btn = tk.Button(buttons, text="Otworz w przegladarce", state="disabled")
    open_btn.pack(side="left", padx=(0, 10))

    close_btn = tk.Button(buttons, text="Zamknij", command=root.destroy, state="disabled")
    close_btn.pack(side="left")

    raw_frame = tk.Frame(content, bg=bg)
    raw_frame.grid(row=7, column=0, sticky="nsew")
    content.grid_rowconfigure(7, weight=1)
    content.grid_columnconfigure(0, weight=1)

    raw_text = ScrolledText(raw_frame, height=12, wrap="word", state="disabled", font=("Consolas", 9))
    raw_text.pack(fill="both", expand=True)
    raw_frame.grid_remove()

    root.protocol("WM_DELETE_WINDOW", on_close)

    set_sink(GuiSink(queue_events))

    def install_worker():
        try:
            result = {}
            run_installer(auto_launch=True, result=result)
            queue_events.put(("done", result))
        except InstallerExit:
            queue_events.put(("done", None))
        except InstallerAbort:
            pass
        except Exception as e:
            queue_events.put(("error", f"Wystapil nieoczekiwany blad: {e}"))

    quick_reset_buf = {"value": ""}
    quick_reset_active = {"value": True}

    def on_key(event):
        if not quick_reset_active["value"]:
            return
        if not event.char:
            return
        if event.char == "\b":
            quick_reset_buf["value"] = quick_reset_buf["value"][:-1]
            return
        quick_reset_buf["value"] += event.char
        if quick_reset_buf["value"].lower().endswith("rst"):
            global QUICK_RESET_REQUESTED
            QUICK_RESET_REQUESTED = True
            hint_label.config(text="Tryb reset...", fg=fg)

    def start_install():
        quick_reset_active["value"] = False
        if not QUICK_RESET_REQUESTED:
            hint_label.config(text="")
        thread = threading.Thread(target=install_worker, daemon=True)
        thread.start()

    root.bind_all("<Key>", on_key)
    root.after(2000, start_install)
    def _bring_to_front():
        try:
            root.lift()
            root.attributes("-topmost", True)
            root.after(200, lambda: root.attributes("-topmost", False))
        except Exception:
            pass

    root.after(50, process_queue)
    root.after(200, _bring_to_front)

    root.mainloop()


def _write_gui_error(e: Exception) -> str:
    tmp_dir = os.environ.get("TEMP") or os.environ.get("TMP") or os.getcwd()
    err_path = os.path.join(tmp_dir, "asystent_installer_gui_error.log")
    try:
        with open(err_path, "a", encoding="utf-8") as f:
            f.write(f"[GUI ERROR] {datetime.utcnow().isoformat()}Z\n")
            f.write("".join(traceback.format_exception(type(e), e, e.__traceback__)))
            f.write("\n")
    except Exception:
        pass
    return err_path


def _show_gui_error(err_path: str) -> None:
    try:
        import ctypes
        msg = (
            "Nie udalo sie uruchomic GUI instalatora.\n\n"
            f"Szczegoly zapisano w:\n{err_path}\n\n"
            "Uruchom ponownie lub skontaktuj sie z supportem."
        )
        ctypes.windll.user32.MessageBoxW(0, msg, "Instalator AsystentMedyczny", 0x10)
    except Exception:
        pass


def main():
    args = [a.lower() for a in sys.argv[1:]]
    force_console = "--console" in args or os.environ.get("WYWIAD_INSTALLER_CONSOLE") == "1"
    is_exe = str(sys.argv[0]).lower().endswith(".exe")

    if force_console:
        run_console()
        return

    try:
        run_gui()
    except Exception as e:
        err_path = _write_gui_error(e)
        if is_exe:
            _show_gui_error(err_path)
            sys.exit(1)
        run_console()


if __name__ == "__main__":
    main()
