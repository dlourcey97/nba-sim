# Progress

Last updated after PlayByPlayV3 possessions and the 5-game checks for 2015-16 and 2019-20.

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Project setup and storage | done | Config, schema, ignore files, cap, and storage report. |
| 2. Ingestion and backfill | done | nba_api, PlayByPlayV3 possessions, live-feed fallback, backfill.py. Sample games from 2015-16, 2019-20, and 2024-25. |
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

This checkout now runs on the local Mac, not the cloud VM. Python 3.13.12 is installed. The virtualenv is `.venv`. `.env` points at `DATA_DIR=/Users/deanlourcey/nba_data` and `ARCHIVE_DIR=/Users/deanlourcey/nba_archive`.

Source order for a historical season:

- `stats.nba.com` is primary. The schedule uses `LeagueGameLog`, then `LeagueGameFinder`. Each final game uses `BoxScoreTraditional` (that response includes `START_POSITION`), then the season player `LeagueGameLog`.
- If `stats.nba.com` does not answer, the season file on `data.nba.com` supplies the schedule and the live box score supplies player lines. The current season still reads `cdn.nba.com/static/json/staticData/scheduleLeagueV2.json` when that file matches `season.current`. Those CDN requests send browser client hints (`sec-ch-ua`, `sec-fetch-*`).
- Historical possessions use `stats.nba.com` PlayByPlayV3 (`playbyplayv3`). The live feed remains the source for the current season and the fallback when PlayByPlayV3 does not answer. Actions are parsed into the same per-game rate rows (lineups from the box-score starters plus substitutions; shot zones use the same distance cutoffs).
- A response that is not JSON (HTML, empty, or an error page) is not retried. It is logged once. The game is recorded as possessions missing, its box score and game logs are still stored, and the run moves on. A later run retries it because the game is in the logs but not in `player_game_rates`. Pace that was left null is filled when the possessions arrive. The season is not frozen while any game is missing possessions.
- Every 25 final games, and again at the end of the season type, the run prints `season`, games done/total, and failures.
- Older box scores put a position on every player. Only the first five such rows per team are stored as starters.
- Requests use nba_api's browser headers, a 60 second timeout, and exponential backoff for errors that return a response. A read that returns no bytes, and a body that is not JSON, are not repeated five times. After one failed `stats.nba.com` schedule call, the rest of that run uses the schedule fallbacks. One bad play-by-play response does not turn that off.

Storage rules are unchanged:

- Final games write `player_game_logs`, `team_game_results` (pace is offensive possessions), `player_game_rates`, and a schedule row. If possessions are missing, the logs and the team score are still written and the rate rows are left for the next run.
- Scheduled games upsert the schedule row only.
- A game already in both logs and rates is skipped, so a rerun resumes.
- Logs and team results are written before rates.
- Derived aggregates and zone defense are replaced from the stored season at the end of each season.
- `_COMPLETE` is written only for an older season after a full run with no failures. Date filters and `--max-games` keep the season unfrozen.

`LeagueGameLog` for 2024-25 Regular Season succeeded from this Mac: 2460 team rows, inside the 60 second timeout.

One week, `2024-10-22` through `2024-10-29`: stored 56 games from `BoxScoreTraditional`, 1264 player rows, 560 starters, pace from 90 to 115.

Five regular-season games from 2015-16 (`0021500001` through `0021500005`) and five from 2019-20 (`0021900001` through `0021900005`): 10 games stored, 0 failed, 0 possessions missing. 2015-16 has 102 player rows and 50 starters, pace 95 to 102. 2019-20 has 99 player rows and 50 starters, pace 94 to 114, including one overtime game. `DATA_DIR` is 167128 bytes. No `.json`, no `_tmp`, and no `_COMPLETE` (the samples used `--max-games`). Exit 0. The full `2015-2025` pull was not run.

## Next

Phase 3: official injury PDF and `overrides.yaml`.

Overnight full backfill, from the repo root after the data directories exist:

```bash
.venv/bin/python backfill.py --seasons 2015-2025 --log-file /Users/deanlourcey/nba_archive/backfill.log
```
