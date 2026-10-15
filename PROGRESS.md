# Progress

Last updated after Phase 4 (projection blending, context, minutes).

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Project setup and storage | done | Config, schema, ignore files, cap, and storage report. |
| 2. Ingestion and backfill | done | nba_api, PlayByPlayV3 possessions, live-feed fallback, backfill.py. Sample games from 2015-16, 2019-20, and 2024-25. |
| 3. Injury report and overrides | done | Official PDF parse via pypdf, overrides.yaml precedence, in-memory only. |
| 4. Projections | done | Blend, opponent/pace/rest context, absence redistribution, minutes model. |
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

Storage rules are unchanged. Sample coverage: 2015-16 (5 games), 2019-20 (5 games), 2024-25 (one week). Full `2015-2025` backfill is run separately.

## Phase 3

`ingest/injuries.py` downloads the official NBA injury PDF from `ak-static.cms.nba.com` (with `static.cms.nba.com` as a second host), parses it with `pypdf`, and discards the bytes. `overrides.yaml` wins on status and minutes caps. Injury rows are not written under `DATA_DIR`.

## Phase 4

`projections/` builds per-game player rates and minutes from stored logs/rates only (no future leakage when `as_of` is the game date).

- `rates.py`: per-possession vectors (usage, TOV, FT, rebound/assist/steal/block, zone shares and FG%).
- `blend.py`: multi-season baseline from `config.yaml` season weights, exponential recent-form decay, position regression with `regression_strength`.
- `context.py`: opponent zone defense, home/away and rest pace, teammate absence usage redistribution, injury name→id match.
- `minutes.py`: rotation mean with variance, out/doubtful → 0, questionable/probable discounts, minutes_cap.
- `build.py`: roster from recent appearances (up to 15), returns `GameProjection`.

Checked on `0022400102` (IND@ORL, 2024-10-28) in `DATA_DIR`: home/away possessions ~100, usage among active teammates ~1.0, out override zeros minutes.

Open issues: with only sample seasons in `DATA_DIR`, multi-season player baselines are thin until the full backfill finishes; position priors fill the gap.

## Next

Phase 5: possession-level simulation engine.
