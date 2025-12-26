#!/usr/bin/env python3
import xml.etree.ElementTree as ET
from typing import Optional

from services.release_utils import NZB_HINT_RE, decode_yenc


def build_nzb_payload(lines: list[str]) -> Optional[bytes]:
    text = "\n".join(lines)
    if NZB_HINT_RE.search(text):
        return text.encode("utf-8", errors="ignore")
    if any(line.startswith("=ybegin") for line in lines):
        decoded = decode_yenc(lines).decode("utf-8", errors="ignore")
        if NZB_HINT_RE.search(decoded):
            return decoded.encode("utf-8")
    return None


def parse_nzb_segments(payload: bytes) -> list[dict]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []
    segments = []
    for seg in root.findall(".//{*}segments/{*}segment"):
        message_id = (seg.text or "").strip()
        if message_id.startswith("<") and message_id.endswith(">"):
            message_id = message_id[1:-1].strip()
        try:
            size = int(seg.attrib.get("bytes", "0"))
        except ValueError:
            size = 0
        try:
            number = int(seg.attrib.get("number", "0"))
        except ValueError:
            number = 0
        if message_id:
            segments.append({"message_id": message_id, "bytes": size, "number": number})
    return segments


def build_nzb_xml(
    *,
    name: str,
    poster: Optional[str],
    groups: list[str],
    segments: list[dict],
) -> bytes:
    nzb = ET.Element("nzb", {"xmlns": "http://www.newzbin.com/DTD/2003/nzb"})
    file_elem = ET.SubElement(
        nzb,
        "file",
        {
            "poster": poster or "",
            "subject": name or "release",
            "date": "0",
        },
    )
    groups_elem = ET.SubElement(file_elem, "groups")
    for group in groups:
        if group:
            ET.SubElement(groups_elem, "group").text = group
    segments_elem = ET.SubElement(file_elem, "segments")
    for segment in segments:
        message_id = segment.get("message_id") or ""
        if message_id.startswith("<") and message_id.endswith(">"):
            message_id = message_id[1:-1].strip()
        seg_elem = ET.SubElement(
            segments_elem,
            "segment",
            {
                "bytes": str(segment.get("bytes") or 0),
                "number": str(segment.get("number") or 0),
            },
        )
        seg_elem.text = message_id
    return ET.tostring(nzb, encoding="utf-8", xml_declaration=True)
