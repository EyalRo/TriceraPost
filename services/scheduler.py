#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from nntp_client import NNTPClient
from services.event_bus import publish_event
from services.settings import get_bool_setting, get_int_setting, get_setting

GROUPS_PATH = os.path.join(BASE_DIR, "groups.json")


def _is_binary_group(name: str) -> bool:
    tokens = re.split(r"[._-]+", name.lower())
    return any(token in {"bin", "binary", "binaries"} for token in tokens)


def _extract_binary_groups(groups: list[dict]) -> list[str]:
    matches = []
    for entry in groups:
        name = str(entry.get("group", "")).strip()
        if not name:
            continue
        if _is_binary_group(name):
            matches.append(name)
    return sorted({g for g in matches if g})


def _load_groups_json() -> list[dict]:
    if not os.path.exists(GROUPS_PATH):
        return []
    try:
        with open(GROUPS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [entry for entry in data if isinstance(entry, dict)]
    return []


def _write_groups_json(groups: list[dict]) -> None:
    try:
        with open(GROUPS_PATH, "w", encoding="utf-8") as handle:
            json.dump(groups, handle, indent=2)
            handle.write("\n")
    except OSError:
        pass


def _fetch_groups_from_nntp() -> list[dict]:
    host = get_setting("NNTP_HOST")
    if not host:
        return []
    port = get_int_setting("NNTP_PORT", 119)
    use_ssl = get_bool_setting("NNTP_SSL")
    user = get_setting("NNTP_USER")
    password = get_setting("NNTP_PASS")

    client = NNTPClient(host, port, use_ssl=use_ssl)
    try:
        client.connect()
        client.reader_mode()
        client.auth(user, password)
        return client.list()
    except Exception:
        return []
    finally:
        try:
            client.quit()
        except Exception:
            pass


def load_groups() -> list[str]:
    override = get_setting("NNTP_GROUPS")
    if override:
        return [g.strip() for g in override.split(",") if g.strip()]

    fetched = _fetch_groups_from_nntp()
    if fetched:
        _write_groups_json(fetched)
        return _extract_binary_groups(fetched)

    cached = _load_groups_json()
    if cached:
        return _extract_binary_groups(cached)

    return []


def _coerce_interval(value: str) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit scan_requested events.")
    parser.add_argument("--groups", help="Comma-separated groups (override defaults)")
    parser.add_argument("--lookback", type=int, help="Override NNTP_LOOKBACK")
    parser.add_argument("--reset", action="store_true", help="Reset group state")
    parser.add_argument(
        "--interval",
        type=int,
        default=_coerce_interval(get_int_setting("TRICERAPOST_SCHEDULER_INTERVAL", 0)),
        help="Repeat scan requests every N seconds (default: 0, run once)",
    )
    args = parser.parse_args()

    while True:
        if args.groups:
            groups = [g.strip() for g in args.groups.split(",") if g.strip()]
        else:
            groups = load_groups()

        if not groups:
            print("No groups selected")
            if args.interval <= 0:
                return 1
        else:
            payload = {"groups": groups, "lookback": args.lookback, "reset": args.reset}
            publish_event("scan_requested", payload)
            print(f"Emitted scan_requested for {len(groups)} groups")

        if args.interval <= 0:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
