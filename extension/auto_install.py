"""
Automatyczna instalacja i pobranie klucza - używa Selenium który ładuje rozszerzenie automatycznie.
"""
import subprocess
import time
import os
import sys
import json

def get_session_key():
    """Uruchamia Edge z rozszerzeniem, pobiera klucz, zamyka."""

    # Instaluj zależności jeśli brak
    try:
        from selenium import webdriver
        from selenium.webdriver.edge.service import Service
        from selenium.webdriver.edge.options import Options
        from webdriver_manager.microsoft import EdgeChromiumDriverManager
    except ImportError:
        print("Instaluje wymagane biblioteki...")
        subprocess.run([sys.executable, "-m", "pip", "install", "selenium", "webdriver-manager", "-q"])
        from selenium import webdriver
        from selenium.webdriver.edge.service import Service
        from selenium.webdriver.edge.options import Options
        from webdriver_manager.microsoft import EdgeChromiumDriverManager

    extension_path = os.path.dirname(os.path.abspath(__file__))

    print("=== AUTOMATYCZNE POBIERANIE KLUCZA CLAUDE ===")
    print()

    # Konfiguracja Edge z rozszerzeniem
    print("[1/4] Uruchamiam Edge z rozszerzeniem...")
    options = Options()
    options.add_argument(f"--load-extension={extension_path}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")

    try:
        service = Service(EdgeChromiumDriverManager().install())
        driver = webdriver.Edge(service=service, options=options)
    except Exception as e:
        print(f"BLAD: {e}")
        return None

    # Otwórz Claude
    print("[2/4] Otwieram claude.ai...")
    driver.get("https://claude.ai/")

    print("[3/4] Pobieram sessionKey z cookies...")

    # Czekaj na cookie (max 60 sekund - użytkownik może musieć się zalogować)
    max_wait = 60
    session_key = None

    for i in range(max_wait):
        time.sleep(1)
        try:
            cookies = driver.get_cookies()
            for cookie in cookies:
                if cookie['name'] == 'sessionKey':
                    session_key = cookie['value']
                    break
            if session_key:
                break
        except:
            pass

        if i > 0 and i % 10 == 0:
            print(f"    Czekam na zalogowanie... ({i}s)")

    driver.quit()

    if session_key:
        print("[4/4] Zapisuje klucz do konfiguracji...")

        # Zapisz do config.json
        config_path = os.path.join(os.path.dirname(extension_path), "config.json")
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
            else:
                config = {}

            config['session_key'] = session_key

            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)

            print()
            print("=== SUKCES! ===")
            print(f"Klucz zapisany: {session_key[:30]}...")
            return session_key
        except Exception as e:
            print(f"Blad zapisu: {e}")
            print(f"Klucz: {session_key}")
            return session_key
    else:
        print()
        print("=== NIE UDALO SIE ===")
        print("Nie znaleziono sessionKey. Upewnij sie ze jestes zalogowany na claude.ai")
        return None

if __name__ == "__main__":
    get_session_key()
    input("\nNacisnij Enter aby zamknac...")
