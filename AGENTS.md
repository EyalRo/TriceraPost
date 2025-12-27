# AGENTS

## Working Agreement

- Keep the scope to private, self-hosted indexing only.
- Avoid external services, telemetry, or analytics.
- Prefer simple, readable code with minimal dependencies.
- Store state in local files (JSON/SQLite) only.

## Project Layout

- `services/ingest_worker.py`: NNTP ingest worker (consumes `scan_requested`).
- `services/nzb_expander.py`: NZB expander worker (consumes `nzb_seen`).
- `services/aggregate_writer.py`: rebuilds release tables on ingest/NZB events.
- `services/writer_worker.py`: writes ingest/state data into SQLite.
- `services/scheduler.py`: emits `scan_requested`.
- `server.py`: local API + UI.
- `list_groups.py`: dump NNTP group listings to JSON/TSV.
- `data/`: SQLite storage (split per table) and events bus if not running in RAM.
- Default scan uses groups from `groups.json` whose names include `bin`/`binary`.
- `nzbs/`: stored NZB files (found or generated).
- Invalid NZBs are tracked in SQLite and excluded from the UI.

## Debugging

- Use `curl` against the API to validate service behavior:
  - `curl -s http://127.0.0.1:8080/api/releases`
  - `curl -s http://127.0.0.1:8080/api/releases/raw`
  - `curl -s http://127.0.0.1:8080/api/nzbs`
  - `curl -s http://127.0.0.1:8080/api/nzb/file?key=...`
- If `/mnt/stags/.ssh` is missing, try SSH certs in `~/.ssh` for git operations.

## Local Env

- `.env` holds NNTP credentials and defaults.
- `.env.example` documents required variables.

## Commands

```
python3 list_groups.py --output groups.json
python3 nntp_search.py
python3 tricerapost.py
```
