"""
model_registry.py - Model Configuration & Registry
═══════════════════════════════════════════════════
LAYER 2 — sits on top of database.py and errors.py

WHO CALLS ME:
  - router.py    → get_router_model(), get_model_config()
  - agent.py     → get_model_config(), get_default_model(),
                    get_thinking_level(), get_temperature()
  - app.py       → load_model_registry_from_file() at startup,
                    API endpoints for settings UI

WHAT I IMPORT:
  - database.py  → get_config(), set_config()
  - errors.py    → ValidationError for typed errors
"""

import os
import json
from database import get_config, set_config
from errors import ValidationError

MODELS_FILE = os.path.join(os.path.dirname(__file__), "models.json")


# ── Registry: Load, Read, Save ────────────────────────────────────

def load_model_registry_from_file():
    """
    Reads models.json and stores it in the config table.
    Called ONCE at app startup by app.py.
    """
    if os.path.exists(MODELS_FILE):
        with open(MODELS_FILE, "r", encoding="utf-8") as f:
            raw = f.read()

        # Validate before storing — catch bad JSON early at startup
        try:
            data = json.loads(raw)
            if "models" not in data:
                raise ValidationError("models.json must contain a 'models' key")
        except json.JSONDecodeError as e:
            raise ValidationError(f"models.json contains invalid JSON: {e}")

        set_config("model_registry", raw)
    else:
        default_registry = {
            "models": [
                {
                    "id": "gemini-2.5-flash",
                    "label": "2.5 Flash (Fallback)",
                    "supports_thinking": False,
                    "default_thinking": "OFF",
                    "temperature_range": [0.0, 2.0],
                    "default_temperature": 1.0,
                    "requires_thought_signatures": False,
                    "status": "active",
                    "notes": "Auto-generated fallback. Edit models.json or use Settings."
                }
            ]
        }
        json_str = json.dumps(default_registry, indent=2)
        with open(MODELS_FILE, "w", encoding="utf-8") as f:
            f.write(json_str)
        set_config("model_registry", json_str)


def get_model_registry():
    """Returns the full list of model dicts from the config table."""
    raw = get_config("model_registry", None)
    if raw:
        try:
            data = json.loads(raw)
            return data.get("models", [])
        except json.JSONDecodeError:
            return []
    return []


def get_model_config(model_id):
    """Looks up ONE model's capabilities. Returns dict or None."""
    for model in get_model_registry():
        if model["id"] == model_id:
            return model
    return None


def get_default_model():
    """Returns the first active model's ID string."""
    for model in get_model_registry():
        if model.get("status") == "active":
            return model["id"]
    return "gemini-2.5-flash"


def save_model_registry(registry_data):
    """
    Saves registry to BOTH config table AND models.json.
    Raises ValidationError if data is malformed.
    """
    if not isinstance(registry_data, dict) or "models" not in registry_data:
        raise ValidationError("Registry data must be a dict with a 'models' key")

    if not isinstance(registry_data["models"], list):
        raise ValidationError("'models' key must be a list")

    for model in registry_data["models"]:
        if not isinstance(model, dict):
            raise ValidationError("Each model entry must be an object")
        if not model.get("id", "").strip():
            raise ValidationError("Every model must have a non-empty 'id' field")
        if "temperature_range" in model and not isinstance(model["temperature_range"], list):
            raise ValidationError(f"temperature_range for model '{model['id']}' must be a list")
        if "default_temperature" in model:
            try:
                float(model["default_temperature"])
            except (ValueError, TypeError):
                raise ValidationError(f"default_temperature for model '{model['id']}' must be a number")

    json_str = json.dumps(registry_data, indent=2)
    try:
        with open(MODELS_FILE, "w", encoding="utf-8") as f:
            f.write(json_str)
    except IOError as e:
        raise ValidationError(f"Failed to write to models.json: {e}")

    set_config("model_registry", json_str)


# ── Per-Agent Config Helpers ──────────────────────────────────────

def get_router_model():
    return get_config("router_model", get_default_model())

def set_router_model(model_name):
    set_config("router_model", model_name)

def get_thinking_level(agent_id):
    return get_config(f"thinking_level_{agent_id}", None)

def set_thinking_level(agent_id, level):
    set_config(f"thinking_level_{agent_id}", level.upper() if level else "")

def get_temperature(agent_id):
    return get_config(f"temperature_{agent_id}", None)

def set_temperature(agent_id, temp):
    set_config(f"temperature_{agent_id}", str(temp) if temp is not None and temp != "" else "")
