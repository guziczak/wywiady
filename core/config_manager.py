import json
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

CONFIG_FILE = Path(__file__).parent.parent / "config.json"

@dataclass
class AppConfig:
    """Model konfiguracji aplikacji."""
    api_key: str = ""
    session_key: str = ""
    transcriber_backend: str = "gemini_cloud"
    transcriber_model: str = "small"
    selected_device: str = "auto"
    generation_model: str = "Auto"  # Auto, Claude, Gemini

class ConfigManager:
    """Zarządza ładowaniem i zapisywaniem konfiguracji."""
    
    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self._config: AppConfig = self._load()

    def _load(self) -> AppConfig:
        """Ładuje konfigurację z pliku lub tworzy domyślną."""
        if not self.config_path.exists():
            return AppConfig()
        
        try:
            data = json.loads(self.config_path.read_text(encoding='utf-8'))
            # Filtrujemy tylko znane pola, zeby nie psuc sie przy smieciach
            valid_keys = AppConfig.__annotations__.keys()
            filtered_data = {k: v for k, v in data.items() if k in valid_keys}
            return AppConfig(**filtered_data)
        except Exception as e:
            print(f"[CONFIG] Błąd ładowania configu: {e}", flush=True)
            return AppConfig()

    def save(self):
        """Zapisuje obecny stan konfiguracji do pliku."""
        try:
            data = asdict(self._config)
            self.config_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
            print("[CONFIG] Zapisano ustawienia.", flush=True)
        except Exception as e:
            print(f"[CONFIG] Błąd zapisu configu: {e}", flush=True)

    # Dostęp do pól (Gettery/Settery lub property)
    
    @property
    def config(self) -> AppConfig:
        return self._config

    def update(self, **kwargs):
        """Aktualizuje wiele pól naraz i zapisuje."""
        changed = False
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                current_val = getattr(self._config, key)
                if current_val != value:
                    setattr(self._config, key, value)
                    changed = True
        
        if changed:
            self.save()

    # Helpers for specific keys (optional, for cleaner code)
    def get(self, key: str, default=None):
        return getattr(self._config, key, default)

    def set(self, key: str, value):
        if hasattr(self._config, key):
            setattr(self._config, key, value)
            self.save()

    # Dictionary-like access for compatibility
    def __getitem__(self, key):
        return getattr(self._config, key)

    def __setitem__(self, key, value):
        self.set(key, value)

    def get(self, key, default=None):
        return getattr(self._config, key, default)
