"""
Centralized UI labels for Live Interview.
Keep copy consistent across components.
"""

# Status labels
STATUS_READY = "GOTOWY"
STATUS_RECORDING = "NAGRYWANIE"

# Conversation modes
MODE_LABELS = {
    "symptom": "Tryb: Diagnostyczny",
    "decision": "Tryb: Poradniczy",
    "followup": "Tryb: Kontrolny",
    "admin": "Tryb: Formalny",
    "general": "Tryb: Ogolny",
}

MODE_COLORS = {
    "symptom": "blue",
    "decision": "indigo",
    "followup": "teal",
    "admin": "gray",
    "general": "gray",
}

# Dock buttons
DOCK_TRANSCRIPT = "Transkrypt"
DOCK_PROMPTER = "Sufler"
DOCK_PIPELINE = "Przeplyw"
DOCK_FOCUS = "Skupienie"

# Overlay titles
OVERLAY_PIPELINE_TITLE = "Przeplyw"

# QA desk
QA_TITLE = "Zebrane Q+A (Biurko 3D)"
QA_ENGINE_LOADING = "Laduje biurko 3D..."
QA_ENGINE_FALLBACK = "3D niedostepne - tryb 2D"

# Pipeline panel
PIPELINE_PANEL_TITLE = "Przeplyw transkrypcji"
PIPELINE_SETTINGS_TITLE = "Ustawienia przeplywu"

# Suggestion cards
CARD_TAG_QUESTION = "PYTANIE"
CARD_TAG_SCRIPT = "SKRYPT"
CARD_TAG_CHECK = "CHECKLISTA"

CARD_HINT_QUESTION = "Kliknij, aby skopiowac"
CARD_HINT_SCRIPT = "Kliknij, aby otworzyc skrypt"
CARD_HINT_CHECK = "Kliknij, aby odhaczyc"
