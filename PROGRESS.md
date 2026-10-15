# Progress

Last updated after Phase 6 (outputs, daily.py, run.py).

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Project setup and storage | done | Config, schema, ignore files, cap, and storage report. |
| 2. Ingestion and backfill | done | nba_api, PlayByPlayV3 possessions, live-feed fallback, backfill.py. |
| 3. Injury report and overrides | done | Official PDF parse via pypdf, overrides.yaml precedence. |
| 4. Projections | done | Blend, context, absence redistribution, minutes model. |
| 5. Simulation | done | Vectorized possession engine; ~5s for 10k runs. |
| 6. Outputs and daily.py | done | Summaries, results/latest JSON, prediction history, daily.py, run.py. |
| 7. Backtesting | not started | Walk-forward metrics and tuning. |

## Phase 3

`ingest/injuries.py` downloads and parses the official NBA injury PDF in memory. `overrides.yaml` wins on status and minutes caps. Nothing is written under `DATA_DIR`.

## Phase 4

`projections/` builds per-game player rates and minutes from stored logs/rates with `as_of` cutoff (no future leakage). Blend weights, form decay, regression, pace/rest/home factors, and minutes variance come from `config.yaml`.

## Phase 5

`sim/engine.py` vectorizes possessions across runs. Steals, turnovers, FTs, zone shots, blocks, assists, rebounds, pace noise, overtime. Seeded and reproducible. ~5s for 10k runs on the sample IND@ORL game.

## Phase 6

- `outputs/summarize.py`: mean and p10–p90 for player stats and combos, plus game win/OT/margin/total.
- `outputs/json_writer.py`: one JSON per game in `results/latest/` (overwritten).
- `outputs/history.py`: upserts `prediction_history`, then fills actuals from final logs/schedule.
- `outputs/pipeline.py`: projections → sim → summarize → JSON/history.
- `run.py`: `--date` with `--game AWAY-HOME` or `--all`.
- `daily.py`: ingest current season → injuries → slate → finish_run/storage report.

Checked with `run.py --date 2024-10-28 --game IND-ORL --season 2024-25 --runs 200 --seed 9 --skip-injury-pdf`: home_win≈0.51, JSON written, history actuals filled, storage report printed.

## Next

Phase 7: walk-forward backtest metrics and parameter tuning.
