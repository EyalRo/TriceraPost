#!/usr/bin/env python3
import argparse
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from nntp_client import NNTPClient
from services.event_bus import get_last_event_id, iter_events, publish_event, set_last_event_id
from services.ingest import load_env
from services.settings import get_bool_setting, get_int_setting, get_setting
from services.release_utils import parse_nzb, strip_article_headers
from services.nzb_store import store_nzb_invalid, store_nzb_payload, verify_message_ids
from services.nzb_utils import build_nzb_payload, parse_nzb_segments

SERVICE_NAME = "nzb_expander"


def wait_for_settings(poll_seconds: float) -> tuple[str, int, bool, str, str]:
    while True:
        load_env()
        host = get_setting("NNTP_HOST")
        if host:
            port = get_int_setting("NNTP_PORT", 119)
            use_ssl = get_bool_setting("NNTP_SSL")
            user = get_setting("NNTP_USER")
            password = get_setting("NNTP_PASS")
            return host, port, use_ssl, user, password
        print("NNTP_HOST not set in settings or .env; waiting for settings...")
        time.sleep(poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Worker to expand NZB files.")
    parser.add_argument("--poll", type=float, default=1.0)
    args = parser.parse_args()

    host, port, use_ssl, user, password = wait_for_settings(args.poll)

    client = NNTPClient(host, port, use_ssl=use_ssl)
    client.connect()
    client.reader_mode()
    client.auth(user, password)

    last_id = get_last_event_id(SERVICE_NAME)
    print(f"NZB expander starting at event {last_id}")

    try:
        while True:
            processed = False
            for event in iter_events(last_id):
                processed = True
                last_id = event["id"]
                if event["type"] != "nzb_seen":
                    set_last_event_id(SERVICE_NAME, last_id)
                    continue

                payload = event["payload"]
                group = payload.get("group")
                article = payload.get("article")
                message_id = payload.get("message_id")
                subject = payload.get("subject")
                poster = payload.get("poster")
                date = payload.get("date")

                try:
                    client.group(group)
                    target = message_id or article
                    body_lines = client.body(target)
                except Exception:
                    try:
                        client.group(group)
                        target = message_id or article
                        article_lines = client.article(target)
                        body_lines = strip_article_headers(article_lines)
                    except Exception:
                        publish_event(
                            "nzb_failed",
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
                        set_last_event_id(SERVICE_NAME, last_id)
                        continue

                nzb_files = parse_nzb(body_lines)
                raw_payload = build_nzb_payload(body_lines)
                if raw_payload:
                    segments = parse_nzb_segments(raw_payload)
                    message_ids = [seg.get("message_id", "") for seg in segments]
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
                    publish_event("nzb_file", record)

                publish_event("nzb_parsed", {"group": group, "article": article})
                set_last_event_id(SERVICE_NAME, last_id)

            if not processed:
                time.sleep(args.poll)
    finally:
        client.quit()


if __name__ == "__main__":
    raise SystemExit(main())
