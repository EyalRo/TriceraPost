#!/usr/bin/env python3.13
import re
import xml.etree.ElementTree as ET

PART_RE = re.compile(r"(?:\(|\[)?\s*(\d{1,4})\s*/\s*(\d{1,4})\s*(?:\)|\])")
PART_FILE_RE = re.compile(r"\.part\d{1,4}\.[^\s\"']+", re.IGNORECASE)
PAR2_RE = re.compile(r"\.vol\d{1,4}\+\d{1,4}\.par2\b", re.IGNORECASE)
PAR2_SINGLE_RE = re.compile(r"\.par2\b", re.IGNORECASE)
NZB_RE = re.compile(r"\.nzb\b", re.IGNORECASE)
FILENAME_RE = re.compile(r"\"([^\"]+\.(?:rar|r\d+|7z|zip|par2|nzb|mkv|mp4|avi))\"", re.IGNORECASE)
EXT_RE = re.compile(r"\b[^\s\"']+\.(?:rar|r\d+|7z|zip|par2|nzb|mkv|mp4|avi)\b", re.IGNORECASE)
YENC_RE = re.compile(r"\s+yenc\b.*$", re.IGNORECASE)
NZB_HINT_RE = re.compile(r"<nzb\b", re.IGNORECASE)


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


def build_tags(name: str, filename: str | None = None) -> list[str]:
    text = " ".join(part for part in (name, filename or "") if part).lower()
    tags: set[str] = set()

    for resolution in ("2160p", "1080p", "720p", "576p", "480p"):
        if re.search(rf"\b{resolution}\b", text):
            tags.add(f"resolution:{resolution}")

    if re.search(r"\bhdr10\+|\bhdr10plus\b", text):
        tags.add("hdr:hdr10+")
    if re.search(r"\bhdr10\b", text):
        tags.add("hdr:hdr10")
    if re.search(r"\bdolby[ .-]?vision\b|\bdv\b", text):
        tags.add("hdr:dv")
    if re.search(r"\bhlg\b", text):
        tags.add("hdr:hlg")
    if re.search(r"\bsdr\b", text):
        tags.add("hdr:sdr")

    if re.search(r"\b(x265|h265|hevc)\b", text):
        tags.add("format:hevc")
    if re.search(r"\b(x264|h264|avc)\b", text):
        tags.add("format:h264")
    if re.search(r"\bav1\b", text):
        tags.add("format:av1")
    if re.search(r"\bvp9\b", text):
        tags.add("format:vp9")

    if re.search(r"\bweb[-. ]?dl\b", text):
        tags.add("source:web-dl")
    if re.search(r"\bwebrip\b", text):
        tags.add("source:webrip")
    if re.search(r"\bbluray\b|\bblu[-. ]?ray\b", text):
        tags.add("source:bluray")
    if re.search(r"\bhdtv\b", text):
        tags.add("source:hdtv")
    if re.search(r"\bremux\b", text):
        tags.add("source:remux")
    if re.search(r"\buhd\b", text):
        tags.add("source:uhd")

    if re.search(r"\bdts[-. ]?hd\b|\bdts\b", text):
        tags.add("audio:dts")
    if re.search(r"\btruehd\b", text):
        tags.add("audio:truehd")
    if re.search(r"\batmos\b", text):
        tags.add("audio:atmos")
    if re.search(r"\baac\b", text):
        tags.add("audio:aac")
    if re.search(r"\beac3\b|\bddp\b", text):
        tags.add("audio:eac3")
    if re.search(r"\bac3\b|\bdolby[ .-]?digital\b", text):
        tags.add("audio:ac3")

    if re.search(r"\bmkv\b", text):
        tags.add("container:mkv")
    if re.search(r"\bmp4\b", text):
        tags.add("container:mp4")
    if re.search(r"\bavi\b", text):
        tags.add("container:avi")

    if re.search(r"\brepack\b", text):
        tags.add("other:repack")
    if re.search(r"\bproper\b", text):
        tags.add("other:proper")
    if re.search(r"\bremastered\b", text):
        tags.add("other:remastered")
    if re.search(r"\bextended\b", text):
        tags.add("other:extended")
    if re.search(r"\b10[- ]?bit\b", text):
        tags.add("other:10bit")

    return sorted(tags)


def parse_part(subject: str) -> tuple[int, int]:
    match = PART_RE.search(subject)
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


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


def strip_article_headers(lines: list[str]) -> list[str]:
    if not lines:
        return []
    for idx, line in enumerate(lines):
        if line.strip() == "":
            return lines[idx + 1 :]
    return lines


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


def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"
