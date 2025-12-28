from app.settings import (
    get_bool_setting,
    get_int_setting,
    get_setting,
    load_settings,
    save_settings,
)

type SettingsPayload = dict[str, object]


def coerce_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def coerce_int(value: object, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_settings_payload() -> SettingsPayload:
    return {
        "NNTP_HOST": get_setting("NNTP_HOST", ""),
        "NNTP_PORT": get_int_setting("NNTP_PORT", 119),
        "NNTP_SSL": get_bool_setting("NNTP_SSL", False),
        "NNTP_USER": get_setting("NNTP_USER", ""),
        "NNTP_PASS_SET": bool(get_setting("NNTP_PASS")),
        "NNTP_LOOKBACK": get_int_setting("NNTP_LOOKBACK", 2000),
        "NNTP_GROUPS": get_setting("NNTP_GROUPS", ""),
        "TRICERAPOST_SCHEDULER_INTERVAL": get_int_setting("TRICERAPOST_SCHEDULER_INTERVAL", 0),
        "TRICERAPOST_SAVE_NZBS": get_bool_setting("TRICERAPOST_SAVE_NZBS", False),
        "TRICERAPOST_NZB_DIR": get_setting("TRICERAPOST_NZB_DIR", ""),
        "TRICERAPOST_DOWNLOAD_STATION_ENABLED": get_bool_setting(
            "TRICERAPOST_DOWNLOAD_STATION_ENABLED",
            True,
        ),
    }


def apply_settings_payload(payload: dict[str, object]) -> SettingsPayload:
    settings = load_settings()
    clear_password = bool(payload.get("clear_password"))
    if clear_password:
        settings.pop("NNTP_PASS", None)

    if "NNTP_PASS" in payload and payload.get("NNTP_PASS"):
        settings["NNTP_PASS"] = str(payload.get("NNTP_PASS")).strip()

    if "TRICERAPOST_SAVE_NZBS" in payload:
        settings["TRICERAPOST_SAVE_NZBS"] = coerce_bool(
            payload.get("TRICERAPOST_SAVE_NZBS"),
            True,
        )
    if "TRICERAPOST_DOWNLOAD_STATION_ENABLED" in payload:
        settings["TRICERAPOST_DOWNLOAD_STATION_ENABLED"] = coerce_bool(
            payload.get("TRICERAPOST_DOWNLOAD_STATION_ENABLED"),
            True,
        )
    if "TRICERAPOST_NZB_DIR" in payload:
        nzb_dir = str(payload.get("TRICERAPOST_NZB_DIR") or "").strip()
        if nzb_dir:
            settings["TRICERAPOST_NZB_DIR"] = nzb_dir
        else:
            settings.pop("TRICERAPOST_NZB_DIR", None)

    for key in ("NNTP_HOST", "NNTP_USER", "NNTP_GROUPS"):
        if key in payload:
            value = payload.get(key)
            if value is None or str(value).strip() == "":
                settings.pop(key, None)
            else:
                settings[key] = str(value).strip()

    for key, default in (
        ("NNTP_PORT", 119),
        ("NNTP_LOOKBACK", 2000),
        ("TRICERAPOST_SCHEDULER_INTERVAL", 0),
    ):
        if key in payload:
            value = payload.get(key)
            if value is None or value == "":
                settings.pop(key, None)
            else:
                settings[key] = coerce_int(value, default)

    if "NNTP_SSL" in payload:
        settings["NNTP_SSL"] = coerce_bool(payload.get("NNTP_SSL"), False)

    save_settings(settings)
    return build_settings_payload()
