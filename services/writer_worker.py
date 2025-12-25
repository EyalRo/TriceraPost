#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from services.db import get_ingest_db, get_state_db, init_ingest_db, init_state_db
from services.event_bus import get_last_event_id, iter_events, set_last_event_id

SERVICE_NAME = "ingest_writer"


def append_ingest(conn, record: dict) -> None:
    payload = record.get("payload")
    conn.execute(
        """
        INSERT INTO ingest(
            group_name, type, article, subject, poster, date, bytes, message_id, payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.get("group"),
            record.get("type"),
            record.get("article"),
            record.get("subject"),
            record.get("poster"),
            record.get("date"),
            record.get("bytes"),
            record.get("message_id"),
            json.dumps(payload) if payload is not None else None,
        ),
    )


def update_state(conn, group: str, last_article: int) -> None:
    conn.execute(
        "INSERT INTO state(group_name, last_article) VALUES(?, ?) "
        "ON CONFLICT(group_name) DO UPDATE SET last_article=excluded.last_article",
        (group, int(last_article)),
    )


def reset_state(conn, group: str) -> None:
    conn.execute("DELETE FROM state WHERE group_name = ?", (group,))


def flush_ingest(buffer: list[dict]) -> None:
    if not buffer:
        return
    conn = get_ingest_db()
    init_ingest_db(conn)
    rows = []
    for record in buffer:
        payload = record.get("payload")
        rows.append(
            (
                record.get("group"),
                record.get("type"),
                record.get("article"),
                record.get("subject"),
                record.get("poster"),
                record.get("date"),
                record.get("bytes"),
                record.get("message_id"),
                json.dumps(payload) if payload is not None else None,
            )
        )
    conn.executemany(
        """
        INSERT INTO ingest(
            group_name, type, article, subject, poster, date, bytes, message_id, payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    buffer.clear()


def main() -> int:
    parser = argparse.ArgumentParser(description="Writer worker for ingest/state.")
    parser.add_argument("--poll", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--flush-seconds", type=float, default=2.0)
    args = parser.parse_args()

    last_id = get_last_event_id(SERVICE_NAME)
    print(f"Writer worker starting at event {last_id}")
    ingest_buffer = []
    last_flush = time.monotonic()

    while True:
        processed = False
        for event in iter_events(last_id, limit=1000):
            processed = True
            last_id = event["id"]
            event_type = event["type"]
            payload = event["payload"]
            if event_type == "header_ingested":
                ingest_buffer.append(payload)
            elif event_type == "header_ingested_batch":
                items = payload.get("items") if isinstance(payload, dict) else None
                if isinstance(items, list):
                    ingest_buffer.extend(items)
            elif event_type == "nzb_file":
                ingest_buffer.append(payload)
            elif event_type == "nzb_failed":
                ingest_buffer.append(payload)
            elif event_type == "state_update":
                group = payload.get("group")
                last_article = payload.get("last_article")
                if group and last_article is not None:
                    conn = get_state_db()
                    init_state_db(conn)
                    update_state(conn, group, last_article)
                    conn.commit()
                    conn.close()
            elif event_type == "state_reset":
                group = payload.get("group")
                if group:
                    conn = get_state_db()
                    init_state_db(conn)
                    reset_state(conn, group)
                    conn.commit()
                    conn.close()
            set_last_event_id(SERVICE_NAME, last_id)

            if len(ingest_buffer) >= args.batch_size:
                flush_ingest(ingest_buffer)
                last_flush = time.monotonic()

        if ingest_buffer and (time.monotonic() - last_flush) >= args.flush_seconds:
            flush_ingest(ingest_buffer)
            last_flush = time.monotonic()

        if not processed:
            time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
