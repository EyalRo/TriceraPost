#!/usr/bin/env python3.13
import json
import os
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SETTINGS_PATH = os.path.join(BASE_DIR, "data", "settings.json")


def settings_path() -> str:
    return os.environ.get("TRICERAPOST_SETTINGS_PATH", DEFAULT_SETTINGS_PATH)


def load_settings() -> dict:
    path = settings_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data, dict):
        return data
    return {}


def save_settings(settings: dict) -> None:
    path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, path)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _coerce_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_setting(key: str, default: Any = None) -> Any:
    settings = load_settings()
    if key in settings and settings[key] not in {None, ""}:
        return settings[key]
    return os.environ.get(key, default)


def get_bool_setting(key: str, default: bool = False) -> bool:
    settings = load_settings()
    if key in settings:
        return _coerce_bool(settings[key], default)
    return _coerce_bool(os.environ.get(key), default)


def get_int_setting(key: str, default: int) -> int:
    settings = load_settings()
    if key in settings:
        return _coerce_int(settings[key], default)
    return _coerce_int(os.environ.get(key), default)
