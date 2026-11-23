import json
import os
import logging
import uuid

from cocbot.core.paths import is_frozen, resource_path, user_path

SETTINGS_PATH = user_path("settings.json")
# Shipped inside the bundle; used to seed a fresh install.
DEFAULT_SETTINGS_RESOURCE = "settings.json"


def _seed_default_settings():
    """Copy the bundled default settings into the user data dir (once)."""
    if not is_frozen() or os.path.exists(SETTINGS_PATH):
        return
    try:
        with open(resource_path(DEFAULT_SETTINGS_RESOURCE), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            save_settings(data)
    except (OSError, ValueError):
        pass


def load_settings(strict=False):
    """Read settings.json. Returns an empty dict if missing or unreadable."""
    _seed_default_settings()
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logging.getLogger(__name__).error("Cannot read settings %s: %s", SETTINGS_PATH, exc)
        if strict:
            raise ValueError(f"Cannot read settings.json: {exc}") from exc
    if strict:
        raise ValueError("settings.json must contain a JSON object")
    return {}


def save_settings(data):
    """Write settings.json. Returns True on success, False on failure."""
    temporary = SETTINGS_PATH + "." + uuid.uuid4().hex + ".tmp"
    try:
        if not isinstance(data, dict):
            raise ValueError("Settings must be an object")
        with open(temporary, "x", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, SETTINGS_PATH)
        return True
    except (OSError, ValueError, TypeError):
        logging.getLogger(__name__).exception("Cannot save settings")
        return False
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
