#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

zig build-exe \
  -target wasm32-freestanding \
  -O ReleaseFast \
  -fno-entry \
  "$ROOT_DIR/wasm/pipeline.zig" \
  -femit-bin="$ROOT_DIR/wasm/pipeline.wasm"
