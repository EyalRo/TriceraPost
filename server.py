#!/usr/bin/env python3
import json
import os
import re
import select
import sys
import threading
import time
import tty
import termios
from typing import Optional

from services.db import (
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
from services.ingest import load_env
from services.nzb_store import save_all_nzbs_to_disk
from services.settings import get_bool_setting, get_int_setting, get_setting, load_settings, save_settings
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
GROUPS_PATH = os.path.join(BASE_DIR, "groups.json")


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
    rows = conn.execute(
        """
        SELECT key, name, source, group_name, poster, release_key, bytes, path, created_at
        FROM nzbs
        ORDER BY created_at DESC
        """
    ).fetchall()
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
        }
        for row in rows
    ]


def read_nzb_payload(key: str) -> tuple[Optional[str], Optional[bytes], Optional[str]]:
    conn = get_nzb_db_readonly()
    if conn is None:
        return None, None, None
    row = conn.execute("SELECT name, payload, path FROM nzbs WHERE key = ?", (key,)).fetchone()
    conn.close()
    if not row:
        return None, None, None
    return row["name"], row["payload"], row["path"]


def clear_db() -> dict:
    db_paths = [
        STATE_DB_PATH,
        INGEST_DB_PATH,
        RELEASES_DB_PATH,
        COMPLETE_DB_PATH,
        NZB_DB_PATH,
    ]
    removed = []
    failed = []
    for path in db_paths:
        if not path:
            continue
        try:
            if os.path.exists(path):
                os.remove(path)
                removed.append(path)
        except Exception as exc:
            failed.append({"path": path, "error": str(exc)})

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
    def _coerce_bool(self, value, default=False):
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "y"}

    def _coerce_int(self, value, default):
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _settings_payload(self):
        return {
            "NNTP_HOST": get_setting("NNTP_HOST", ""),
            "NNTP_PORT": get_int_setting("NNTP_PORT", 119),
            "NNTP_SSL": get_bool_setting("NNTP_SSL", False),
            "NNTP_USER": get_setting("NNTP_USER", ""),
            "NNTP_PASS_SET": bool(get_setting("NNTP_PASS")),
            "NNTP_LOOKBACK": get_int_setting("NNTP_LOOKBACK", 2000),
            "NNTP_GROUPS": get_setting("NNTP_GROUPS", ""),
            "TRICERAPOST_SCHEDULER_INTERVAL": get_int_setting("TRICERAPOST_SCHEDULER_INTERVAL", 0),
            "TRICERAPOST_SAVE_NZBS": get_bool_setting("TRICERAPOST_SAVE_NZBS", True),
            "TRICERAPOST_NZB_DIR": get_setting("TRICERAPOST_NZB_DIR", ""),
        }
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

    def _send_bytes(self, data: bytes, content_type: str, filename: Optional[str] = None):
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

        if path == "/":
            return self._send_file(os.path.join(WEB_DIR, "index.html"), "text/html; charset=utf-8")
        if path == "/settings":
            return self._send_file(os.path.join(WEB_DIR, "settings.html"), "text/html; charset=utf-8")
        if path == "/permissions":
            return self._send_file(os.path.join(WEB_DIR, "permissions.html"), "text/html; charset=utf-8")
        if path == "/assets/style.css":
            return self._send_file(os.path.join(WEB_DIR, "style.css"), "text/css; charset=utf-8")
        if path == "/assets/icon.png":
            return self._send_file(os.path.join(WEB_DIR, "icon.png"), "image/png")
        if path == "/assets/app.js":
            return self._send_file(os.path.join(WEB_DIR, "app.js"), "text/javascript; charset=utf-8")
        if path == "/assets/settings.js":
            return self._send_file(os.path.join(WEB_DIR, "settings.js"), "text/javascript; charset=utf-8")

        if path == "/api/releases":
            return self._send_json(read_releases("releases_complete"))
        if path == "/api/releases/raw":
            return self._send_json(read_releases("releases"))
        if path == "/api/nzbs":
            return self._send_json(read_nzbs())
        if path == "/api/status":
            return self._send_json(read_status())
        if path == "/api/status/stream":
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
        if path == "/api/nzb/file":
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
        if path == "/api/groups":
            return self._send_json(read_json(GROUPS_PATH, []))
        if path == "/api/settings":
            return self._send_json(self._settings_payload())

        return self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/settings":
            raw = self._read_body()
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)

            settings = load_settings()
            clear_password = bool(payload.get("clear_password"))
            if clear_password:
                settings.pop("NNTP_PASS", None)

            if "NNTP_PASS" in payload and payload.get("NNTP_PASS"):
                settings["NNTP_PASS"] = str(payload.get("NNTP_PASS")).strip()

            if "TRICERAPOST_SAVE_NZBS" in payload:
                settings["TRICERAPOST_SAVE_NZBS"] = self._coerce_bool(
                    payload.get("TRICERAPOST_SAVE_NZBS"),
                    True,
                )
            if "TRICERAPOST_NZB_DIR" in payload:
                nzb_dir = str(payload.get("TRICERAPOST_NZB_DIR") or "").strip()
                if nzb_dir:
                    settings["TRICERAPOST_NZB_DIR"] = nzb_dir
                else:
                    settings.pop("TRICERAPOST_NZB_DIR", None)

            for key in ("NNTP_HOST", "NNTP_USER", "NNTP_GROUPS"):
                if key in payload:
                    value = payload.get(key)
                    if value is None or str(value).strip() == "":
                        settings.pop(key, None)
                    else:
                        settings[key] = str(value).strip()

            for key, default in (
                ("NNTP_PORT", 119),
                ("NNTP_LOOKBACK", 2000),
                ("TRICERAPOST_SCHEDULER_INTERVAL", 0),
            ):
                if key in payload:
                    value = payload.get(key)
                    if value is None or value == "":
                        settings.pop(key, None)
                    else:
                        settings[key] = self._coerce_int(value, default)

            if "NNTP_SSL" in payload:
                settings["NNTP_SSL"] = self._coerce_bool(payload.get("NNTP_SSL"), False)

            save_settings(settings)
            return self._send_json({"ok": True, "settings": self._settings_payload()})
        if path == "/api/nzb/save_all":
            count = save_all_nzbs_to_disk(get_setting("TRICERAPOST_NZB_DIR") or None)
            return self._send_json({"ok": True, "saved": count})
        if path == "/api/admin/clear_db":
            raw = self._read_body()
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            if not payload.get("confirm"):
                return self._send_json({"ok": False, "error": "Confirmation required"}, HTTPStatus.BAD_REQUEST)
            result = clear_db()
            return self._send_json({"ok": True, **result})

        return self.send_error(HTTPStatus.NOT_FOUND)



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
    host = os.environ.get("TRICERAPOST_BIND_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving on http://{host}:{port}")
    print("Press Ctrl+C or type 'q' then Enter to stop.")

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
