# TriceraPost

Private, self-hosted Usenet indexer that scans binary groups, discovers releases, and outputs verified NZB files for your NZB client.

## Status

Split into simple services (ingest → aggregate → filter) with a lightweight UI/API. NZBs are verified against NNTP before they are saved or shown in the UI.

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

Start the local web UI (binds to `127.0.0.1` by default, override with `TRICERAPOST_BIND_HOST`):

```
python3 server.py
```

The server loads `groups.json`, filters for groups with `bin`/`binary` in the name, and emits a default `scan_requested` on startup. Visit `/settings` to store NNTP credentials locally in `data/settings.json` (override with `TRICERAPOST_SETTINGS_PATH`). NZBs are stored in SQLite by default; enable disk writes in settings or with `TRICERAPOST_SAVE_NZBS=1` and `TRICERAPOST_NZB_DIR=/path/to/nzbs`.

Run everything (workers + server + scheduler):

```
python3 tricerapost.py
```

For DSM Task Scheduler, you can run periodic scans with:

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
- `GET /api/status` → ingest/NZB counters for the UI
- `GET /api/nzb/file?key=...` → download a stored NZB file
- `POST /api/nzb/save_all` → persist all stored NZB payloads to disk
- `POST /api/admin/clear_db` → wipe SQLite state (requires `{"confirm": true}` payload)

## Service Breakdown

- `services/ingest_worker.py`: consumes `scan_requested` events and ingests headers.
- `services/nzb_expander.py`: consumes `nzb_seen` events and validates NZBs before storing.
- `services/aggregate_writer.py`: rebuilds release tables on ingest/NZB events.
- `services/writer_worker.py`: writes ingest/state data into SQLite.
- `services/scheduler.py`: emits `scan_requested` events.
- `server.py`: local API + UI for browsing.

## Notes

- SQLite state is split into per-table files (state/ingest/releases/complete/nzbs) unless `TRICERAPOST_DB_IN_MEMORY=1`.
- NZB payloads are stored in SQLite; disk writes are optional via settings or `TRICERAPOST_SAVE_NZBS=1` and `TRICERAPOST_NZB_DIR=/path/to/nzbs`.
- Invalid NZBs are tracked in SQLite but not written to disk.
