#!/usr/bin/env python3
import argparse
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from services.event_bus import get_last_event_id, iter_events, publish_event, set_last_event_id
from services.ingest import ingest_groups

SERVICE_NAME = "ingest_worker"


def main() -> int:
    parser = argparse.ArgumentParser(description="Worker that ingests headers on scan_requested events.")
    parser.add_argument("--poll", type=float, default=1.0)
    args = parser.parse_args()

    last_id = get_last_event_id(SERVICE_NAME)
    print(f"Ingest worker starting at event {last_id}")

    while True:
        processed = False
        for event in iter_events(last_id):
            processed = True
            last_id = event["id"]
            if event["type"] != "scan_requested":
                set_last_event_id(SERVICE_NAME, last_id)
                continue

            payload = event["payload"]
            groups = payload.get("groups", [])
            lookback = payload.get("lookback")
            reset = bool(payload.get("reset"))
            publish_event("scan_started", {"groups": groups})

            ingest_groups(
                groups=groups,
                lookback=lookback,
                reset=reset,
                emit_events=True,
            )

            publish_event("scan_finished", {"groups": groups})
            set_last_event_id(SERVICE_NAME, last_id)

        if not processed:
            time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
