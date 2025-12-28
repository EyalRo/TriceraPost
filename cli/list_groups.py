#!/usr/bin/env python3.13
import argparse
import json
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.nntp_client import NNTPClient


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


def main() -> int:
    load_env()

    parser = argparse.ArgumentParser(description="List NNTP newsgroups to a file.")
    parser.add_argument("--output", default="groups.json", help="Output file path")
    parser.add_argument(
        "--format",
        choices=("json", "tsv"),
        help="Output format (default: inferred from output extension)",
    )
    args = parser.parse_args()

    host = os.environ.get("NNTP_HOST")
    if not host:
        print("NNTP_HOST not set in .env")
        return 1

    port = int(os.environ.get("NNTP_PORT", "119"))
    use_ssl = get_env_bool("NNTP_SSL")
    user = os.environ.get("NNTP_USER")
    password = os.environ.get("NNTP_PASS")

    client = NNTPClient(host, port, use_ssl=use_ssl)
    client.connect()
    client.reader_mode()
    client.auth(user, password)
    try:
        groups = client.list()
    finally:
        client.quit()

    output_format = args.format
    if not output_format:
        output_format = "json" if args.output.lower().endswith(".json") else "tsv"

    if output_format == "json":
        payload = []
        for group in groups:
            name = group.get("group") or ""
            high = group.get("high") or ""
            low = group.get("low") or ""
            flags = group.get("flags") or ""
            raw = group.get("raw") or ""
            payload.append(
                {
                    "group": name,
                    "low": low,
                    "high": high,
                    "flags": flags,
                    "raw": raw,
                }
            )
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
    else:
        with open(args.output, "w", encoding="utf-8") as handle:
            for group in groups:
                name = group.get("group") or ""
                high = group.get("high") or ""
                low = group.get("low") or ""
                flags = group.get("flags") or ""
                handle.write(f"{name}\t{low}\t{high}\t{flags}\n")

    print(f"Wrote {len(groups)} groups to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
