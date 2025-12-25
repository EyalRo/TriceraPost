#!/usr/bin/env python3
import argparse
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from services.event_bus import get_last_event_id, iter_events, publish_event, set_last_event_id

SERVICE_NAME = "aggregate_worker"


def main() -> int:
    parser = argparse.ArgumentParser(description="Worker to emit aggregate_requested on ingest events.")
    parser.add_argument("--poll", type=float, default=1.0)
    parser.add_argument("--debounce", type=float, default=2.0)
    args = parser.parse_args()

    last_id = get_last_event_id(SERVICE_NAME)
    dirty = False
    last_change = 0.0

    while True:
        processed = False
        for event in iter_events(last_id):
            processed = True
            last_id = event["id"]
            if event["type"] in {"scan_finished", "nzb_parsed", "nzb_failed"}:
                dirty = True
                last_change = time.monotonic()
            set_last_event_id(SERVICE_NAME, last_id)

        if dirty and (time.monotonic() - last_change) >= args.debounce:
            publish_event("aggregate_requested", {})
            dirty = False

        if not processed:
            time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
