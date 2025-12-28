#!/usr/bin/env python3
import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.db import (
    get_ingest_db_readonly,
    get_releases_db,
    init_releases_db,
)
from app.release_utils import extract_filename, format_bytes, normalize_subject, parse_part


def iter_records(conn):
    rows = conn.execute(
        "SELECT type, group_name, article, subject, poster, date, bytes, message_id, payload FROM ingest ORDER BY id"
    ).fetchall()
    for row in rows:
        payload = row["payload"]
        if payload:
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = None
        yield {
            "type": row["type"],
            "group": row["group_name"],
            "article": row["article"],
            "subject": row["subject"],
            "poster": row["poster"],
            "date": row["date"],
            "bytes": row["bytes"],
            "message_id": row["message_id"],
            "payload": payload,
        }


def build_releases() -> None:
    ingest_conn = get_ingest_db_readonly()
    if ingest_conn is None:
        return
    releases_conn = get_releases_db()
    init_releases_db(releases_conn)
    releases = {}

    for record in iter_records(ingest_conn):
        rtype = record.get("type")
        if rtype == "nzb_failed":
            key = ("nzb_failed", record.get("poster", ""), record.get("group", ""))
            entry = releases.setdefault(
                key,
                {
                    "name": record.get("subject", "") or "NZB fetch failed",
                    "normalized_name": normalize_subject(record.get("subject", "")),
                    "filename_hint": extract_filename(record.get("subject", "")),
                    "poster": record.get("poster", ""),
                    "group": record.get("group", ""),
                    "first_seen": record.get("date", ""),
                    "last_seen": record.get("date", ""),
                    "bytes": 0,
                    "parts": set(),
                    "part_total": 0,
                    "subjects": set(),
                    "articles": 0,
                    "source": "nzb",
                    "nzb_source_subject": record.get("subject", ""),
                    "nzb_article": record.get("article"),
                    "nzb_message_id": record.get("message_id"),
                    "nzb_fetch_failed": True,
                },
            )
            entry["subjects"].add(record.get("subject", ""))
            continue

        if rtype == "nzb_file":
            subject = record.get("subject", "")
            poster = record.get("poster", "")
            group = record.get("group", "")
            norm = normalize_subject(subject)
            payload = record.get("payload") or {}
            key = (norm, poster, group)
            entry = releases.setdefault(
                key,
                {
                    "name": norm or subject,
                    "normalized_name": norm or subject,
                    "filename_hint": extract_filename(subject),
                    "poster": poster,
                    "group": group,
                    "first_seen": record.get("date", ""),
                    "last_seen": record.get("date", ""),
                    "bytes": 0,
                    "parts": set(),
                    "part_total": 0,
                    "subjects": set(),
                    "articles": 0,
                    "source": "nzb",
                    "nzb_source_subject": payload.get("nzb_source_subject"),
                    "nzb_article": payload.get("nzb_article"),
                    "nzb_message_id": payload.get("nzb_message_id"),
                },
            )
            entry["bytes"] += int(record.get("bytes") or 0)
            segments = 0
            if payload:
                segments = int(payload.get("segments") or 0)
            entry["articles"] += segments
            entry["subjects"].add(subject)
            if segments:
                entry["parts"].update(range(1, segments + 1))
                entry["part_total"] = max(entry["part_total"], segments)
            continue

        if rtype != "header":
            continue

        subject = record.get("subject", "")
        poster = record.get("poster", "")
        group = record.get("group", "")
        norm = normalize_subject(subject)
        part_num, part_total = parse_part(subject)

        key = (norm, poster, group)
        entry = releases.setdefault(
            key,
            {
                "name": norm or subject,
                "normalized_name": norm or subject,
                "filename_hint": None,
                "poster": poster,
                "group": group,
                "first_seen": record.get("date", ""),
                "last_seen": record.get("date", ""),
                "bytes": 0,
                "parts": set(),
                "part_total": 0,
                "subjects": set(),
                "articles": 0,
                "source": "header",
                "message_id": record.get("message_id"),
            },
        )

        entry["bytes"] += int(record.get("bytes") or 0)
        entry["articles"] += 1
        if record.get("date"):
            entry["last_seen"] = record.get("date")
            if not entry["first_seen"]:
                entry["first_seen"] = record.get("date")
        if part_num:
            entry["parts"].add(part_num)
        if part_total:
            entry["part_total"] = max(entry["part_total"], part_total)
        if subject:
            entry["subjects"].add(subject)
            if not entry["filename_hint"]:
                entry["filename_hint"] = extract_filename(subject)

    payload = []
    for info in releases.values():
        parts_received = len(info["parts"]) if info["parts"] else 0
        parts_expected = info["part_total"] or (parts_received or 0)
        payload.append(
            {
                "key": f"{info['group']}|{info['poster']}|{info['name']}",
                "name": info["name"],
                "normalized_name": info["normalized_name"],
                "filename_hint": info.get("filename_hint"),
                "poster": info["poster"],
                "group": info["group"],
                "source": info.get("source"),
                "message_id": info.get("message_id"),
                "nzb_source_subject": info.get("nzb_source_subject"),
                "nzb_article": info.get("nzb_article"),
                "nzb_message_id": info.get("nzb_message_id"),
                "nzb_fetch_failed": info.get("nzb_fetch_failed"),
                "first_seen": info["first_seen"],
                "last_seen": info["last_seen"],
                "bytes": info["bytes"],
                "size_human": format_bytes(int(info["bytes"] or 0)),
                "parts_received": parts_received,
                "parts_expected": parts_expected or None,
                "part_numbers": sorted(info["parts"]),
                "part_total": info["part_total"] or None,
                "articles": info["articles"],
                "subjects": sorted(info["subjects"]),
            }
        )

    payload.sort(key=lambda r: r.get("last_seen") or "", reverse=True)

    releases_conn.execute("DELETE FROM releases")
    for row in payload:
        releases_conn.execute(
            """
            INSERT INTO releases(
                key, name, normalized_name, filename_hint, poster, group_name, source,
                message_id, nzb_source_subject, nzb_article, nzb_message_id, nzb_fetch_failed,
                first_seen, last_seen, bytes, size_human, parts_received, parts_expected,
                part_numbers, part_total, articles, subjects
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("key"),
                row.get("name"),
                row.get("normalized_name"),
                row.get("filename_hint"),
                row.get("poster"),
                row.get("group"),
                row.get("source"),
                row.get("message_id"),
                row.get("nzb_source_subject"),
                row.get("nzb_article"),
                row.get("nzb_message_id"),
                1 if row.get("nzb_fetch_failed") else 0,
                row.get("first_seen"),
                row.get("last_seen"),
                row.get("bytes"),
                row.get("size_human"),
                row.get("parts_received"),
                row.get("parts_expected"),
                json.dumps(row.get("part_numbers")),
                row.get("part_total"),
                row.get("articles"),
                json.dumps(row.get("subjects")),
            ),
        )
    releases_conn.commit()
    releases_conn.close()
    ingest_conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate ingested headers into releases.")
    parser.parse_args()

    build_releases()
    print("Wrote releases to SQLite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
