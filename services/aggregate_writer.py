#!/usr/bin/env python3
import argparse
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from services.aggregate import build_releases
from services.event_bus import get_last_event_id, iter_events, set_last_event_id
from release_filter import main as filter_main

SERVICE_NAME = "aggregate_writer"


def main() -> int:
    parser = argparse.ArgumentParser(description="Writer for releases tables.")
    parser.add_argument("--poll", type=float, default=float(os.environ.get("TRICERAPOST_AGGREGATE_POLL", "1")))
    parser.add_argument(
        "--debounce",
        type=float,
        default=float(os.environ.get("TRICERAPOST_AGGREGATE_DEBOUNCE", "60")),
    )
    parser.add_argument(
        "--max-interval",
        type=float,
        default=float(os.environ.get("TRICERAPOST_AGGREGATE_INTERVAL", "60")),
    )
    args = parser.parse_args()

    last_id = get_last_event_id(SERVICE_NAME)
    print(f"Aggregate writer starting at event {last_id}")
    dirty = False
    last_change = 0.0
    last_build = 0.0

    while True:
        processed = False
        for event in iter_events(last_id):
            processed = True
            last_id = event["id"]
            if event["type"] in {"scan_progress", "scan_finished", "nzb_parsed", "nzb_failed", "aggregate_requested"}:
                dirty = True
                last_change = time.monotonic()
            set_last_event_id(SERVICE_NAME, last_id)

        now = time.monotonic()
        if dirty and ((now - last_change) >= args.debounce or (now - last_build) >= args.max_interval):
            build_releases()
            filter_main([])
            last_build = time.monotonic()
            dirty = False

        if not processed:
            time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
