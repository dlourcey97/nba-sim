# Progress

Last updated after Phase 2.

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Project setup and storage | done | Config, schema, ignore files, cap, and storage report. |
| 2. Ingestion and backfill | done | nba_api, pbpstats, incremental tables, backfill.py. Small-range test only. |
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

Open issues: none.

## Phase 2

`backfill.py` writes compact logs, team results, rates, and a schedule row. Raw JSON is not stored. `ARCHIVE_DIR` is unused while `archive.save_play_by_play` is false.

Schedule order:

- The current season is read from `cdn.nba.com/static/json/staticData/scheduleLeagueV2.json`. The request includes browser client hints (`sec-ch-ua`, `sec-fetch-*`). Without those headers the CDN returns 403. On 2026-10-14 that file is the 2026-27 season.
- Other seasons try `stats.nba.com` `LeagueGameLog`, then `LeagueGameFinder`, with nba_api's browser headers, a 60 second timeout, and exponential backoff for errors that return a response. A read that returns no bytes is not repeated five times.
- When `stats.nba.com` times out, the season file on `data.nba.com` is used. With the same browser headers that file returns 200. A headerless client gets 403.

Player logs prefer the live box score. `stats.nba.com` is not called again in a run after it has timed out, so the live feed is used directly. Possessions come from the pbpstats live feed.

- Final games write `player_game_logs`, `team_game_results` (pace is offensive possessions), `player_game_rates`, and a schedule row.
- Scheduled games upsert the schedule row only.
- A game already in both logs and rates is skipped, so a rerun resumes.
- Logs and team results are written before rates.
- Derived aggregates and zone defense are replaced from the stored season at the end of each season.
- `_COMPLETE` is written only for an older season after a full run with no failures. Date filters and `--max-games` keep the season unfrozen.
- `http.timeout_seconds` is 60. `http.max_retries` is 5.

`LeagueGameLog` for 2024-25 Regular Season was called with those headers and a 60 second timeout. Five attempts, then one more during backfill, all timed out with 0 bytes (`ReadTimeout`).

One game, `2024-10-22`, `--max-games 1`: stored `0022400061` (NYK at BOS). `DATA_DIR` 24529 bytes. Exit 0.

One week, `2024-10-22` through `2024-10-29`: stored 56 games, 1264 player rows, 560 starters, pace from 90 to 115. `DATA_DIR` 97589 bytes. No `.json`, no `_tmp`, and no `_COMPLETE`. Exit 0. The full `2015-2025` pull was not run.

## Next

Phase 3: official injury PDF and `overrides.yaml`.

Overnight full backfill, from the repo root after the data directories exist:

```bash
python3 backfill.py --seasons 2015-2025 --log-file /var/lib/nba-sim/backfill.log
```
