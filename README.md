# TriceraPost

Private, self-hosted Usenet indexer that scans binary groups, discovers releases, and builds verified NZBs for your downloader. It runs as a standalone Python service or as a Synology DSM package.

## Requirements

- Python 3.x
- NNTP access credentials

## Install (Standalone)

1. Copy `.env.example` to `.env` and fill in values.
2. Start the local web UI:

```
python3 server.py
```

The server loads `groups.json`, filters for groups with `bin`/`binary` in the name, and emits a default `scan_requested` on startup. Visit `/settings` to store NNTP credentials locally in `data/settings.json` (override with `TRICERAPOST_SETTINGS_PATH`).

Run everything (workers + server + scheduler):

```
python3 tricerapost.py
```

## Install (Synology DSM)

1. Ensure DSM's `Python3` package is installed.
2. Build the SPK:

```
./synology/build_spk.sh
```

3. Open DSM Package Center and choose Manual Install.
4. Select `synology/build/TriceraPost.spk`.

After install, launch TriceraPost from the DSM app menu.

## Swagger

This project uses Swagger (OpenAPI) for API documentation. See https://swagger.io/ for tooling and UI details.

## Service Breakdown

- `services/ingest_worker.py`: consumes `scan_requested` events and ingests headers.
- `services/nzb_expander.py`: consumes `nzb_seen` events and validates NZBs before storing.
- `services/aggregate_writer.py`: rebuilds release tables on ingest/NZB events.
- `services/writer_worker.py`: writes ingest/state data into SQLite.
- `services/scheduler.py`: emits `scan_requested` events.
- `server.py`: local API + UI for browsing.
