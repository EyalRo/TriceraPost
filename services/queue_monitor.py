#!/usr/bin/env python3
import argparse
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from services.event_bus import get_event_db, init_event_db


def get_queue_stats() -> tuple[int, int, int]:
    conn = get_event_db()
    init_event_db(conn)
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM events").fetchone()
    max_id = int(row["max_id"] or 0)
    row = conn.execute("SELECT COALESCE(MIN(last_event_id), 0) AS min_id FROM cursors").fetchone()
    min_id = int(row["min_id"] or 0)
    conn.close()
    pending = max(0, max_id - min_id)
    return pending, max_id, min_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Print event queue length periodically.")
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    while True:
        pending, max_id, min_id = get_queue_stats()
        print(f"Event queue: {pending} pending (max={max_id} min_cursor={min_id})")
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
