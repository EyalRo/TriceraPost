#!/usr/bin/env python3.13
import hashlib
import os
import random
import re
import sqlite3
from typing import Optional

from app.nntp_client import NNTPClient
from app.db import get_nzb_db, get_nzb_db_readonly, init_nzb_db
from app.ingest import load_env
from app.settings import get_bool_setting, get_int_setting, get_setting

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_NZB_DIR = os.path.join(BASE_DIR, "nzbs")


def _nzb_dir() -> str:
    override = get_setting("TRICERAPOST_NZB_DIR")
    if override:
        return override
    return DEFAULT_NZB_DIR


def _auto_save_enabled() -> bool:
    return get_bool_setting("TRICERAPOST_SAVE_NZBS", True)


def ensure_nzb_dir() -> str:
    path = _nzb_dir()
    os.makedirs(path, exist_ok=True)
    return path


def sanitize_filename(name: str) -> str:
    name = (name or "nzb").strip()
    name = re.sub(r"[^\w\s.-]", "_", name, flags=re.ASCII)
    name = re.sub(r"\s+", "_", name).strip("_")
    return name or "nzb"


def build_nzb_key(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()


def find_nzb_by_release(release_key: str) -> Optional[str]:
    if not release_key:
        return None
    conn = get_nzb_db_readonly()
    if conn is None:
        return None
    row = conn.execute("SELECT key FROM nzbs WHERE release_key = ?", (release_key,)).fetchone()
    conn.close()
    return row["key"] if row else None


def store_nzb_payload(
    *,
    name: str,
    payload: bytes,
    source: str,
    group_name: Optional[str] = None,
    poster: Optional[str] = None,
    release_key: Optional[str] = None,
    nzb_source_subject: Optional[str] = None,
    nzb_article: Optional[int] = None,
    nzb_message_id: Optional[str] = None,
) -> tuple[str, str]:
    seed = "|".join(
        [
            source or "",
            release_key or "",
            nzb_message_id or "",
            name or "",
            group_name or "",
        ]
    )
    key = build_nzb_key(seed)

    conn = get_nzb_db()
    init_nzb_db(conn)
    existing = conn.execute("SELECT key, path FROM nzbs WHERE key = ?", (key,)).fetchone()
    if existing:
        conn.close()
        return existing["key"], existing["path"]

    filename = sanitize_filename(name)
    if not filename.lower().endswith(".nzb"):
        filename = f"{filename}.nzb"
    path = ""

    conn.execute(
        """
        INSERT INTO nzbs(
            key, name, source, group_name, poster, release_key,
            nzb_source_subject, nzb_article, nzb_message_id, bytes, path, payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            key,
            name,
            source,
            group_name,
            poster,
            release_key,
            nzb_source_subject,
            nzb_article,
            nzb_message_id,
            len(payload),
            path,
            sqlite3.Binary(payload),
        ),
    )
    conn.commit()
    conn.close()

    if _auto_save_enabled():
        saved_path = save_nzb_to_disk(key)
        if saved_path:
            _update_nzb_path(key, saved_path)
            path = saved_path
    return key, path


def store_nzb_invalid(
    *,
    name: str,
    source: str,
    reason: str,
    release_key: Optional[str] = None,
    payload: Optional[bytes] = None,
) -> None:
    conn = get_nzb_db()
    init_nzb_db(conn)
    key = build_nzb_key("|".join([source or "", release_key or "", name or ""]))
    conn.execute(
        """
        INSERT OR REPLACE INTO nzb_invalid(key, name, source, release_key, reason, payload)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (key, name, source, release_key, reason, sqlite3.Binary(payload) if payload else None),
    )
    conn.commit()
    conn.close()


def _update_nzb_path(key: str, path: str) -> None:
    conn = get_nzb_db()
    init_nzb_db(conn)
    conn.execute("UPDATE nzbs SET path = ? WHERE key = ?", (path, key))
    conn.commit()
    conn.close()


def save_nzb_to_disk(key: str, directory: Optional[str] = None) -> Optional[str]:
    conn = get_nzb_db_readonly()
    if conn is None:
        return None
    row = conn.execute("SELECT name, payload FROM nzbs WHERE key = ?", (key,)).fetchone()
    conn.close()
    if not row:
        return None
    payload = row["payload"]
    if payload is None:
        return None

    filename = sanitize_filename(row["name"] or "nzb")
    if not filename.lower().endswith(".nzb"):
        filename = f"{filename}.nzb"
    target_dir = directory or _nzb_dir()
    path = os.path.join(target_dir, f"{key[:8]}_{filename}")
    try:
        os.makedirs(target_dir, exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(payload)
    except OSError:
        return None
    return path


def save_all_nzbs_to_disk(directory: Optional[str] = None) -> int:
    conn = get_nzb_db_readonly()
    if conn is None:
        return 0
    rows = conn.execute("SELECT key, path FROM nzbs").fetchall()
    conn.close()
    saved = 0
    for row in rows:
        key = row["key"]
        path = row["path"] or ""
        if path and os.path.exists(path):
            continue
        saved_path = save_nzb_to_disk(key, directory)
        if saved_path:
            _update_nzb_path(key, saved_path)
            saved += 1
    return saved


def _connect_nntp() -> Optional[NNTPClient]:
    load_env()
    host = get_setting("NNTP_HOST")
    if not host:
        return None
    port = get_int_setting("NNTP_PORT", 119)
    use_ssl = get_bool_setting("NNTP_SSL")
    user = get_setting("NNTP_USER")
    password = get_setting("NNTP_PASS")

    client = NNTPClient(host, port, use_ssl=use_ssl)
    try:
        client.connect()
        client.reader_mode()
        client.auth(user, password)
    except Exception:
        try:
            client.quit()
        except Exception:
            pass
        raise
    return client


def verify_message_ids(message_ids: list[str]) -> tuple[bool, Optional[str]]:
    if not message_ids:
        return False, "no segments"

    sample = get_int_setting("TRICERAPOST_NZB_VERIFY_SAMPLE", 0)
    targets = message_ids
    if sample > 0 and len(message_ids) > sample:
        head = message_ids[:1]
        tail = message_ids[-1:]
        middle = message_ids[1:-1]
        pick = random.sample(middle, min(sample - len(head) - len(tail), len(middle))) if middle else []
        targets = list(dict.fromkeys(head + pick + tail))

    try:
        client = _connect_nntp()
        if client is None:
            return False, "NNTP_HOST not set"
        for msg_id in targets:
            msg = msg_id.strip()
            if not msg:
                return False, "missing message-id"
            if not msg.startswith("<"):
                msg = f"<{msg}>"
            client.stat(msg)
        return True, None
    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            if "client" in locals() and client is not None:
                client.quit()
        except Exception:
            pass
