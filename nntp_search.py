#!/usr/bin/env python3
import argparse
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from typing import Dict, Tuple

from nntp_client import NNTPClient

STATE_PATH = os.path.join("data", "state.json")
RELEASES_PATH = os.path.join("data", "releases.json")

PART_RE = re.compile(r"(?:\(|\[)?\s*(\d{1,4})\s*/\s*(\d{1,4})\s*(?:\)|\])")
PART_FILE_RE = re.compile(r"\.part\d{1,4}\.[^\s\"']+", re.IGNORECASE)
PAR2_RE = re.compile(r"\.vol\d{1,4}\+\d{1,4}\.par2\b", re.IGNORECASE)
PAR2_SINGLE_RE = re.compile(r"\.par2\b", re.IGNORECASE)
NZB_RE = re.compile(r"\.nzb\b", re.IGNORECASE)
FILENAME_RE = re.compile(r"\"([^\"]+\.(?:rar|r\d+|7z|zip|par2|nzb|mkv|mp4|avi))\"", re.IGNORECASE)
EXT_RE = re.compile(r"\b[^\s\"']+\.(?:rar|r\d+|7z|zip|par2|nzb|mkv|mp4|avi)\b", re.IGNORECASE)
YENC_RE = re.compile(r"\s+yenc\b.*$", re.IGNORECASE)
NZB_HINT_RE = re.compile(r"<nzb\\b", re.IGNORECASE)


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


def load_state() -> Dict[str, int]:
    if not os.path.exists(STATE_PATH):
        return {}
    with open(STATE_PATH, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return {k: int(v) for k, v in data.items()}


def save_state(state: Dict[str, int]) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")


def normalize_subject(subject: str) -> str:
    subject = YENC_RE.sub("", subject)
    subject = PART_RE.sub("", subject)
    subject = PART_FILE_RE.sub("", subject)
    subject = PAR2_RE.sub("", subject)
    subject = PAR2_SINGLE_RE.sub("", subject)
    subject = NZB_RE.sub("", subject)
    subject = re.sub(r"\s+", " ", subject)
    return subject.strip(" -_[]()\t ")


def extract_filename(subject: str) -> str | None:
    match = FILENAME_RE.search(subject)
    if match:
        return match.group(1)
    match = EXT_RE.search(subject)
    if match:
        return match.group(0)
    return None


def decode_yenc(lines: list[str]) -> bytes:
    data = bytearray()
    for line in lines:
        if line.startswith("=ybegin") or line.startswith("=ypart") or line.startswith("=yend"):
            continue
        i = 0
        raw = line.encode("latin-1", errors="ignore")
        while i < len(raw):
            ch = raw[i]
            if ch == 61:  # '='
                i += 1
                if i >= len(raw):
                    break
                ch = (raw[i] - 64) & 0xFF
            data.append((ch - 42) & 0xFF)
            i += 1
    return bytes(data)


def parse_nzb(lines: list[str]) -> list[dict]:
    text = "\n".join(lines)
    if not NZB_HINT_RE.search(text):
        if any(line.startswith("=ybegin") for line in lines):
            decoded = decode_yenc(lines).decode("utf-8", errors="ignore")
            if NZB_HINT_RE.search(decoded):
                text = decoded
        if not NZB_HINT_RE.search(text):
            return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []

    files = []
    for file_elem in root.findall(".//{*}file"):
        subject = file_elem.attrib.get("subject", "")
        poster = file_elem.attrib.get("poster", "")
        groups = [g.text.strip() for g in file_elem.findall(".//{*}groups/{*}group") if g.text]
        segments = file_elem.findall(".//{*}segments/{*}segment")
        total_bytes = 0
        for seg in segments:
            try:
                total_bytes += int(seg.attrib.get("bytes", "0"))
            except ValueError:
                pass
        files.append(
            {
                "subject": subject,
                "poster": poster,
                "groups": groups,
                "segments": len(segments),
                "bytes": total_bytes,
            }
        )
    return files


def strip_article_headers(lines: list[str]) -> list[str]:
    if not lines:
        return []
    for idx, line in enumerate(lines):
        if line.strip() == "":
            return lines[idx + 1 :]
    return lines


def parse_overview(overview) -> Tuple[str, str, str, int, str]:
    """Return subject, from, date, bytes, message-id from an overview line."""
    if isinstance(overview, dict):
        subject = overview.get("subject", "")
        poster = overview.get("from", "")
        date = overview.get("date", "")
        size_raw = overview.get("bytes", "0")
        message_id = overview.get("message-id", "")
    else:
        # Legacy tuple ordering: subject, from, date, message-id, references, bytes, lines, xref
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


def parse_part(subject: str) -> Tuple[int, int]:
    match = PART_RE.search(subject)
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"


def load_releases() -> Dict[str, Dict[str, str]]:
    if not os.path.exists(RELEASES_PATH):
        return {}
    with open(RELEASES_PATH, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return {entry["key"]: entry for entry in data if "key" in entry}


def save_releases(releases: Dict[str, Dict[str, str]]) -> None:
    os.makedirs(os.path.dirname(RELEASES_PATH), exist_ok=True)
    payload = sorted(releases.values(), key=lambda r: r.get("last_seen") or "", reverse=True)
    with open(RELEASES_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def parse_groups(args_group: str | None, env_group: str | None, env_groups: str | None) -> list[str]:
    if args_group:
        return [args_group]
    if env_groups:
        return [g.strip() for g in env_groups.split(",") if g.strip()]
    if env_group:
        return [env_group]
    return []


def main() -> int:
    load_env()

    parser = argparse.ArgumentParser(description="Fetch NNTP headers and print grouped releases.")
    parser.add_argument("--group", help="Override NNTP_GROUP from .env")
    parser.add_argument("--groups", help="Comma-separated list of groups")
    parser.add_argument("--lookback", type=int, help="Override NNTP_LOOKBACK")
    parser.add_argument("--output", help="Write releases to JSON file (default: data/releases.json)")
    parser.add_argument("--reset", action="store_true", help="Ignore saved state for this group")
    parser.add_argument("--no-nzb", action="store_true", help="Disable NZB body fetch/parsing")
    parser.add_argument("--progress-interval", type=int, default=500, help="Progress update interval")
    args = parser.parse_args()

    host = os.environ.get("NNTP_HOST")
    if not host:
        print("NNTP_HOST not set in .env")
        return 1

    port = int(os.environ.get("NNTP_PORT", "119"))
    use_ssl = get_env_bool("NNTP_SSL")
    user = os.environ.get("NNTP_USER")
    password = os.environ.get("NNTP_PASS")
    env_group = os.environ.get("NNTP_GROUP")
    env_groups = os.environ.get("NNTP_GROUPS")
    groups = parse_groups(args.group, env_group, args.groups or env_groups)
    if not groups:
        print("NNTP_GROUP or NNTP_GROUPS not set in .env (or pass --group/--groups)")
        return 1

    lookback = args.lookback or int(os.environ.get("NNTP_LOOKBACK", "2000"))
    progress_interval = max(int(args.progress_interval or 500), 1)
    progress_seconds = 10.0

    state = load_state()
    for group in groups:
        if args.reset and group in state:
            state.pop(group)

    client = NNTPClient(host, port, use_ssl=use_ssl)
    client.connect()
    client.reader_mode()
    client.auth(user, password)
    try:
        if args.output:
            save_path = args.output
            if os.path.exists(save_path):
                with open(save_path, "r", encoding="utf-8") as handle:
                    existing = json.load(handle)
                releases_output = {entry["key"]: entry for entry in existing if "key" in entry}
            else:
                releases_output = {}
        else:
            releases_output = load_releases() if os.path.exists(RELEASES_PATH) else {}

        fetch_nzb = not args.no_nzb

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
            print(f"Scanning {group}: 0/{total_range} (fetching overview)", flush=True)
            overview_list = client.xover(start, end)
            releases = {}
            nzb_articles = []
            nzb_entry_keys = {}
            total_articles = len(overview_list)
            if total_articles != total_range:
                print(f"Scanning {group}: overview returned {total_articles} articles", flush=True)

            last_progress = time.monotonic()
            for idx, (art_number, overview) in enumerate(overview_list, start=1):
                subject, poster, date_raw, size, message_id = parse_overview(overview)
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
                        "message_id": message_id,
                        "first_seen": date_raw,
                        "last_seen": date_raw,
                        "bytes": 0,
                        "parts": set(),
                        "part_total": 0,
                        "subjects": set(),
                        "articles": 0,
                        "range": {"start": start, "end": end},
                    },
                )

                entry["bytes"] += size
                entry["articles"] += 1
                if date_raw:
                    entry["last_seen"] = date_raw
                    if not entry["first_seen"]:
                        entry["first_seen"] = date_raw
                if part_num:
                    entry["parts"].add(part_num)
                if part_total:
                    entry["part_total"] = max(entry["part_total"], part_total)
                if subject:
                    entry["subjects"].add(subject)
                    if not entry["filename_hint"]:
                        entry["filename_hint"] = extract_filename(subject)
                if message_id and not entry.get("message_id"):
                    entry["message_id"] = message_id
                if fetch_nzb and NZB_RE.search(subject):
                    entry["source"] = "nzb"
                    entry["nzb_article"] = art_number
                    entry["nzb_message_id"] = message_id
                    entry["nzb_source_subject"] = subject
                    nzb_articles.append((art_number, subject, poster, date_raw, message_id))
                    nzb_entry_keys[art_number] = key

                now = time.monotonic()
                if now - last_progress >= progress_seconds or idx == total_articles:
                    print(f"Scanning {group}: {idx}/{total_articles}", flush=True)
                    last_progress = now

            if fetch_nzb and nzb_articles:
                for art_number, subject, poster, date_raw, message_id in nzb_articles:
                    try:
                        body_target = message_id or art_number
                        body_lines = client.body(body_target)
                    except Exception:
                        body_lines = None

                    if body_lines is None:
                        try:
                            article_target = message_id or art_number
                            article_lines = client.article(article_target)
                            body_lines = strip_article_headers(article_lines)
                        except Exception:
                            body_lines = None

                    if body_lines is None:
                        entry_key = nzb_entry_keys.get(art_number)
                        if entry_key and entry_key in releases:
                            releases[entry_key]["nzb_fetch_failed"] = True
                        continue

                    nzb_files = parse_nzb(body_lines)
                    for nzb_file in nzb_files:
                        nzb_subject = nzb_file.get("subject", "")
                        nzb_norm = normalize_subject(nzb_subject)
                        nzb_groups = nzb_file.get("groups") or []
                        nzb_group = nzb_groups[0] if nzb_groups else group
                        nzb_poster = nzb_file.get("poster") or poster
                        nzb_key = (nzb_norm, nzb_poster, nzb_group)
                        nzb_entry = releases.setdefault(
                            nzb_key,
                            {
                                "name": nzb_norm or nzb_subject,
                                "normalized_name": nzb_norm or nzb_subject,
                                "filename_hint": extract_filename(nzb_subject),
                                "poster": nzb_poster,
                                "group": nzb_group,
                                "message_id": None,
                                "first_seen": date_raw,
                                "last_seen": date_raw,
                                "bytes": 0,
                                "parts": set(),
                                "part_total": 0,
                                "subjects": set(),
                                "articles": 0,
                                "range": {"start": start, "end": end},
                                "source": "nzb",
                                "nzb_source_subject": subject,
                                "nzb_article": art_number,
                                "nzb_message_id": message_id,
                            },
                        )
                        nzb_entry["bytes"] += int(nzb_file.get("bytes") or 0)
                        nzb_entry["articles"] += int(nzb_file.get("segments") or 0)
                        nzb_entry["subjects"].add(nzb_subject)
                        segments = int(nzb_file.get("segments") or 0)
                        if segments:
                            nzb_entry["parts"].update(range(1, segments + 1))
                            nzb_entry["part_total"] = max(nzb_entry["part_total"], segments)

            if not releases:
                print(f"No releases found in {group} for articles {start}-{end}")
            else:
                print(f"Found {len(releases)} releases in {group} ({start}-{end})")
                for info in sorted(releases.values(), key=lambda r: r["last_seen"], reverse=True):
                    parts_received = len(info["parts"]) if info["parts"] else 0
                    parts_expected = info["part_total"] or (parts_received or "?")
                    size = format_bytes(info["bytes"])
                    print("-")
                    print(f"  Name: {info['name']}")
                    print(f"  Poster: {info['poster']}")
                    print(f"  Group: {info['group']}")
                    print(f"  Parts: {parts_received}/{parts_expected}")
                    print(f"  Size: {size}")
                    print(f"  First Seen: {info['first_seen']}")
                    print(f"  Last Seen: {info['last_seen']}")

            for info in releases.values():
                parts_received = len(info["parts"]) if info["parts"] else 0
                parts_expected = info["part_total"] or (parts_received or 0)
                key = f"{info['group']}|{info['poster']}|{info['name']}"
                releases_output[key] = {
                    "key": key,
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
                    "size_human": format_bytes(info["bytes"]),
                    "parts_received": parts_received,
                    "parts_expected": parts_expected or None,
                    "part_numbers": sorted(info["parts"]),
                    "part_total": info["part_total"] or None,
                    "articles": info["articles"],
                    "subjects": sorted(info["subjects"]),
                    "range": info["range"],
                }

            state[group] = end
            save_state(state)

        if args.output:
            os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
            payload = sorted(releases_output.values(), key=lambda r: r.get("last_seen") or "", reverse=True)
            with open(save_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
        else:
            if releases_output:
                save_releases(releases_output)
    finally:
        client.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
