# Progress

Last updated after Phase 7 (backtesting and tuning). All build phases are done.

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Project setup and storage | done | Config, schema, ignore files, cap, and storage report. |
| 2. Ingestion and backfill | done | nba_api, PlayByPlayV3 possessions, live-feed fallback, backfill.py. |
| 3. Injury report and overrides | done | Official PDF parse via pypdf, overrides.yaml precedence. |
| 4. Projections | done | Blend, context, absence redistribution, minutes model. |
| 5. Simulation | done | Vectorized possession engine; ~5s for 10k runs. |
| 6. Outputs and daily.py | done | Summaries, results/latest JSON, prediction history, daily.py, run.py. |
| 7. Backtesting | done | Walk-forward metrics, calibration SVG, blend-parameter tuner. |

## Phase 3

`ingest/injuries.py` downloads and parses the official NBA injury PDF in memory. `overrides.yaml` wins on status and minutes caps. Nothing is written under `DATA_DIR`.

## Phase 4

`projections/` builds per-game player rates and minutes from stored logs/rates with an `as_of` cutoff. Blend window falls back to older available seasons when recent partitions are missing (partial backfill). Rosters prefer the newest season with appearances.

## Phase 5

`sim/engine.py` vectorizes possessions across runs. Steals, turnovers, FTs, zone shots, blocks, assists, rebounds, pace noise, overtime. ~5s for 10k runs on the sample IND@ORL game.

## Phase 6

Summaries → `results/latest/*.json` and `prediction_history` (actuals filled after finals). `run.py` for single games/slates. `daily.py` for ingest → injuries → sim → storage report.

## Phase 7

- `backtest/metrics.py`: Brier (home win), MAE for PTS/REB/AST/MIN, 10th–90th coverage, calibration bins, SVG plot.
- `backtest/evaluate.py`: walk-forward over finals with prior same-season games only; writes `results/backtest/metrics.json` and `calibration.svg`.
- `backtest/tune.py`: small grid over `form_decay`, `regression_strength`, and season weights; optional `--write` into `config.yaml`.

Checked on `DATA_DIR` 2024-25 with `--max-games 4 --runs 100`: metrics and calibration SVG written. Full pytest: 51 passed.

Open issues: backtest metrics on the sample week are noisy (few games, thin multi-season player history until the overnight backfill finishes). Re-run `backtest/evaluate.py --seasons 2023-2025` after more seasons land.

## Commands

```bash
python backfill.py --seasons 2015-2025 --log-file /Users/deanlourcey/nba_archive/backfill.log
python daily.py --log-file /Users/deanlourcey/nba_archive/daily.log
python run.py --date 2026-10-21 --game BOS-NYK --runs 10000
python run.py --date 2026-10-21 --all
python backtest/evaluate.py --seasons 2023-2025
python backtest/tune.py --seasons 2024-25 --max-games 12
```
