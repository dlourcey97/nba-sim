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

`backfill.py` reads the data.nba.com season schedule (browser user agent, nothing written to disk), then box scores and possessions. nba_api `LeagueGameLog` is used when `stats.nba.com` answers. Otherwise the live S3 box score is used. Possessions come from the pbpstats live feed, then `stats.nba.com` only if that probe succeeded. Raw JSON is not stored. `ARCHIVE_DIR` is unused while `archive.save_play_by_play` is false.

- Final games write `player_game_logs`, `team_game_results` (pace is offensive possessions), `player_game_rates`, and a schedule row.
- Scheduled games upsert the schedule row only.
- A game already in both logs and rates is skipped, so a rerun resumes.
- Logs and team results are written before rates, so a crash still retries the missing half with pace already stored.
- Derived aggregates and zone defense are replaced from the stored season at the end of each season.
- `_COMPLETE` is written only for an older season after a full run with no failures. `--start-date`, `--end-date`, and `--max-games` keep the season unfrozen. Replace-policy tables are never frozen.
- Exit status is 1 when any game or schedule fetch failed.

Checked one game only: `2024-25`, `2024-10-22`, `--max-games 1`. Stored `0022400061` (NYK at BOS, 109-132, 23 players, 10 starters, 90 offensive possessions each, no overtime). Second run skipped that game. `DATA_DIR` was 24529 bytes, with no `.json`, no `_tmp`, and no `_COMPLETE`. The full `2015-2025` pull was not run.

`stats.nba.com` timed out with 0 bytes on a 12 second probe. Early seasons whose live feeds return 403 stay incomplete until that host answers. Rerun the same command; it will not mark those seasons complete.

## Next

Phase 3: official injury PDF and `overrides.yaml`.

Overnight full backfill, from the repo root after the data directories exist:

```bash
python3 backfill.py --seasons 2015-2025 --log-file /var/lib/nba-sim/backfill.log
```
