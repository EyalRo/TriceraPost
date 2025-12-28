#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

zig build-exe \
  -target wasm32-freestanding \
  -O ReleaseFast \
  -fno-entry \
  --export=alloc \
  --export=dealloc \
  --export=parse_overviews \
  --export=parse_tag_mask \
  --export-memory \
  "$ROOT_DIR/parsers/overview/zig/pipeline.zig" \
  -femit-bin="$ROOT_DIR/parsers/overview/wasm/pipeline.wasm"
