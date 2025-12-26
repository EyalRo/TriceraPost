#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from services.event_bus import publish_event
from services.settings import get_setting

GROUPS_PATH = os.path.join(BASE_DIR, "groups.json")


def _is_binary_group(name: str) -> bool:
    tokens = re.split(r"[._-]+", name.lower())
    return any(token in {"bin", "binary", "binaries"} for token in tokens)


def load_groups() -> list[str]:
    override = get_setting("NNTP_GROUPS")
    if override:
        return [g.strip() for g in override.split(",") if g.strip()]
    if os.path.exists(GROUPS_PATH):
        try:
            with open(GROUPS_PATH, "r", encoding="utf-8") as handle:
                groups = json.load(handle)
            matches = []
            for entry in groups:
                name = str(entry.get("group", "")).strip()
                if not name:
                    continue
                if _is_binary_group(name):
                    matches.append(name)
            return sorted({g for g in matches if g})
        except (OSError, json.JSONDecodeError):
            pass
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit scan_requested events.")
    parser.add_argument("--groups", help="Comma-separated groups (override defaults)")
    parser.add_argument("--lookback", type=int, help="Override NNTP_LOOKBACK")
    parser.add_argument("--reset", action="store_true", help="Reset group state")
    args = parser.parse_args()

    if args.groups:
        groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    else:
        groups = load_groups()

    if not groups:
        print("No groups selected")
        return 1

    payload = {"groups": groups, "lookback": args.lookback, "reset": args.reset}
    publish_event("scan_requested", payload)
    print(f"Emitted scan_requested for {len(groups)} groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
