#!/usr/bin/env python3
import argparse
import os
import sys
import time
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from nntp_client import NNTPClient
from release_filter import main as filter_main
from services.aggregate import build_releases
from services.ingest import (
    append_record,
    load_env,
    load_state,
    parse_groups,
    parse_overview,
    save_state,
)
from services.nzb_store import store_nzb_invalid, store_nzb_payload, verify_message_ids
from services.nzb_utils import build_nzb_payload, parse_nzb_segments
from services.release_utils import NZB_RE, parse_nzb, strip_article_headers
from services.scheduler import load_groups as load_default_groups
from services.settings import get_bool_setting, get_int_setting, get_setting
from services.db import get_ingest_db, get_state_db, init_ingest_db, init_state_db


def _fetch_nzb_body(client: NNTPClient, group: str, target: str) -> Optional[list[str]]:
    try:
        client.group(group)
        return client.body(target)
    except Exception:
        try:
            client.group(group)
            article_lines = client.article(target)
            return strip_article_headers(article_lines)
        except Exception:
            return None


def _ingest_nzb_target(
    *,
    client: NNTPClient,
    ingest_conn,
    group: str,
    article: int,
    subject: str,
    poster: str,
    date: str,
    message_id: str,
    verify_nzb: bool,
) -> None:
    target = message_id or article
    body_lines = _fetch_nzb_body(client, group, str(target))
    if body_lines is None:
        append_record(
            ingest_conn,
            {
                "type": "nzb_failed",
                "group": group,
                "article": article,
                "subject": subject,
                "poster": poster,
                "date": date,
                "message_id": message_id,
            },
        )
        return

    nzb_files = parse_nzb(body_lines)
    raw_payload = build_nzb_payload(body_lines)
    if raw_payload:
        segments = parse_nzb_segments(raw_payload)
        message_ids = [seg.get("message_id", "") for seg in segments]
        ok = True
        reason = None
        if verify_nzb:
            ok, reason = verify_message_ids(message_ids)
        if ok:
            store_nzb_payload(
                name=subject or "nzb",
                payload=raw_payload,
                source="found",
                group_name=group,
                poster=poster,
                nzb_source_subject=subject,
                nzb_article=article,
                nzb_message_id=message_id,
            )
        else:
            store_nzb_invalid(
                name=subject or "nzb",
                source="found",
                reason=reason or "verification failed",
                payload=raw_payload,
            )

    for nzb_file in nzb_files:
        record = {
            "type": "nzb_file",
            "group": (nzb_file.get("groups") or [group])[0],
            "article": article,
            "subject": nzb_file.get("subject", ""),
            "poster": nzb_file.get("poster") or poster,
            "date": date,
            "bytes": int(nzb_file.get("bytes") or 0),
            "message_id": message_id,
            "payload": {
                "segments": int(nzb_file.get("segments") or 0),
                "nzb_source_subject": subject,
                "nzb_article": article,
                "nzb_message_id": message_id,
            },
        }
        append_record(ingest_conn, record)


def run_pipeline_once(
    *,
    groups: list[str],
    lookback: Optional[int] = None,
    reset: bool = False,
    parse_nzb_bodies: bool = True,
    verify_nzb: bool = True,
    progress_seconds: int = 10,
) -> int:
    load_env()

    host = get_setting("NNTP_HOST")
    if not host:
        print("NNTP_HOST not set in settings or .env")
        return 1

    port = get_int_setting("NNTP_PORT", 119)
    use_ssl = get_bool_setting("NNTP_SSL")
    user = get_setting("NNTP_USER")
    password = get_setting("NNTP_PASS")
    lookback = lookback or get_int_setting("NNTP_LOOKBACK", 2000)

    state_conn = get_state_db()
    init_state_db(state_conn)
    state = load_state(state_conn)

    ingest_conn = get_ingest_db()
    init_ingest_db(ingest_conn)

    client = NNTPClient(host, port, use_ssl=use_ssl)
    client.connect()
    client.reader_mode()
    client.auth(user, password)

    try:
        for group in groups:
            if reset:
                state_conn.execute("DELETE FROM state WHERE group_name = ?", (group,))
                state.pop(group, None)

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

            overview_list = client.xover(start, end)
            total_articles = len(overview_list)
            if total_articles != total_range:
                print(f"Scanning {group}: overview returned {total_articles} articles")

            last_progress = time.monotonic()

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
                append_record(ingest_conn, record)

                if parse_nzb_bodies and NZB_RE.search(subject or ""):
                    _ingest_nzb_target(
                        client=client,
                        ingest_conn=ingest_conn,
                        group=group,
                        article=art_number,
                        subject=subject,
                        poster=poster,
                        date=date_raw,
                        message_id=message_id,
                        verify_nzb=verify_nzb,
                    )

                now = time.monotonic()
                if now - last_progress >= progress_seconds or idx == total_articles:
                    print(f"Scanning {group}: {idx}/{total_articles}")
                    last_progress = now

            save_state(state_conn, group, end)
            ingest_conn.commit()
            state_conn.commit()
    finally:
        try:
            client.quit()
        except Exception:
            pass
        ingest_conn.close()
        state_conn.close()

    build_releases()
    filter_main([])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run single-process ingest + aggregate + filter pipeline.")
    parser.add_argument("--group", help="Override NNTP_GROUP from settings/.env")
    parser.add_argument("--groups", help="Comma-separated list of groups")
    parser.add_argument("--lookback", type=int, help="Override NNTP_LOOKBACK")
    parser.add_argument("--reset", action="store_true", help="Ignore saved state for this group")
    parser.add_argument(
        "--interval",
        type=int,
        default=get_int_setting("TRICERAPOST_SCHEDULER_INTERVAL", 0),
        help="Repeat scans every N seconds (default: 0, run once)",
    )
    parser.add_argument("--no-nzb", action="store_true", help="Disable NZB body fetch/parsing")
    parser.add_argument("--no-verify", action="store_true", help="Skip NNTP verification for found NZBs")
    parser.add_argument("--progress-seconds", type=int, default=10, help="Progress update interval")
    args = parser.parse_args()

    env_group = get_setting("NNTP_GROUP")
    env_groups = get_setting("NNTP_GROUPS")
    groups = parse_groups(args.group, env_group, args.groups or env_groups)
    if not groups:
        groups = load_default_groups()

    if not groups:
        print("No groups selected")
        return 1

    interval = max(0, int(args.interval or 0))
    while True:
        code = run_pipeline_once(
            groups=groups,
            lookback=args.lookback,
            reset=args.reset,
            parse_nzb_bodies=not args.no_nzb,
            verify_nzb=not args.no_verify,
            progress_seconds=args.progress_seconds,
        )
        if code != 0 or interval <= 0:
            return code
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
