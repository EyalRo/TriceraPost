#!/usr/bin/env python3
import json
import os
import sqlite3
import time
from typing import Iterator, Optional


def _bool_env(key: str) -> bool:
    return os.environ.get(key, "").strip().lower() in {"1", "true", "yes", "y"}


def _events_base_dir() -> str:
    if _bool_env("TRICERAPOST_DB_IN_MEMORY"):
        return os.environ.get("TRICERAPOST_DB_DIR", "/dev/shm/tricerapost")
    return os.environ.get("TRICERAPOST_DB_DIR", "data")


EVENTS_DB_PATH = os.environ.get("TRICERAPOST_EVENTS_DB", os.path.join(_events_base_dir(), "events.db"))


def get_event_db(path: Optional[str] = None) -> sqlite3.Connection:
    db_path = path or EVENTS_DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if db_path.startswith("file:"):
        conn = sqlite3.connect(db_path, timeout=30, uri=True)
    else:
        conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_event_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cursors (
            service TEXT PRIMARY KEY,
            last_event_id INTEGER NOT NULL
        )
        """
    )
    conn.commit()


def publish_event(event_type: str, payload: dict) -> int:
    for attempt in range(5):
        conn = get_event_db()
        init_event_db(conn)
        try:
            cur = conn.execute(
                "INSERT INTO events(type, payload) VALUES(?, ?)",
                (event_type, json.dumps(payload)),
            )
            conn.commit()
            event_id = cur.lastrowid
            return event_id
        except Exception as exc:
            if "locked" not in str(exc).lower() or attempt == 4:
                raise
            time.sleep(0.2 * (attempt + 1))
        finally:
            conn.close()
    raise RuntimeError("Failed to publish event")


def get_last_event_id(service: str) -> int:
    conn = get_event_db()
    init_event_db(conn)
    row = conn.execute("SELECT last_event_id FROM cursors WHERE service = ?", (service,)).fetchone()
    conn.close()
    return int(row["last_event_id"]) if row else 0


def set_last_event_id(service: str, event_id: int) -> None:
    conn = get_event_db()
    init_event_db(conn)
    conn.execute(
        "INSERT INTO cursors(service, last_event_id) VALUES(?, ?) "
        "ON CONFLICT(service) DO UPDATE SET last_event_id=excluded.last_event_id",
        (service, int(event_id)),
    )
    conn.commit()
    conn.close()


def iter_events(after_id: int, limit: int = 200) -> Iterator[dict]:
    conn = get_event_db()
    init_event_db(conn)
    rows = conn.execute(
        "SELECT id, type, payload, created_at FROM events WHERE id > ? ORDER BY id LIMIT ?",
        (int(after_id), int(limit)),
    ).fetchall()
    conn.close()
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            payload = {}
        yield {
            "id": row["id"],
            "type": row["type"],
            "payload": payload,
            "created_at": row["created_at"],
        }
