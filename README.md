# nba-sim

NBA Monte Carlo simulation engine. It simulates player stat distributions and game outcomes. It does not compute odds, lines, or betting edges.

Game data lives outside this repository. `DATA_DIR` and `ARCHIVE_DIR` in `.env` must be absolute paths outside the repo. The default cap is 2 GiB. A run stops instead of writing past it.

```bash
pip install -e ".[dev]"
pytest
python -m nba_sim
```

`python -m nba_sim` prints a storage report for `DATA_DIR` (bytes per table and season, plus the total) and exits with status 1 when the cap is exceeded.

Table layouts are in `SCHEMA.md`. Phase status is in `PROGRESS.md`. Tunable blend, minutes, and simulation parameters are in `config.yaml`. Manual injury overrides live in `overrides.yaml`.

## Simulate

```bash
python run.py --date 2024-10-28 --game IND-ORL --season 2024-25 --runs 1000 --seed 1 --skip-injury-pdf
python run.py --date 2024-10-28 --all --season 2024-25 --runs 1000 --skip-injury-pdf
```

JSON summaries land in `results/latest/` (gitignored). Prediction history is upserted under `DATA_DIR/prediction_history/`.

## Nightly

```bash
python daily.py --date 2026-10-21 --log-file /Users/deanlourcey/nba_archive/daily.log
```

Ingests the current season, fetches the injury PDF, simulates the slate, writes JSON and history, then prints the storage report.

## Backfill

Create the data directories from `.env` first. The log file has to sit outside the repo.

```bash
mkdir -p /Users/deanlourcey/nba_data /Users/deanlourcey/nba_archive
python3 backfill.py --seasons 2015-2025 --log-file /Users/deanlourcey/nba_archive/backfill.log
```

That command is the full historical pull. It is rate-limited and resumable: run the same command again after an interruption. Games already stored in both `player_game_logs` and `player_game_rates` are skipped. A season is frozen only when that run had no date filter, no `--max-games`, and no failed games. Exit status is 1 when any game failed.

Historical seasons use `stats.nba.com` first: `LeagueGameLog` for the schedule, `BoxScoreTraditional` for player lines, and `PlayByPlayV3` for possessions. When that host does not answer, schedules come from `data.nba.com` and box scores come from the live NBA feed. The current season uses `cdn.nba.com` when that file is for the requested season, and the live play-by-play feed for possessions. The live feed is also the fallback for an older game. A response that is not JSON is logged once and not retried; that game's box score is stored and its possessions are left for a later run of the same command. The requests send browser client hints; without them the CDN returns 403.

Every 25 final games the run prints `season`, games done/total, and failures.

A one-day check, which does not freeze the season:

```bash
python3 backfill.py --season 2024-25 --start-date 2024-10-22 --end-date 2024-10-22 --max-games 1
```
