import sqlite3
import shutil
import os
import subprocess
import tempfile

cookies_path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data", "Default", "Network", "Cookies")
temp_path = os.path.join(tempfile.gettempdir(), "cookies_schema_check")

print(f"Source: {cookies_path}")
print(f"Temp: {temp_path}")

# Metoda 1: shutil
try:
    shutil.copy2(cookies_path, temp_path)
    print("Metoda shutil: OK")
except Exception as e:
    print(f"Metoda shutil: {e}")

    # Metoda 2: PowerShell
    ps_script = f'''
$source = "{cookies_path}"
$dest = "{temp_path}"
$fs = [System.IO.File]::Open($source, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
$buffer = New-Object byte[] $fs.Length
$fs.Read($buffer, 0, $fs.Length) | Out-Null
$fs.Close()
[System.IO.File]::WriteAllBytes($dest, $buffer)
'''
    result = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, timeout=10)
    if result.returncode == 0:
        print("Metoda PowerShell: OK")
    else:
        print(f"Metoda PowerShell: FAIL - {result.stderr}")

if os.path.exists(temp_path):
    print(f"Skopiowany plik: {os.path.getsize(temp_path)} bytes")

    try:
        conn = sqlite3.connect(temp_path)
        cursor = conn.cursor()

        # Lista wszystkich tabel
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"Tabele: {tables}")

        # Schemat każdej tabeli
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table[0]})")
            cols = cursor.fetchall()
            print(f"  {table[0]}: {[c[1] for c in cols]}")

        conn.close()
    except Exception as e:
        print(f"Blad SQLite: {e}")

        # Sprawdź czy to w ogóle plik SQLite
        with open(temp_path, 'rb') as f:
            header = f.read(16)
            print(f"Header: {header}")

    os.remove(temp_path)
