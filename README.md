# TriceraPost

Private, self-hosted Usenet indexer that scans binary groups, discovers releases, and outputs verified NZB files for your NZB client.

## Status

Single-process pipeline (scan → ingest → aggregate → filter → verify) optimized for single-machine runtimes, with a lightweight UI/API. Legacy worker-based services remain available if you prefer the event-bus flow.

## Requirements

- Python 3.x
- NNTP access credentials

## Setup

1. Copy `.env.example` to `.env` and fill in values.
2. Run one of the scripts.

## Usage

List groups to JSON:

```
python3 list_groups.py --output groups.json
```

Start the local web UI:

```
python3 server.py
```

The server loads `groups.json`, filters for groups with `bin`/`binary` in the name, and emits a default `scan_requested` on startup. Visit `/settings` to store NNTP credentials locally in `data/settings.json` (override with `TRICERAPOST_SETTINGS_PATH`).

Run the single-process pipeline (scan + aggregate + filter in one process):

```
python3 tricerapost.py
```

Run the legacy worker stack (event bus + workers):

```
TRICERAPOST_MODE=eda python3 tricerapost.py
```

For periodic scans in single-process mode, set an interval:

```
TRICERAPOST_SCHEDULER_INTERVAL=3600 python3 tricerapost.py
```

For DSM Task Scheduler with the legacy worker stack, you can run periodic scans with:

```
python3 services/scheduler.py
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

- `services/pipeline.py`: single-process pipeline (scan → ingest → aggregate → filter).
- `services/ingest_worker.py`: consumes `scan_requested` events and ingests headers.
- `services/nzb_expander.py`: consumes `nzb_seen` events and validates NZBs before storing.
- `services/aggregate_writer.py`: rebuilds release tables on ingest/NZB events.
- `services/writer_worker.py`: writes ingest/state data into SQLite.
- `services/scheduler.py`: emits `scan_requested` events.
- `server.py`: local API + UI for browsing.

## Notes

- SQLite state is split into per-table files (state/ingest/releases/complete/nzbs) unless `TRICERAPOST_DB_PATH` is set to a single file or `TRICERAPOST_DB_IN_MEMORY=1` is enabled.
- Saved NZB files live in `nzbs/`. Invalid NZBs are tracked in SQLite but not written to disk.
