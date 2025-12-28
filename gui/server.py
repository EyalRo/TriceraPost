#!/usr/bin/env python3.13
import json
import logging
import os
import re
import select
import sqlite3
import sys
import threading
import time
import tty
import termios

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.db import (
    COMPLETE_DB_PATH,
    INGEST_DB_PATH,
    NZB_DB_PATH,
    RELEASES_DB_PATH,
    STATE_DB_PATH,
    get_complete_db_readonly,
    get_ingest_db_readonly,
    get_nzb_db_readonly,
    get_releases_db_readonly,
    get_state_db_readonly,
)
from app.ingest import load_env
from app.logging_setup import configure_logging
from app.nzb_store import save_all_nzbs_to_disk
from app.settings import get_setting
from gui.http_assets import asset_info
from gui.settings_api import apply_settings_payload, build_settings_payload
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
GROUPS_PATH = os.path.join(ROOT_DIR, "groups.json")
LOGGER = logging.getLogger("tricerapost")


def read_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def read_releases(table):
    if table == "releases_complete":
        conn = get_complete_db_readonly()
    else:
        conn = get_releases_db_readonly()
    if conn is None:
        return []
    if table == "releases_complete":
        nzb_keys = load_nzb_release_keys()
        rows = conn.execute("SELECT * FROM releases_complete").fetchall()
        payload = []
        for row in rows:
            name_value = str(row["name"] or "").lower()
            if "xxx" in name_value or "porn" in name_value:
                continue
            if "part" in name_value or name_value.endswith(".rar"):
                continue
            payload.append(
                {
                    "key": row["key"],
                    "name": row["name"],
                    "normalized_name": row["normalized_name"] if "normalized_name" in row.keys() else "",
                    "filename_guess": row["filename_guess"],
                    "nzb_fetch_failed": bool(row["nzb_fetch_failed"]),
                    "nzb_source_subject": row["nzb_source_subject"],
                    "nzb_article": row["nzb_article"],
                    "nzb_message_id": row["nzb_message_id"],
                    "groups": json.loads(row["groups"]) if row["groups"] else [],
                    "poster": row["poster"],
                    "bytes": row["bytes"],
                    "size_human": row["size_human"],
                    "first_seen": row["first_seen"],
                    "last_seen": row["last_seen"],
                    "parts_expected": row["parts_expected"],
                    "parts_received": row["parts_received"],
                    "type": row["type"],
                    "quality": row["quality"],
                    "source": row["source"],
                    "codec": row["codec"],
                    "audio": row["audio"],
                    "languages": json.loads(row["languages"]) if row["languages"] else [],
                    "subtitles": bool(row["subtitles"]),
                    "tags": (
                        json.loads(row["tags"])
                        if "tags" in row.keys() and row["tags"]
                        else []
                    ),
                    "nzb_created": row["key"] in nzb_keys,
                }
            )
        conn.close()
        return payload

    rows = conn.execute("SELECT * FROM releases").fetchall()
    payload = []
    for row in rows:
        payload.append(
            {
                "key": row["key"],
                "name": row["name"],
                "normalized_name": row["normalized_name"],
                "filename_hint": row["filename_hint"],
                "poster": row["poster"],
                "group": row["group_name"],
                "source": row["source"],
                "message_id": row["message_id"],
                "nzb_source_subject": row["nzb_source_subject"],
                "nzb_article": row["nzb_article"],
                "nzb_message_id": row["nzb_message_id"],
                "nzb_fetch_failed": bool(row["nzb_fetch_failed"]),
                "first_seen": row["first_seen"],
                "last_seen": row["last_seen"],
                "bytes": row["bytes"],
                "size_human": row["size_human"],
                "parts_received": row["parts_received"],
                "parts_expected": row["parts_expected"],
                "part_numbers": json.loads(row["part_numbers"]) if row["part_numbers"] else [],
                "part_total": row["part_total"],
                "articles": row["articles"],
                "subjects": json.loads(row["subjects"]) if row["subjects"] else [],
            }
        )
    conn.close()
    return payload


def _count_rows(conn, query, params=None) -> int:
    if conn is None:
        return 0
    try:
        row = conn.execute(query, params or ()).fetchone()
    except Exception:
        return 0
    if row is None:
        return 0
    return int(list(row)[0] or 0)


def read_status() -> dict:
    state_conn = get_state_db_readonly()
    ingest_conn = get_ingest_db_readonly()
    releases_conn = get_complete_db_readonly()
    nzb_conn = get_nzb_db_readonly()

    status = {
        "groups_scanned": _count_rows(state_conn, "SELECT COUNT(*) FROM state"),
        "posts_scanned": _count_rows(ingest_conn, "SELECT COUNT(*) FROM ingest WHERE type = 'header'"),
        "sets_found": _count_rows(releases_conn, "SELECT COUNT(*) FROM releases_complete"),
        "sets_rejected": _count_rows(nzb_conn, "SELECT COUNT(*) FROM nzb_invalid"),
        "nzbs_found": _count_rows(nzb_conn, "SELECT COUNT(*) FROM nzbs WHERE source = 'found'"),
        "nzbs_generated": _count_rows(nzb_conn, "SELECT COUNT(*) FROM nzbs WHERE source = 'generated'"),
    }

    for conn in (state_conn, ingest_conn, releases_conn, nzb_conn):
        if conn is not None:
            conn.close()
    return status


def load_nzb_release_keys() -> set[str]:
    conn = get_nzb_db_readonly()
    if conn is None:
        return set()
    rows = conn.execute("SELECT release_key FROM nzbs WHERE release_key IS NOT NULL").fetchall()
    conn.close()
    return {row["release_key"] for row in rows if row["release_key"]}


def read_nzbs() -> list[dict]:
    conn = get_nzb_db_readonly()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT key, name, source, group_name, poster, release_key, bytes, path, created_at, tags
            FROM nzbs
            ORDER BY created_at DESC
            """
        ).fetchall()
        has_tags = True
    except sqlite3.OperationalError:
        rows = conn.execute(
            """
            SELECT key, name, source, group_name, poster, release_key, bytes, path, created_at
            FROM nzbs
            ORDER BY created_at DESC
            """
        ).fetchall()
        has_tags = False
    conn.close()
    return [
        {
            "key": row["key"],
            "name": row["name"],
            "source": row["source"],
            "group": row["group_name"],
            "poster": row["poster"],
            "release_key": row["release_key"],
            "bytes": row["bytes"],
            "path": row["path"],
            "created_at": row["created_at"],
            "tags": json.loads(row["tags"]) if has_tags and row["tags"] else [],
        }
        for row in rows
    ]


def _collect_tags(raw_values: list[str]) -> list[str]:
    tags = set()
    for raw in raw_values:
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            tags.update(str(tag) for tag in parsed if tag)
    return sorted(tags)


def read_all_tags() -> list[str]:
    tags = set()
    nzb_conn = get_nzb_db_readonly()
    if nzb_conn is not None:
        try:
            rows = nzb_conn.execute("SELECT tags FROM nzbs").fetchall()
        except sqlite3.OperationalError:
            rows = []
        nzb_conn.close()
        tags.update(_collect_tags([row["tags"] for row in rows if row["tags"]]))

    complete_conn = get_complete_db_readonly()
    if complete_conn is not None:
        try:
            rows = complete_conn.execute("SELECT tags FROM releases_complete").fetchall()
        except sqlite3.OperationalError:
            rows = []
        complete_conn.close()
        tags.update(_collect_tags([row["tags"] for row in rows if row["tags"]]))

    return sorted(tags)


def read_nzbs_by_tag(tag: str) -> list[dict]:
    if not tag:
        return []
    tag_value = tag.strip().lower()
    results = []
    for entry in read_nzbs():
        tags = [str(t).lower() for t in entry.get("tags") or []]
        if tag_value in tags:
            results.append(entry)
    return results


def read_nzb_payload(key: str) -> tuple[str | None, bytes | None, str | None]:
    conn = get_nzb_db_readonly()
    if conn is None:
        return None, None, None
    row = conn.execute("SELECT name, payload, path FROM nzbs WHERE key = ?", (key,)).fetchone()
    conn.close()
    if not row:
        return None, None, None
    return row["name"], row["payload"], row["path"]


def clear_db() -> dict[str, list[object]]:
    db_paths = [
        STATE_DB_PATH,
        INGEST_DB_PATH,
        RELEASES_DB_PATH,
        COMPLETE_DB_PATH,
        NZB_DB_PATH,
    ]
    removed: list[str] = []
    failed: list[dict[str, str]] = []
    errors: list[Exception] = []
    for path in db_paths:
        if not path:
            continue
        try:
            if os.path.exists(path):
                os.remove(path)
                removed.append(path)
        except Exception as exc:
            failed.append({"path": path, "error": str(exc)})
            errors.append(exc)

    if errors:
        try:
            raise ExceptionGroup("Failed to remove DB files", errors)
        except* Exception as exc_group:
            LOGGER.error("Clear DB failures: %s", exc_group)

    return {"removed": removed, "failed": failed}


def _is_binary_group(name: str) -> bool:
    tokens = re.split(r"[._-]+", name.lower())
    return any(token in {"bin", "binary", "binaries"} for token in tokens)


def load_binary_groups() -> list[str]:
    override = get_setting("NNTP_GROUPS")
    if override:
        return [g.strip() for g in override.split(",") if g.strip()]
    groups = read_json(GROUPS_PATH, [])
    matches = []
    for entry in groups:
        name = str(entry.get("group", "")).strip()
        if not name:
            continue
        if _is_binary_group(name):
            matches.append(name)
    return sorted(set(matches))


class Handler(BaseHTTPRequestHandler):

    def _send_json(self, payload, status=HTTPStatus.OK):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            return

    def _send_bytes(self, data: bytes, content_type: str, filename: str | None = None):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            return

    def _send_text(self, text, status=HTTPStatus.OK):
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path, content_type):
        if not os.path.exists(path):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        with open(path, "rb") as handle:
            data = handle.read()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_error(self, code, message=None, explain=None):
        try:
            super().send_error(code, message, explain)
        except BrokenPipeError:
            return

    def _read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return b""
        return self.rfile.read(length)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        asset_info_result = asset_info(path)
        if asset_info_result:
            filename, content_type = asset_info_result
            return self._send_file(os.path.join(WEB_DIR, filename), content_type)

        match path:
            case "/":
                return self._send_file(os.path.join(WEB_DIR, "index.html"), "text/html; charset=utf-8")
            case "/settings":
                return self._send_file(os.path.join(WEB_DIR, "settings.html"), "text/html; charset=utf-8")
            case "/permissions":
                return self._send_file(os.path.join(WEB_DIR, "permissions.html"), "text/html; charset=utf-8")
            case "/api/releases":
                return self._send_json(read_releases("releases_complete"))
            case "/api/releases/raw":
                return self._send_json(read_releases("releases"))
            case "/api/nzbs":
                return self._send_json(read_nzbs())
            case "/api/tags":
                return self._send_json(read_all_tags())
            case "/api/status":
                return self._send_json(read_status())
            case "/api/status/stream":
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                try:
                    while True:
                        payload = json.dumps(read_status())
                        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        time.sleep(2)
                except (BrokenPipeError, ConnectionResetError):
                    return
            case "/api/nzb/file":
                query = parse_qs(parsed.query)
                key = (query.get("key") or [None])[0]
                if not key:
                    return self._send_json({"ok": False, "error": "Missing key"}, HTTPStatus.BAD_REQUEST)
                name, payload, path_info = read_nzb_payload(key)
                if not name and not payload and not path_info:
                    return self._send_json({"ok": False, "error": "Not found"}, HTTPStatus.NOT_FOUND)
                filename = name or "release"
                if not filename.lower().endswith(".nzb"):
                    filename = f"{filename}.nzb"
                if payload is not None:
                    return self._send_bytes(payload, "application/x-nzb", filename)
                if path_info and os.path.exists(path_info):
                    with open(path_info, "rb") as handle:
                        data = handle.read()
                    return self._send_bytes(data, "application/x-nzb", filename)
                return self._send_json({"ok": False, "error": "Missing payload"}, HTTPStatus.NOT_FOUND)
            case "/api/groups":
                return self._send_json(read_json(GROUPS_PATH, []))
            case "/api/settings":
                return self._send_json(build_settings_payload())
            case "/api/nzbs/by_tag":
                query = parse_qs(parsed.query)
                tag = (query.get("tag") or [None])[0]
                if not tag:
                    return self._send_json({"ok": False, "error": "Missing tag"}, HTTPStatus.BAD_REQUEST)
                return self._send_json(read_nzbs_by_tag(str(tag)))
            case _:
                return self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        match path:
            case "/api/settings":
                raw = self._read_body()
                try:
                    payload = json.loads(raw.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    return self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
                settings_payload = apply_settings_payload(payload)
                return self._send_json({"ok": True, "settings": settings_payload})
            case "/api/nzb/save_all":
                count = save_all_nzbs_to_disk(get_setting("TRICERAPOST_NZB_DIR") or None)
                return self._send_json({"ok": True, "saved": count})
            case "/api/admin/clear_db":
                raw = self._read_body()
                try:
                    payload = json.loads(raw.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    return self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
                if not payload.get("confirm"):
                    return self._send_json({"ok": False, "error": "Confirmation required"}, HTTPStatus.BAD_REQUEST)
                result = clear_db()
                return self._send_json({"ok": True, **result})
            case _:
                return self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format, *args):
        logging.getLogger("tricerapost.http").info(
            "%s - - %s", self.client_address[0], format % args
        )

    def log_error(self, format, *args):
        logging.getLogger("tricerapost.http").error(
            "%s - - %s", self.client_address[0], format % args
        )



def wait_for_quit(server, stop_event):
    if not sys.stdin.isatty():
        while not stop_event.is_set():
            ready, _, _ = select.select([sys.stdin], [], [], 0.2)
            if not ready:
                continue
            line = sys.stdin.readline()
            if line.strip().lower() == "q":
                server.shutdown()
                break
        return

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while not stop_event.is_set():
            ready, _, _ = select.select([sys.stdin], [], [], 0.2)
            if not ready:
                continue
            ch = sys.stdin.read(1)
            if ch.lower() == "q":
                server.shutdown()
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def main():
    load_env()
    configure_logging()
    host = os.environ.get("TRICERAPOST_BIND_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    httpd = ThreadingHTTPServer((host, port), Handler)
    LOGGER.info("Serving on http://%s:%s", host, port)
    LOGGER.info("Press Ctrl+C or type 'q' then Enter to stop.")

    stop_event = threading.Event()
    quit_thread = threading.Thread(target=wait_for_quit, args=(httpd, stop_event))
    quit_thread.start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
    finally:
        stop_event.set()
        quit_thread.join(timeout=1.0)
        httpd.server_close()


if __name__ == "__main__":
    main()
