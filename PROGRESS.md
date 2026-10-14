# Progress

Last updated after Phase 1.

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Project setup and storage | done | Config, schema, ignore files, cap, and storage report. |
| 2. Ingestion and backfill | not started | nba_api, pbpstats, incremental tables, backfill.py. |
| 3. Injury report and overrides | not started | Official PDF plus overrides.yaml. |
| 4. Projections | not started | Blend, context, minutes model. |
| 5. Simulation | not started | Possession engine. |
| 6. Outputs and daily.py | not started | JSON summaries, prediction history, nightly pipeline. |
| 7. Backtesting | not started | Walk-forward metrics and tuning. |

## Phase 1

Built the Python package, `.env`, `.gitignore`, `.cursorignore`, `config.yaml`, `SCHEMA.md`, and the storage utilities in `nba_sim/storage.py`.

- `DATA_DIR` and `ARCHIVE_DIR` are absolute paths outside the repository.
- Each table is one ZSTD Parquet file at `{DATA_DIR}/{table}/season={season}/data.parquet`.
- `incremental_current` adds new keys only (`player_game_logs`, `team_game_results`).
- `upsert_current` updates current-season keys (`schedule`, `prediction_history`) so finals and actuals can land on the same row.
- `replace` rewrites derived partitions (`player_game_rates`, season aggregates, `team_zone_defense`).
- `mark_season_complete` writes `_COMPLETE` and later writes to that season fail.
- Backfill opts in with `allow_historical=True` until the marker is written. Nightly calls leave it false.
- `finish_run` deletes `_tmp/` and `*.tmp`, prints bytes per table and season, and aborts when `storage.max_bytes` is exceeded (default 2 GiB).
- DuckDB runs in memory. No `.duckdb` file is kept. Raw responses and simulation draws are not stored.

Open issues: none. Phase 2 should fetch a game once it is final for box scores, and upsert the schedule row from scheduled to final.

## Next

Phase 2: ingestion with nba_api and pbpstats, compact tables, incremental updates, and `backfill.py`. Test on a small date range before a full historical pull.
