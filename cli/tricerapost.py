#!/usr/bin/env python3.13
import argparse
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from subprocess import DEVNULL, Popen


def _base_url() -> str:
    return os.environ.get("TRICERAPOST_API_URL", "http://127.0.0.1:8080").rstrip("/")


def _root_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pid_path() -> str:
    return os.environ.get("TRICERAPOST_PID_PATH", os.path.join(_root_dir(), "data", "tricerapost.pid"))


def _log_path() -> str:
    return os.environ.get("TRICERAPOST_LOG_PATH", os.path.join(_root_dir(), "data", "tricerapost.log"))


def _fetch_json(path: str, params: dict | None = None):
    url = _base_url() + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8") if exc.fp else str(exc)
        raise SystemExit(f"HTTP {exc.code}: {message}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Request failed: {exc}") from exc
    return json.loads(payload)


def _normalize_tag(raw: str) -> str:
    cleaned = raw.strip().lower()
    if cleaned in {"sdr", "hdr"}:
        return f"hdr:{cleaned}"
    return cleaned


def _read_pid() -> int | None:
    path = _pid_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return None


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def cmd_start(_args: argparse.Namespace) -> int:
    pid = _read_pid()
    if pid and _is_running(pid):
        print(f"Already running (pid {pid}).")
        return 0
    os.makedirs(os.path.dirname(_pid_path()), exist_ok=True)
    os.makedirs(os.path.dirname(_log_path()), exist_ok=True)
    log_handle = open(_log_path(), "a", encoding="utf-8")
    proc = Popen(
        [sys.executable, os.path.join(_root_dir(), "gui", "server.py")],
        stdout=log_handle,
        stderr=log_handle,
        stdin=DEVNULL,
        start_new_session=True,
    )
    with open(_pid_path(), "w", encoding="utf-8") as handle:
        handle.write(str(proc.pid))
    print(f"Started (pid {proc.pid}).")
    return 0


def cmd_stop(_args: argparse.Namespace) -> int:
    pid = _read_pid()
    if not pid:
        print("Not running (no pid file).")
        return 1
    if not _is_running(pid):
        print("Not running (stale pid file).")
        try:
            os.remove(_pid_path())
        except OSError:
            pass
        return 1
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 5
    while time.time() < deadline:
        if not _is_running(pid):
            break
        time.sleep(0.1)
    if _is_running(pid):
        os.kill(pid, signal.SIGKILL)
    try:
        os.remove(_pid_path())
    except OSError:
        pass
    print("Stopped.")
    return 0


def cmd_tags(_args: argparse.Namespace) -> int:
    tags = _fetch_json("/api/tags")
    for tag in tags:
        print(tag)
    return 0


def cmd_nzbs(args: argparse.Namespace) -> int:
    if args.tag:
        tag_value = _normalize_tag(args.tag)
        nzbs = _fetch_json("/api/nzbs/by_tag", {"tag": tag_value})
    else:
        nzbs = _fetch_json("/api/nzbs")
    print(json.dumps(nzbs, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="TriceraPost")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="Start the local API server")
    start_parser.set_defaults(func=cmd_start)

    stop_parser = subparsers.add_parser("stop", help="Stop the local API server")
    stop_parser.set_defaults(func=cmd_stop)

    tags_parser = subparsers.add_parser("tags", help="List all tags")
    tags_parser.set_defaults(func=cmd_tags)

    nzbs_parser = subparsers.add_parser("nzbs", help="List NZBs")
    nzbs_parser.add_argument("--tag", help="Filter by tag (e.g. SDR or hdr:sdr)")
    nzbs_parser.set_defaults(func=cmd_nzbs)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
