# AGENTS

## Working Agreement

- Keep the scope to private, self-hosted indexing only.
- Avoid external services, telemetry, or analytics.
- Prefer simple, readable code with minimal dependencies.
- Store state in local files (JSON/SQLite) only.

## Project Layout

- `services/pipeline.py`: single-process pipeline (scan → ingest → aggregate → filter).
- `server.py`: local API + UI.
- `list_groups.py`: dump NNTP group listings to JSON/TSV.
- `data/`: SQLite storage (split per table unless `TRICERAPOST_DB_PATH` is set).
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
- `TRICERAPOST_DB_PATH=/path/to/tricerapost.db` forces a single SQLite file for all tables.

## Commands

```
python3 list_groups.py --output groups.json
python3 nntp_search.py
python3 tricerapost.py
```
