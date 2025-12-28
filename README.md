# TriceraPost

Private, self-hosted Usenet indexer that scans binary groups, discovers releases, and outputs verified NZB files for your NZB client.

## Status

Single-process pipeline (scan → ingest → aggregate → filter → verify) optimized for single-machine runtimes, with a lightweight UI/API.

## Requirements

- Python 3.13
- NNTP access credentials
- Optional: `wasmtime` Python package for WASM-accelerated overview parsing (installed by `nix develop`)

## Setup

1. Copy `.env.example` to `.env` and fill in values.
2. Run one of the scripts.

## Usage

Start the local web UI:

```
python3.13 gui/server.py
```

Visit `/settings` to store NNTP credentials locally in `data/settings.json` (override with `TRICERAPOST_SETTINGS_PATH`).

Run the single-process pipeline (scan + aggregate + filter in one process):

```
python3.13 app/pipeline.py
```

For periodic scans in single-process mode, set an interval:

```
TRICERAPOST_SCHEDULER_INTERVAL=3600 python3.13 app/pipeline.py
```

## Synology SPK

Minimal DSM 7.3+ packaging files are in `synology/`. Build the SPK with:

```
./synology/build_spk.sh
```

See `synology/README.md` for install notes.

## API

Base URL: `http://127.0.0.1:8080`

- `GET /api/groups` → list of NNTP groups from `groups.json`
- `GET /api/releases` → list of complete releases (includes `nzb_created` flag)
- `GET /api/releases/raw` → raw aggregated releases
- `GET /api/nzbs` → list of saved NZB files
- `GET /api/nzb/file?key=...` → download a stored NZB file

## Service Breakdown

- `app/pipeline.py`: single-process pipeline (scan → ingest → aggregate → filter).
- `gui/server.py`: local API + UI for browsing.

## Notes

- SQLite state is split into per-table files (state/ingest/releases/complete/nzbs) unless `TRICERAPOST_DB_PATH` is set to a single file or `TRICERAPOST_DB_IN_MEMORY=1` is enabled.
- Saved NZB files live in `nzbs/`. Invalid NZBs are tracked in SQLite but not written to disk.
- WASM acceleration is enabled automatically when `parsers/overview/wasm/pipeline.wasm` exists and `wasmtime` is installed (the Python package, not just the CLI). Set `TRICERAPOST_DISABLE_WASM=1` to force Python parsing. Use `TRICERAPOST_PIPELINE_WASM=/path/to/pipeline.wasm` to override the module path.

## Build and Test

Run the full Nix checks (tests + WASM build):

```
nix develop -c nix flake check
```

Run pipeline tests directly:

```
python3.13 -m unittest tests.test_pipeline
```

Compile the WASM module:

```
./parsers/overview/build.sh
```

## WASM Build (Zig)

Build the Zig WASM module for overview parsing:

```
./parsers/overview/build.sh
```

If you use Nix:

```
nix develop
./parsers/overview/build.sh
```
