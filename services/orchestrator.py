#!/usr/bin/env python3
import argparse

from services.event_bus import publish_event
from services.scheduler import load_groups


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit scan_requested event.")
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

    publish_event("scan_requested", {"groups": groups, "lookback": args.lookback, "reset": args.reset})
    print(f"Emitted scan_requested for {len(groups)} groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
