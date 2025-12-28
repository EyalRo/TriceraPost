#!/usr/bin/env python3.13
import os
import sqlite3
from typing import Optional

def _bool_env(key: str) -> bool:
    return os.environ.get(key, "").strip().lower() in {"1", "true", "yes", "y"}


def _default_base_dir() -> str:
    if _bool_env("TRICERAPOST_DB_IN_MEMORY"):
        return os.environ.get("TRICERAPOST_DB_DIR", "/dev/shm/tricerapost")
    return os.environ.get("TRICERAPOST_DB_DIR", "data")


BASE_DIR = _default_base_dir()
UNIFIED_DB_PATH = os.environ.get("TRICERAPOST_DB_PATH")

STATE_DB_PATH = os.environ.get(
    "TRICERAPOST_STATE_DB",
    UNIFIED_DB_PATH or os.path.join(BASE_DIR, "tricerapost_state.db"),
)
INGEST_DB_PATH = os.environ.get(
    "TRICERAPOST_INGEST_DB",
    UNIFIED_DB_PATH or os.path.join(BASE_DIR, "tricerapost_ingest.db"),
)
RELEASES_DB_PATH = os.environ.get(
    "TRICERAPOST_RELEASES_DB",
    UNIFIED_DB_PATH or os.path.join(BASE_DIR, "tricerapost_releases.db"),
)
COMPLETE_DB_PATH = os.environ.get(
    "TRICERAPOST_COMPLETE_DB",
    UNIFIED_DB_PATH or os.path.join(BASE_DIR, "tricerapost_releases_complete.db"),
)
NZB_DB_PATH = os.environ.get(
    "TRICERAPOST_NZB_DB",
    UNIFIED_DB_PATH or os.path.join(BASE_DIR, "tricerapost_nzbs.db"),
)


def _connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if path.startswith("file:"):
        conn = sqlite3.connect(path, timeout=30, uri=True)
    else:
        conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_readonly(path: str) -> Optional[sqlite3.Connection]:
    if not os.path.exists(path):
        return None
    if _bool_env("TRICERAPOST_DB_IN_MEMORY"):
        conn = sqlite3.connect(path, timeout=30, uri=path.startswith("file:"))
    else:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")


def get_state_db(path: Optional[str] = None) -> sqlite3.Connection:
    return _connect(path or STATE_DB_PATH)


def get_ingest_db(path: Optional[str] = None) -> sqlite3.Connection:
    return _connect(path or INGEST_DB_PATH)


def get_releases_db(path: Optional[str] = None) -> sqlite3.Connection:
    return _connect(path or RELEASES_DB_PATH)


def get_complete_db(path: Optional[str] = None) -> sqlite3.Connection:
    return _connect(path or COMPLETE_DB_PATH)

def get_nzb_db(path: Optional[str] = None) -> sqlite3.Connection:
    return _connect(path or NZB_DB_PATH)


def get_state_db_readonly(path: Optional[str] = None) -> Optional[sqlite3.Connection]:
    return _connect_readonly(path or STATE_DB_PATH)


def get_ingest_db_readonly(path: Optional[str] = None) -> Optional[sqlite3.Connection]:
    return _connect_readonly(path or INGEST_DB_PATH)


def get_releases_db_readonly(path: Optional[str] = None) -> Optional[sqlite3.Connection]:
    return _connect_readonly(path or RELEASES_DB_PATH)


def get_complete_db_readonly(path: Optional[str] = None) -> Optional[sqlite3.Connection]:
    return _connect_readonly(path or COMPLETE_DB_PATH)

def get_nzb_db_readonly(path: Optional[str] = None) -> Optional[sqlite3.Connection]:
    return _connect_readonly(path or NZB_DB_PATH)


def init_state_db(conn: sqlite3.Connection) -> None:
    _apply_pragmas(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS state (
            group_name TEXT PRIMARY KEY,
            last_article INTEGER NOT NULL
        )
        """
    )
    conn.commit()


def init_ingest_db(conn: sqlite3.Connection) -> None:
    _apply_pragmas(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ingest (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT NOT NULL,
            type TEXT NOT NULL,
            article INTEGER,
            subject TEXT,
            poster TEXT,
            date TEXT,
            bytes INTEGER,
            message_id TEXT,
            payload TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ingest_group ON ingest(group_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ingest_type ON ingest(type)")
    conn.commit()


def init_releases_db(conn: sqlite3.Connection) -> None:
    _apply_pragmas(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS releases (
            key TEXT PRIMARY KEY,
            name TEXT,
            normalized_name TEXT,
            filename_hint TEXT,
            poster TEXT,
            group_name TEXT,
            source TEXT,
            message_id TEXT,
            nzb_source_subject TEXT,
            nzb_article INTEGER,
            nzb_message_id TEXT,
            nzb_fetch_failed INTEGER DEFAULT 0,
            first_seen TEXT,
            last_seen TEXT,
            bytes INTEGER,
            size_human TEXT,
            parts_received INTEGER,
            parts_expected INTEGER,
            part_numbers TEXT,
            part_total INTEGER,
            articles INTEGER,
            subjects TEXT
        )
        """
    )
    conn.commit()


def init_complete_db(conn: sqlite3.Connection) -> None:
    _apply_pragmas(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS releases_complete (
            key TEXT PRIMARY KEY,
            name TEXT,
            normalized_name TEXT,
            filename_guess TEXT,
            nzb_fetch_failed INTEGER DEFAULT 0,
            nzb_source_subject TEXT,
            nzb_article INTEGER,
            nzb_message_id TEXT,
            download_failed INTEGER DEFAULT 0,
            groups TEXT,
            poster TEXT,
            bytes INTEGER,
            size_human TEXT,
            first_seen TEXT,
            last_seen TEXT,
            parts_expected INTEGER,
            parts_received INTEGER,
            type TEXT,
            quality TEXT,
            source TEXT,
            codec TEXT,
            audio TEXT,
            languages TEXT,
            subtitles INTEGER DEFAULT 0,
            tags TEXT
        )
        """
    )
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(releases_complete)")}
    if "normalized_name" not in cols:
        conn.execute("ALTER TABLE releases_complete ADD COLUMN normalized_name TEXT")
    if "nzb_article" not in cols:
        conn.execute("ALTER TABLE releases_complete ADD COLUMN nzb_article INTEGER")
    if "nzb_message_id" not in cols:
        conn.execute("ALTER TABLE releases_complete ADD COLUMN nzb_message_id TEXT")
    if "download_failed" not in cols:
        conn.execute("ALTER TABLE releases_complete ADD COLUMN download_failed INTEGER DEFAULT 0")
    if "tags" not in cols:
        conn.execute("ALTER TABLE releases_complete ADD COLUMN tags TEXT")
    conn.commit()


def init_nzb_db(conn: sqlite3.Connection) -> None:
    _apply_pragmas(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS nzbs (
            key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source TEXT NOT NULL,
            group_name TEXT,
            poster TEXT,
            release_key TEXT,
            nzb_source_subject TEXT,
            nzb_article INTEGER,
            nzb_message_id TEXT,
            bytes INTEGER DEFAULT 0,
            path TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            tags TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS nzb_invalid (
            key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source TEXT NOT NULL,
            release_key TEXT,
            reason TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cols = {row[1] for row in conn.execute("PRAGMA table_info(nzbs)").fetchall()}
    if "payload" not in cols:
        conn.execute("ALTER TABLE nzbs ADD COLUMN payload BLOB")
    if "tags" not in cols:
        conn.execute("ALTER TABLE nzbs ADD COLUMN tags TEXT")
    cols_invalid = {row[1] for row in conn.execute("PRAGMA table_info(nzb_invalid)").fetchall()}
    if "payload" not in cols_invalid:
        conn.execute("ALTER TABLE nzb_invalid ADD COLUMN payload BLOB")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nzbs_release_key ON nzbs(release_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nzbs_source ON nzbs(source)")
    conn.commit()
