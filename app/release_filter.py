#!/usr/bin/env python3
import argparse
import json
import re
from typing import Dict, List, Optional

from app.db import (
    get_complete_db,
    get_ingest_db_readonly,
    get_releases_db_readonly,
    init_complete_db,
)
from app.nzb_store import find_nzb_by_release, store_nzb_invalid, store_nzb_payload, verify_message_ids
from app.nzb_utils import build_nzb_xml
from app.release_utils import normalize_subject, parse_part

QUALITY_RE = re.compile(r"\b(2160p|1080p|720p|576p|480p)\b", re.IGNORECASE)
SOURCE_RE = re.compile(r"\b(bluray|bdrip|brrip|web[-_. ]?dl|webrip|hdtv|dvd|dvdrip)\b", re.IGNORECASE)
CODEC_RE = re.compile(r"\b(x264|x265|h\.?264|h\.?265|hevc)\b", re.IGNORECASE)
AUDIO_RE = re.compile(r"\b(aac|ac3|eac3|dts|flac|mp3)\b", re.IGNORECASE)
SUB_RE = re.compile(r"\b(subs?|subbed|subpack|subtitles?|multi[-_. ]?sub)\b", re.IGNORECASE)
LANG_RE = re.compile(
    r"\b(english|eng|french|fre|fr|spanish|spa|es|german|ger|de|italian|ita|pt|por|portuguese)\b",
    re.IGNORECASE,
)
TV_TAG_RE = re.compile(r"\bS\d{1,2}E\d{1,3}\b", re.IGNORECASE)
SEASON_RE = re.compile(r"\bS(?:eason)?\s*\d{1,2}\b", re.IGNORECASE)
PART_RE = re.compile(r"(?:\(|\[)?\s*(\d{1,4})\s*/\s*(\d{1,4})\s*(?:\)|\])")
PART_FILE_RE = re.compile(r"\.part\d{1,4}\.[^\s\"']+", re.IGNORECASE)
PAR2_RE = re.compile(r"\.vol\d{1,4}\+\d{1,4}\.par2\b", re.IGNORECASE)
PAR2_SINGLE_RE = re.compile(r"\.par2\b", re.IGNORECASE)
NZB_RE = re.compile(r"\.nzb\b", re.IGNORECASE)
FILENAME_QUOTED_RE = re.compile(
    r"\"([^\"]+\.(?:mkv|mp4|avi|mov|rar|r\d+|7z|zip|par2|nzb|png|jpg|jpeg|gif|bmp))\"",
    re.IGNORECASE,
)
FILENAME_TOKEN_RE = re.compile(
    r"\b[^\s\"']+\.(?:mkv|mp4|avi|mov|rar|r\d+|7z|zip|par2|nzb|png|jpg|jpeg|gif|bmp)\b",
    re.IGNORECASE,
)

def load_releases() -> List[Dict[str, object]]:
    conn = get_releases_db_readonly()
    if conn is None:
        return []
    rows = conn.execute(
        """
        SELECT
            key, name, normalized_name, filename_hint, poster, group_name, source,
            first_seen, last_seen, bytes, size_human, parts_received, parts_expected,
            part_numbers, part_total, articles, subjects, nzb_fetch_failed, nzb_source_subject,
            nzb_article, nzb_message_id
        FROM releases
        """
    ).fetchall()
    conn.close()

    payload = []
    for row in rows:
        part_numbers = json.loads(row["part_numbers"]) if row["part_numbers"] else []
        subjects = json.loads(row["subjects"]) if row["subjects"] else []
        payload.append(
            {
                "key": row["key"],
                "name": row["name"],
                "normalized_name": row["normalized_name"],
                "filename_hint": row["filename_hint"],
                "poster": row["poster"],
                "group": row["group_name"],
                "source": row["source"],
                "first_seen": row["first_seen"],
                "last_seen": row["last_seen"],
                "bytes": row["bytes"],
                "size_human": row["size_human"],
                "parts_received": row["parts_received"],
                "parts_expected": row["parts_expected"],
                "part_numbers": part_numbers,
                "part_total": row["part_total"],
                "articles": row["articles"],
                "subjects": subjects,
                "nzb_fetch_failed": bool(row["nzb_fetch_failed"]),
                "nzb_source_subject": row["nzb_source_subject"],
                "nzb_article": row["nzb_article"],
                "nzb_message_id": row["nzb_message_id"],
            }
        )
    return payload


def parse_metadata(name: str) -> Dict[str, object]:
    tokens = re.split(r"[\s._-]+", name)

    def find_token(regex: re.Pattern) -> Optional[str]:
        match = regex.search(name)
        return match.group(1) if match else None

    quality = find_token(QUALITY_RE)
    source = find_token(SOURCE_RE)
    codec = find_token(CODEC_RE)
    audio = find_token(AUDIO_RE)

    languages = sorted({t.lower() for t in tokens if LANG_RE.fullmatch(t.lower())})
    subtitles = bool(SUB_RE.search(name))

    release_type = "tv" if TV_TAG_RE.search(name) or SEASON_RE.search(name) else "unknown"

    return {
        "type": release_type,
        "quality": quality.lower() if quality else None,
        "source": source.lower() if source else None,
        "codec": codec.lower() if codec else None,
        "audio": audio.lower() if audio else None,
        "languages": languages,
        "subtitles": subtitles,
    }


def extract_parts_from_subjects(subjects: List[str]) -> tuple[set[int], int]:
    parts = set()
    max_total = 0
    for subject in subjects:
        match = PART_RE.search(subject)
        if not match:
            continue
        part_num = int(match.group(1))
        part_total = int(match.group(2))
        parts.add(part_num)
        if part_total > max_total:
            max_total = part_total
    return parts, max_total


def is_complete(parts: set[int], expected: int) -> bool:
    return expected > 0 and len(parts) == expected


def normalize_name(value: str) -> str:
    if not value:
        return ""
    cleaned = PART_RE.sub("", value)
    cleaned = PART_FILE_RE.sub("", cleaned)
    cleaned = PAR2_RE.sub("", cleaned)
    cleaned = PAR2_SINGLE_RE.sub("", cleaned)
    cleaned = NZB_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" -_[]()")


def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"


def normalize_filename(value: str) -> str:
    name = value.strip().strip("\"'")
    name = re.sub(r"\.part\d{1,4}(?=\.)", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\.vol\d{1,4}\+\d{1,4}\.par2$", ".par2", name, flags=re.IGNORECASE)
    return name


def filename_candidates(subjects: list[str]) -> list[str]:
    candidates = []
    for subject in subjects:
        match = FILENAME_QUOTED_RE.search(subject)
        if match:
            candidates.append(match.group(1))
            continue
        match = FILENAME_TOKEN_RE.search(subject)
        if match:
            candidates.append(match.group(0))
    return [normalize_filename(c) for c in candidates]


def pick_filename(subjects: list[str]) -> Optional[str]:
    candidates = filename_candidates(subjects)
    if not candidates:
        return None

    priority = [".mkv", ".mp4", ".avi", ".mov", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".rar", ".7z", ".zip", ".par2", ".nzb"]
    for ext in priority:
        for name in candidates:
            if name.lower().endswith(ext):
                return name
    return candidates[0]


def build_segments_for_release(entry: Dict[str, object]) -> list[dict]:
    groups = entry.get("groups") or []
    poster = entry.get("poster") or ""
    normalized = normalize_subject(str(entry.get("normalized_name") or entry.get("name") or ""))
    total = int(entry.get("parts_expected") or 0)
    if not groups or not poster or not normalized or total <= 0:
        return []
    conn = get_ingest_db_readonly()
    if conn is None:
        return []
    placeholders = ",".join(["?"] * len(groups))
    rows = conn.execute(
        f"""
        SELECT subject, message_id, bytes
        FROM ingest
        WHERE type = 'header' AND poster = ? AND group_name IN ({placeholders})
        """,
        (poster, *groups),
    ).fetchall()
    conn.close()

    segments = {}
    for row in rows:
        subject = row["subject"] or ""
        if normalize_subject(subject) != normalized:
            continue
        part_num, _ = parse_part(subject)
        if part_num <= 0:
            continue
        message_id = row["message_id"]
        if not message_id:
            continue
        if part_num in segments:
            continue
        segments[part_num] = {
            "number": part_num,
            "bytes": int(row["bytes"] or 0),
            "message_id": message_id,
        }
        if len(segments) >= total:
            break
    if len(segments) != total:
        return []
    return [segments[i] for i in sorted(segments)]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Filter complete releases and extract metadata.")
    args = parser.parse_args(argv)

    releases = load_releases()
    merged: Dict[str, Dict[str, object]] = {}

    for entry in releases:
        name = str(entry.get("name") or "")
        filename_hint = str(entry.get("filename_hint") or "")
        normalized = str(entry.get("normalized_name") or normalize_name(name))
        poster = str(entry.get("poster") or "")
        key = f"{normalized}|{poster}"

        parts = set(entry.get("part_numbers") or [])
        part_total = entry.get("part_total") or entry.get("parts_expected") or 0

        if not parts:
            subjects = entry.get("subjects") or []
            if isinstance(subjects, list):
                extracted, extracted_total = extract_parts_from_subjects(subjects)
                parts = extracted
                if extracted_total > part_total:
                    part_total = extracted_total
        subjects = entry.get("subjects") or []
        if not isinstance(subjects, list):
            subjects = []
        guessed_filename = pick_filename(subjects)

        bucket = merged.setdefault(
            key,
            {
                "name": filename_hint or guessed_filename or name,
                "normalized_name": normalized,
                "poster": poster,
                "groups": set(),
                "bytes": 0,
                "size_human": None,
                "first_seen": entry.get("first_seen"),
                "last_seen": entry.get("last_seen"),
                "parts": set(),
                "parts_expected": 0,
                "filename_guess": guessed_filename,
                "nzb_fetch_failed": False,
                "nzb_source_subject": None,
                "nzb_article": None,
                "nzb_message_id": None,
            },
        )

        bucket["groups"].add(entry.get("group"))
        bucket["bytes"] = int(bucket["bytes"]) + int(entry.get("bytes") or 0)
        bucket["size_human"] = format_bytes(int(bucket["bytes"]))
        bucket["parts"].update(parts)
        bucket["parts_expected"] = max(int(bucket["parts_expected"]), int(part_total or 0))

        first_seen = entry.get("first_seen")
        last_seen = entry.get("last_seen")
        if first_seen and (not bucket["first_seen"] or first_seen < bucket["first_seen"]):
            bucket["first_seen"] = first_seen
        if last_seen and (not bucket["last_seen"] or last_seen > bucket["last_seen"]):
            bucket["last_seen"] = last_seen
        if entry.get("nzb_fetch_failed"):
            bucket["nzb_fetch_failed"] = True
        if entry.get("nzb_source_subject") and not bucket.get("nzb_source_subject"):
            bucket["nzb_source_subject"] = entry.get("nzb_source_subject")
        if entry.get("nzb_article") and not bucket.get("nzb_article"):
            bucket["nzb_article"] = entry.get("nzb_article")
        if entry.get("nzb_message_id") and not bucket.get("nzb_message_id"):
            bucket["nzb_message_id"] = entry.get("nzb_message_id")

    output = []
    for entry in merged.values():
        name_value = str(entry.get("name") or "")
        filename_value = str(entry.get("filename_guess") or "")
        if name_value.lower().endswith(".nzb") or filename_value.lower().endswith(".nzb"):
            continue
        if not is_complete(entry["parts"], int(entry["parts_expected"])):
            continue
        meta = parse_metadata(str(entry["name"]))
        key_value = f"{entry.get('name')}|{entry.get('poster')}"
        output.append(
            {
                "name": entry["name"],
                "normalized_name": entry["normalized_name"],
                "filename_guess": entry.get("filename_guess"),
                "nzb_fetch_failed": entry.get("nzb_fetch_failed"),
                "nzb_source_subject": entry.get("nzb_source_subject"),
                "nzb_article": entry.get("nzb_article"),
                "nzb_message_id": entry.get("nzb_message_id"),
                "groups": sorted(g for g in entry["groups"] if g),
                "poster": entry["poster"],
                "bytes": entry["bytes"],
                "size_human": entry["size_human"],
                "first_seen": entry["first_seen"],
                "last_seen": entry["last_seen"],
                "parts_expected": entry["parts_expected"],
                "parts_received": len(entry["parts"]),
                **meta,
            }
        )

    output.sort(key=lambda r: r.get("last_seen") or "", reverse=True)

    unique = {}
    for item in output:
        key = f"{item.get('name')}|{item.get('poster')}"
        unique[key] = item
    output = list(unique.values())
    output.sort(key=lambda r: r.get("last_seen") or "", reverse=True)

    conn = get_complete_db()
    init_complete_db(conn)
    conn.execute("DELETE FROM releases_complete")
    for item in output:
        conn.execute(
            """
            INSERT INTO releases_complete(
                key, name, normalized_name, filename_guess, nzb_fetch_failed, nzb_source_subject,
                nzb_article, nzb_message_id, download_failed, groups, poster, bytes, size_human,
                first_seen, last_seen, parts_expected, parts_received, type,
                quality, source, codec, audio, languages, subtitles
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{item.get('name')}|{item.get('poster')}",
                item.get("name"),
                item.get("normalized_name"),
                item.get("filename_guess"),
                1 if item.get("nzb_fetch_failed") else 0,
                item.get("nzb_source_subject"),
                item.get("nzb_article"),
                item.get("nzb_message_id"),
                0,
                json.dumps(item.get("groups")),
                item.get("poster"),
                item.get("bytes"),
                item.get("size_human"),
                item.get("first_seen"),
                item.get("last_seen"),
                item.get("parts_expected"),
                item.get("parts_received"),
                item.get("type"),
                item.get("quality"),
                item.get("source"),
                item.get("codec"),
                item.get("audio"),
                json.dumps(item.get("languages")),
                1 if item.get("subtitles") else 0,
            ),
        )
    conn.commit()
    conn.close()

    generated = 0
    for item in output:
        release_key = f"{item.get('name')}|{item.get('poster')}"
        if find_nzb_by_release(release_key):
            continue
        segments = build_segments_for_release(item)
        if not segments:
            continue
        message_ids = [seg.get("message_id", "") for seg in segments]
        ok, reason = verify_message_ids(message_ids)
        if not ok:
            store_nzb_invalid(
                name=item.get("name") or "release",
                source="generated",
                reason=reason or "verification failed",
                release_key=release_key,
            )
            continue
        payload = build_nzb_xml(
            name=item.get("name") or "release",
            poster=item.get("poster"),
            groups=item.get("groups") or [],
            segments=segments,
        )
        store_nzb_payload(
            name=item.get("name") or "release",
            payload=payload,
            source="generated",
            group_name=(item.get("groups") or [None])[0],
            poster=item.get("poster"),
            release_key=release_key,
        )
        generated += 1

    print(f"Wrote {len(output)} complete releases to SQLite")
    if generated:
        print(f"Generated {generated} NZB files from releases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
