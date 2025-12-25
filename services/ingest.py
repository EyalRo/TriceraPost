#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from nntp_client import NNTPClient
from services.db import (
    get_ingest_db,
    get_state_db,
    get_state_db_readonly,
    init_ingest_db,
    init_state_db,
)
from services.release_utils import NZB_RE, parse_nzb, strip_article_headers


def load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def get_env_bool(key: str, default: bool = False) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y"}


def load_state(conn) -> dict:
    if conn is None:
        return {}
    try:
        rows = conn.execute("SELECT group_name, last_article FROM state").fetchall()
    except Exception:
        return {}
    return {row["group_name"]: int(row["last_article"]) for row in rows}


def save_state(conn, group_name: str, last_article: int) -> None:
    conn.execute(
        "INSERT INTO state(group_name, last_article) VALUES(?, ?) "
        "ON CONFLICT(group_name) DO UPDATE SET last_article=excluded.last_article",
        (group_name, int(last_article)),
    )


def parse_groups(args_group: str | None, env_group: str | None, env_groups: str | None) -> list[str]:
    if args_group:
        return [args_group]
    if env_groups:
        return [g.strip() for g in env_groups.split(",") if g.strip()]
    if env_group:
        return [env_group]
    return []


def append_record(conn, record: dict) -> None:
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
            json.dumps(record.get("payload")) if record.get("payload") is not None else None,
        ),
    )


def parse_overview(overview) -> tuple[str, str, str, int, str]:
    if isinstance(overview, dict):
        subject = overview.get("subject", "")
        poster = overview.get("from", "")
        date = overview.get("date", "")
        size_raw = overview.get("bytes", "0")
        message_id = overview.get("message-id", "")
    else:
        subject = overview[0] if len(overview) > 0 else ""
        poster = overview[1] if len(overview) > 1 else ""
        date = overview[2] if len(overview) > 2 else ""
        size_raw = overview[5] if len(overview) > 5 else "0"
        message_id = overview[3] if len(overview) > 3 else ""
    try:
        size = int(size_raw)
    except (TypeError, ValueError):
        size = 0
    return subject, poster, date, size, message_id


def ingest_groups(
    *,
    groups: list[str],
    lookback: int | None = None,
    reset: bool = False,
    emit_events: bool = False,
    parse_nzb: bool | None = None,
    progress_seconds: int = 10,
) -> None:
    if parse_nzb is None:
        parse_nzb = not emit_events
    if emit_events:
        parse_nzb = False

    load_env()

    host = os.environ.get("NNTP_HOST")
    if not host:
        print("NNTP_HOST not set in .env")
        return

    port = int(os.environ.get("NNTP_PORT", "119"))
    use_ssl = get_env_bool("NNTP_SSL")
    user = os.environ.get("NNTP_USER")
    password = os.environ.get("NNTP_PASS")

    lookback = lookback or int(os.environ.get("NNTP_LOOKBACK", "2000"))

    state_conn = get_state_db() if not emit_events else get_state_db_readonly()
    if state_conn and not emit_events:
        init_state_db(state_conn)
    state = load_state(state_conn)

    ingest_conn = None
    if not emit_events:
        ingest_conn = get_ingest_db()
        init_ingest_db(ingest_conn)

    if emit_events:
        from services.event_bus import publish_event
    else:
        publish_event = None

    for group in groups:
        if reset:
            if emit_events:
                publish_event("state_reset", {"group": group})
            else:
                state_conn.execute("DELETE FROM state WHERE group_name = ?", (group,))
            state.pop(group, None)

    client = NNTPClient(host, port, use_ssl=use_ssl)
    client.connect()
    client.reader_mode()
    client.auth(user, password)

    batch_size = int(os.environ.get("TRICERAPOST_INGEST_BATCH", "500"))
    flush_seconds = float(os.environ.get("TRICERAPOST_INGEST_FLUSH", "2"))
    header_batch = []
    last_batch_flush = time.monotonic()

    def flush_headers() -> None:
        nonlocal last_batch_flush
        if not header_batch:
            return
        publish_event("header_ingested_batch", {"items": header_batch[:]})
        header_batch.clear()
        last_batch_flush = time.monotonic()

    try:
        for group in groups:
            count, first_num, last_num, _ = client.group(group)
            if group in state:
                start = max(state[group] + 1, first_num)
            else:
                start = max(last_num - lookback + 1, first_num)
            end = last_num

            if start > end:
                print(f"No new articles in {group}")
                continue

            total_range = end - start + 1
            print(f"Scanning {group}: 0/{total_range} (fetching overview)")
            if publish_event:
                publish_event("scan_progress", {"group": group, "current": 0, "total": total_range})

            overview_list = client.xover(start, end)
            total_articles = len(overview_list)
            if total_articles != total_range:
                print(f"Scanning {group}: overview returned {total_articles} articles")

            last_progress = time.monotonic()
            nzb_targets = []

            for idx, (art_number, overview) in enumerate(overview_list, start=1):
                subject, poster, date_raw, size, message_id = parse_overview(overview)
                record = {
                    "type": "header",
                    "group": group,
                    "article": art_number,
                    "subject": subject,
                    "poster": poster,
                    "date": date_raw,
                    "bytes": size,
                    "message_id": message_id,
                }
                if publish_event:
                    header_batch.append(record)
                    if len(header_batch) >= batch_size:
                        flush_headers()
                else:
                    append_record(ingest_conn, record)

                if NZB_RE.search(subject):
                    nzb_targets.append(
                        {
                            "group": group,
                            "article": art_number,
                            "subject": subject,
                            "poster": poster,
                            "date": date_raw,
                            "message_id": message_id,
                        }
                    )
                    if publish_event:
                        publish_event("nzb_seen", nzb_targets[-1])

                now = time.monotonic()
                if now - last_progress >= progress_seconds or idx == total_articles:
                    print(f"Scanning {group}: {idx}/{total_articles}")
                    if publish_event:
                        publish_event(
                            "scan_progress",
                            {"group": group, "current": idx, "total": total_articles},
                        )
                    last_progress = now
                if publish_event and (now - last_batch_flush) >= flush_seconds:
                    flush_headers()

            if nzb_targets and parse_nzb:
                for target in nzb_targets:
                    try:
                        body_target = target["message_id"] or target["article"]
                        body_lines = client.body(body_target)
                    except Exception:
                        try:
                            article_target = target["message_id"] or target["article"]
                            article_lines = client.article(article_target)
                            body_lines = strip_article_headers(article_lines)
                        except Exception:
                            fail = {
                                "type": "nzb_failed",
                                "group": target["group"],
                                "article": target["article"],
                                "subject": target["subject"],
                                "poster": target["poster"],
                                "date": target["date"],
                                "message_id": target["message_id"],
                            }
                        append_record(ingest_conn, fail)
                        continue

                    nzb_files = parse_nzb(body_lines)
                    for nzb_file in nzb_files:
                        record = {
                            "type": "nzb_file",
                            "group": (nzb_file.get("groups") or [group])[0],
                            "subject": nzb_file.get("subject", ""),
                            "poster": nzb_file.get("poster") or target["poster"],
                            "date": target["date"],
                            "bytes": int(nzb_file.get("bytes") or 0),
                            "segments": int(nzb_file.get("segments") or 0),
                            "nzb_source_subject": target["subject"],
                            "nzb_article": target["article"],
                            "nzb_message_id": target["message_id"],
                            "payload": {"segments": int(nzb_file.get("segments") or 0)},
                        }
                        append_record(ingest_conn, record)

            if publish_event:
                publish_event("state_update", {"group": group, "last_article": end})
            else:
                save_state(state_conn, group, end)
                ingest_conn.commit()
                state_conn.commit()
    finally:
        if publish_event:
            flush_headers()
        client.quit()
        if ingest_conn:
            ingest_conn.close()
        if state_conn:
            state_conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest NNTP headers into SQLite.")
    parser.add_argument("--group", help="Override NNTP_GROUP from .env")
    parser.add_argument("--groups", help="Comma-separated list of groups")
    parser.add_argument("--lookback", type=int, help="Override NNTP_LOOKBACK")
    parser.add_argument("--reset", action="store_true", help="Ignore saved state for this group")
    parser.add_argument("--no-nzb", action="store_true", help="Disable NZB body fetch/parsing")
    parser.add_argument("--progress-seconds", type=int, default=10, help="Progress update interval")
    args = parser.parse_args()

    env_group = os.environ.get("NNTP_GROUP")
    env_groups = os.environ.get("NNTP_GROUPS")
    groups = parse_groups(args.group, env_group, args.groups or env_groups)
    if not groups:
        print("NNTP_GROUP or NNTP_GROUPS not set in .env (or pass --group/--groups)")
        return 1

    ingest_groups(
        groups=groups,
        lookback=args.lookback,
        reset=args.reset,
        emit_events=False,
        parse_nzb=not args.no_nzb,
        progress_seconds=args.progress_seconds,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
