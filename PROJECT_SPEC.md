Build an NBA Monte Carlo simulation engine in Python. Read this whole spec first. Work autonomously: do not stop to ask for my approval between steps or phases. After completing each phase, run its tests, fix any failures, update SCHEMA.md and PROGRESS.md, commit with a clear message, and push to the repository. Then continue to the next phase. Only stop to ask me if something is truly blocked (e.g. a data source is unreachable or a decision can't be made from this spec).

== GOAL ==
The engine ONLY runs simulations and outputs the results: player stat distributions and game outcomes. It must NOT include odds, sportsbook lines, betting logic, EV, or edge calculations of any kind.

== MOST IMPORTANT: STORAGE RULES ==
A previous engine of mine broke because it stored too much data. These rules are mandatory:
- All data lives OUTSIDE the repo at a path set by DATA_DIR in .env. Optional raw archive at ARCHIVE_DIR, also outside the repo.
- Use DuckDB + Parquet, partitioned by season (e.g. game_logs/season=2025-26/).
- Keep full history, but ONLY in compact processed form: player game logs, team game results, per-player-per-game rate rows (usage, shot zones, possessions, rebound/assist chances, minutes), season aggregates, schedules, and prediction history.
- Completed seasons are written once and never rewritten. Nightly runs only update the current season incrementally (only fetch games not already stored).
- Derived rate tables are overwritten each run, never appended or versioned.
- NEVER persist raw API responses. Process them, then delete them in the same run.
- Raw play-by-play is processed into per-game rate rows, then either deleted or saved compressed to ARCHIVE_DIR (configurable). The engine never reads ARCHIVE_DIR.
- NEVER save individual simulation runs. Compute summaries in memory and discard the raw runs.
- Prediction history is stored as rows in a single season-partitioned Parquet table (one row per player per game, one row per game for team outcomes), with actual results filled in after games finish.
- Website display files: small JSON summaries in results/latest/ only, overwritten each night.
- Hard size cap on DATA_DIR (default 2 GB, set in config). If exceeded, abort the run with a clear error instead of continuing.
- After every run, print a storage report showing size per table, per season, and total.
- Delete all temp files at the end of each run.

== KEEP CURSOR COSTS LOW ==
- Create .cursorignore and .gitignore excluding DATA_DIR, ARCHIVE_DIR, results/, and all *.parquet, *.duckdb, *.db, *.csv, *.json.gz files.
- Create SCHEMA.md documenting every table, column, type, and partition. Never open or read data files directly; use SCHEMA.md. Keep it updated whenever the schema changes.
- Keep modules small and focused so changes only touch a few files.

== DATA SOURCES ==
- nba_api: game logs, schedules, box scores, team stats, pace, shot zones.
- pbpstats: play-by-play parsed into possessions with lineups.
- Official NBA injury report (PDF): download and parse automatically.
- overrides.yaml: manual injury/lineup changes (e.g. player OUT, minutes cap) that take precedence over the injury report.
- Include retries, rate limiting, and polite delays for all requests. Raw response caching is temporary only (deleted after processing).

== PROJECT STRUCTURE ==
ingest/       data fetching, processing, incremental updates
projections/  rate blending, context adjustments, minutes model
sim/          possession-level simulation engine
outputs/      summary statistics, JSON writers, prediction history
backtest/     evaluation and parameter tuning
config.yaml   all tunable parameters
SCHEMA.md     table documentation
PROGRESS.md   phase status and notes
daily.py      nightly pipeline
backfill.py   one-time historical pull
run.py        CLI for single games / slates

== PROJECTION BLENDING ==
For each player, build per-possession rates by blending:
1. A multi-season baseline, weighted toward recent seasons.
2. Current-season form with exponential decay weighting on recent games.
3. Bayesian-style regression toward position/role averages for small samples (rookies, players with few games).
Then apply context adjustments:
- Opponent defense by shot zone and position
- Both teams' pace
- Home/away
- Rest days and back-to-backs
- Teammate absences: redistribute minutes and usage based on historical splits when those teammates were out
MINUTES MODEL: Project minutes separately using rotation history, injuries, foul trouble rates, and blowout probability. Minutes must have realistic variance.
All blend weights, decay rates, regression strengths, and adjustment factors must be parameters in config.yaml.

== SIMULATION ENGINE ==
- Possession-by-possession simulation of each game.
- Each possession: determine turnover or shot; select shooter by usage; select shot type/zone; resolve make/miss; resolve fouls and free throws; resolve rebounds (offensive/defensive by player rebound rates); credit assists, steals, blocks.
- Add randomness to game pace and player minutes so outputs have realistic variance.
- Handle overtime.
- Default 10,000 runs per game (configurable). Use a seed option for reproducibility.
- Vectorize with numpy where possible for speed.

== OUTPUTS ==
Per player: full distributions for PTS, REB, AST, 3PM, STL, BLK, TOV, MIN, and combos (PRA, PR, PA, RA). Report mean, median, 10th/25th/75th/90th percentiles, and P(stat >= X) for user-supplied thresholds.
Per game: win probability for each team, projected score per team, margin distribution, total distribution, percentiles for each, and overtime probability.
Display: one small JSON per game in results/latest/.
History: append summaries to the prediction history Parquet table.

== BACKTESTING ==
- Walk-forward evaluation using only data available before each game (no future data leakage).
- Metrics: calibration plots (predicted probability vs actual frequency), MAE for player stats, Brier score for win probability, and percentile coverage (about 80% of actual results should land inside the 10th-90th percentile band).
- A tuning script that optimizes the config.yaml blend parameters against historical prediction-vs-actual results.

== COMMANDS ==
python backfill.py --seasons 2015-2025   (one-time, rate-limited, resumable if interrupted)
python daily.py                          (ingest new data -> projections -> simulations -> outputs -> cleanup -> storage report; I run this manually each night; log to a file)
python run.py --date 2026-10-21 --game BOS-NYK --runs 10000
python run.py --date 2026-10-21 --all
python backtest/evaluate.py --seasons 2023-2025

== BUILD PHASES ==
Phase 1: Project setup, .env, .cursorignore, .gitignore, config.yaml, SCHEMA.md, PROGRESS.md, storage cap and storage report utilities.
Phase 2: Ingestion (nba_api + pbpstats) with incremental updates, processing into compact tables, and backfill.py. Test on a small date range first.
Phase 3: Injury report parsing and overrides.yaml.
Phase 4: Projection layer (blending, context adjustments, minutes model).
Phase 5: Simulation engine.
Phase 6: Outputs (summaries, JSON, prediction history) and daily.py.
Phase 7: Backtesting and parameter tuning.

Write tests for each phase. Keep a PROGRESS.md file listing each phase as done / in progress / not started, with short notes on what was built and any open issues. Update it after every phase so any new chat can pick up where the last one left off.
