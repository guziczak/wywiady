"""
Manager specjalizacji medycznych.

Zarządza ładowaniem konfiguracji, promptów i schematów lokalizacji
dla różnych specjalizacji medycznych.
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

# Ścieżka do danych specjalizacji
SPECIALIZATIONS_DIR = Path(__file__).parent.parent / "data" / "specializations"
CONFIG_FILE = Path(__file__).parent.parent / "config.json"


@dataclass
class SpecPrompts:
    """Prompty dla specjalizacji."""
    description_system: str = ""
    description_context: str = ""
    description_location: str = ""
    description_output: str = ""
    suggestions_system: str = ""
    suggestions_focus_areas: List[str] = field(default_factory=list)
    suggestions_examples: List[str] = field(default_factory=list)
    validation_terms: List[str] = field(default_factory=list)
    validation_abbreviations: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> 'SpecPrompts':
        desc = data.get('description', {})
        sugg = data.get('suggestions', {})
        valid = data.get('validation', {})

        return cls(
            description_system=desc.get('system', ''),
            description_context=desc.get('context_instructions', ''),
            description_location=desc.get('location_instruction', ''),
            description_output=desc.get('output_format', ''),
            suggestions_system=sugg.get('system', ''),
            suggestions_focus_areas=sugg.get('focus_areas', []),
            suggestions_examples=sugg.get('example_questions', []),
            validation_terms=valid.get('medical_terms', []),
            validation_abbreviations=valid.get('abbreviations', {})
        )


@dataclass
class LocationSchema:
    """Schemat lokalizacji dla specjalizacji."""
    type: str = "text"  # dental_fdi, anatomical_select, eye_select, text
    label: str = "Lokalizacja"
    description: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> 'LocationSchema':
        return cls(
            type=data.get('type', 'text'),
            label=data.get('label', 'Lokalizacja'),
            description=data.get('description', ''),
            data=data
        )

    def get_options(self) -> List[Dict]:
        """Zwraca listę opcji dla select-based typów."""
        if self.type == 'anatomical_select':
            return self.data.get('options', [])
        elif self.type == 'eye_select':
            return self.data.get('eye_options', [])
        elif self.type == 'dental_fdi':
            # Flatten teeth list
            schema = self.data.get('schema', {})
            teeth = []
            for category in ['permanent', 'deciduous']:
                if category in schema:
                    for quadrant_data in schema[category].values():
                        teeth.extend(quadrant_data.get('teeth', []))
            return [{'value': t, 'label': f'Ząb {t}'} for t in teeth]
        return []


@dataclass
class Specialization:
    """Model specjalizacji medycznej."""
    id: int
    name: str
    slug: str
    icon: str = ""
    icon_svg: str = ""
    color_primary: str = "#1976D2"
    color_secondary: str = "#BBDEFB"
    location_label: str = "Lokalizacja"
    location_type: str = "text"
    enabled: bool = True
    description: str = ""

    # Lazy-loaded data
    _prompts: Optional[SpecPrompts] = field(default=None, repr=False)
    _locations: Optional[LocationSchema] = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, data: dict) -> 'Specialization':
        return cls(
            id=data.get('id', 0),
            name=data.get('name', ''),
            slug=data.get('slug', ''),
            icon=data.get('icon', ''),
            icon_svg=data.get('icon_svg', ''),
            color_primary=data.get('color_primary', '#1976D2'),
            color_secondary=data.get('color_secondary', '#BBDEFB'),
            location_label=data.get('location_label', 'Lokalizacja'),
            location_type=data.get('location_type', 'text'),
            enabled=data.get('enabled', True),
            description=data.get('description', '')
        )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'icon': self.icon,
            'icon_svg': self.icon_svg,
            'color_primary': self.color_primary,
            'color_secondary': self.color_secondary,
            'location_label': self.location_label,
            'location_type': self.location_type,
            'enabled': self.enabled,
            'description': self.description
        }


class SpecializationManager:
    """
    Singleton zarządzający specjalizacjami medycznymi.

    Ładuje konfigurację z plików JSON w data/specializations/
    i udostępnia API do pobierania promptów, lokalizacji itp.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._specializations: Dict[int, Specialization] = {}
        self._prompts_cache: Dict[int, SpecPrompts] = {}
        self._locations_cache: Dict[int, LocationSchema] = {}
        self._active_spec_id: int = 1  # Domyślnie stomatologia

        self._load_specializations()
        self._load_active_from_config()
        self._initialized = True

    def _load_specializations(self) -> None:
        """Ładuje wszystkie specjalizacje z katalogu data/specializations/"""
        if not SPECIALIZATIONS_DIR.exists():
            print(f"[SPEC] Directory not found: {SPECIALIZATIONS_DIR}")
            self._load_fallback_specializations()
            return

        for spec_dir in SPECIALIZATIONS_DIR.iterdir():
            if not spec_dir.is_dir():
                continue

            config_path = spec_dir / "config.json"
            if not config_path.exists():
                continue

            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                spec = Specialization.from_dict(data)
                self._specializations[spec.id] = spec
                print(f"[SPEC] Loaded: {spec.name} (ID={spec.id})")

            except Exception as e:
                print(f"[SPEC] Error loading {config_path}: {e}")

        if not self._specializations:
            print("[SPEC] No specializations loaded from disk. Using fallback defaults.")
            self._load_fallback_specializations()

    def _load_fallback_specializations(self) -> None:
        """Awaryjne specjalizacje gdy brak danych na dysku."""
        defaults = [
            {"id": 1, "name": "Stomatologia", "slug": "stomatologia", "icon": "🦷", "enabled": True},
            {"id": 2, "name": "Kardiologia", "slug": "kardiologia", "icon": "❤️", "enabled": True},
            {"id": 3, "name": "Okulistyka", "slug": "okulistyka", "icon": "👁️", "enabled": True},
        ]
        for data in defaults:
            spec = Specialization.from_dict(data)
            self._specializations[spec.id] = spec
            print(f"[SPEC] Loaded fallback: {spec.name} (ID={spec.id})")

    def _load_active_from_config(self) -> None:
        """Ładuje aktywną specjalizację z głównego configa."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._active_spec_id = data.get('active_specialization', 1)
            except:
                pass

    def _save_active_to_config(self) -> None:
        """Zapisuje aktywną specjalizację do głównego configa."""
        try:
            data = {}
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)

            data['active_specialization'] = self._active_spec_id

            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[SPEC] Error saving config: {e}")

    # === Public API ===

    def get_all(self, enabled_only: bool = True) -> List[Specialization]:
        """Zwraca wszystkie specjalizacje."""
        specs = list(self._specializations.values())
        if enabled_only:
            specs = [s for s in specs if s.enabled]
        return sorted(specs, key=lambda s: s.id)

    def get_by_id(self, spec_id: int) -> Optional[Specialization]:
        """Zwraca specjalizację po ID."""
        return self._specializations.get(spec_id)

    def get_by_slug(self, slug: str) -> Optional[Specialization]:
        """Zwraca specjalizację po slug."""
        for spec in self._specializations.values():
            if spec.slug == slug:
                return spec
        return None

    def get_active(self) -> Specialization:
        """Zwraca aktywną specjalizację."""
        spec = self.get_by_id(self._active_spec_id)
        if not spec:
            # Fallback do pierwszej dostępnej
            specs = self.get_all()
            spec = specs[0] if specs else Specialization(id=1, name="Stomatologia", slug="stomatologia")
        return spec

    def set_active(self, spec_id: int) -> bool:
        """Ustawia aktywną specjalizację."""
        if spec_id not in self._specializations:
            return False

        self._active_spec_id = spec_id
        self._save_active_to_config()
        print(f"[SPEC] Active specialization changed to: {self.get_active().name}")
        return True

    def get_prompts(self, spec_id: Optional[int] = None) -> SpecPrompts:
        """Zwraca prompty dla specjalizacji."""
        if spec_id is None:
            spec_id = self._active_spec_id

        # Check cache
        if spec_id in self._prompts_cache:
            return self._prompts_cache[spec_id]

        # Load from file
        spec = self.get_by_id(spec_id)
        if not spec:
            return SpecPrompts()

        prompts_path = SPECIALIZATIONS_DIR / spec.slug / "prompts.json"
        if not prompts_path.exists():
            return SpecPrompts()

        try:
            with open(prompts_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            prompts = SpecPrompts.from_dict(data)
            self._prompts_cache[spec_id] = prompts
            return prompts
        except Exception as e:
            print(f"[SPEC] Error loading prompts: {e}")
            return SpecPrompts()

    def get_locations(self, spec_id: Optional[int] = None) -> LocationSchema:
        """Zwraca schemat lokalizacji dla specjalizacji."""
        if spec_id is None:
            spec_id = self._active_spec_id

        # Check cache
        if spec_id in self._locations_cache:
            return self._locations_cache[spec_id]

        # Load from file
        spec = self.get_by_id(spec_id)
        if not spec:
            return LocationSchema()

        locations_path = SPECIALIZATIONS_DIR / spec.slug / "locations.json"
        if not locations_path.exists():
            return LocationSchema(type="text", label=spec.location_label)

        try:
            with open(locations_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            locations = LocationSchema.from_dict(data)
            self._locations_cache[spec_id] = locations
            return locations
        except Exception as e:
            print(f"[SPEC] Error loading locations: {e}")
            return LocationSchema()

    def build_description_prompt(
        self,
        transcript: str,
        icd_context: str,
        proc_context: str,
        spec_id: Optional[int] = None
    ) -> str:
        """
        Buduje pełny prompt do generowania opisu wizyty.

        Używa promptów specyficznych dla specjalizacji.
        """
        prompts = self.get_prompts(spec_id)
        spec = self.get_by_id(spec_id) if spec_id else self.get_active()

        prompt = f"""{prompts.description_system}

{prompts.description_context}

Dostępne słowniki (BAZA WIEDZY):
--- ICD-10 (Diagnozy) ---
{icd_context}
... (i więcej)

--- ICD-9 PL (Procedury) ---
{proc_context}
... (i więcej)

INSTRUKCJA:
1. Przeanalizuj tekst i zidentyfikuj WSZYSTKIE wykonane czynności oraz postawione diagnozy.
2. Dla każdej pozycji znajdź NAJLEPIEJ pasujący kod z powyższych list.
3. {prompts.description_location}
4. Jeśli procedury/kodu nie ma na liście, użyj najbardziej zbliżonego lub ogólnego.

Format wyjściowy JSON:
{{
  "diagnozy": [
    {{
      "kod": "...",
      "nazwa": "...",
      "opis_tekstowy": "...",
      "zab": "..."
    }}
  ],
  "procedury": [
    {{
      "kod": "...",
      "nazwa": "...",
      "opis_tekstowy": "...",
      "zab": "..."
    }}
  ]
}}

Transkrypcja wywiadu:
{transcript}

Odpowiedz TYLKO poprawnym kodem JSON."""

        return prompt

    def build_suggestions_prompt(
        self,
        transcript: str,
        exclude_questions: Optional[List[str]] = None,
        spec_id: Optional[int] = None
    ) -> str:
        """Buduje prompt do generowania sugestii pytań."""
        prompts = self.get_prompts(spec_id)
        spec = self.get_by_id(spec_id) if spec_id else self.get_active()

        exclude_section = ""
        if exclude_questions:
            exclude_list = "\n".join([f"- {q}" for q in exclude_questions])
            exclude_section = f"""
PYTANIA JUŻ ZADANE (NIE POWTARZAJ ICH):
{exclude_list}
"""

        focus_areas = "\n".join([f"- {area}" for area in prompts.suggestions_focus_areas])
        examples = json.dumps(prompts.suggestions_examples[:3], ensure_ascii=False)

        prompt = f"""{prompts.suggestions_system}

Obszary na które zwracaj uwagę:
{focus_areas}

Oto dotychczasowy przebieg rozmowy:
---
{transcript}
---
{exclude_section}
Zadanie:
Zasugeruj DOKŁADNIE 3 krótkie, konkretne pytania, które warto teraz zadać pacjentowi.

Jeśli wywiad jest kompletny lub brak danych, zasugeruj pytania ogólne jak: {examples}

Odpowiedź zwróć TYLKO jako listę JSON stringów, np.:
["Pytanie 1?", "Pytanie 2?", "Pytanie 3?"]
"""

        return prompt

    def clear_cache(self) -> None:
        """Czyści cache promptów i lokalizacji."""
        self._prompts_cache.clear()
        self._locations_cache.clear()

    def reload(self) -> None:
        """Przeładowuje wszystkie specjalizacje."""
        self._specializations.clear()
        self.clear_cache()
        self._load_specializations()


# Singleton accessor
_manager: Optional[SpecializationManager] = None


def get_specialization_manager() -> SpecializationManager:
    """Zwraca singleton SpecializationManager."""
    global _manager
    if _manager is None:
        _manager = SpecializationManager()
    return _manager
