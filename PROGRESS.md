# Progress

Last updated after Upgrade 2 stint-rotation backtest (2026-10-17).

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Project setup and storage | done | Config, schema, ignore files, cap, and storage report. |
| 2. Ingestion and backfill | done | nba_api, PlayByPlayV3 possessions, live-feed fallback, backfill.py. Preseason supported. |
| 3. Injury report and overrides | done | Official PDF parse via pypdf, overrides.yaml precedence. |
| 4. Projections | done | Blend, context, absence redistribution, minutes model, zone + position defense. |
| 5. Simulation | done | Vectorized possession engine; OREB no longer consumes pace budget. |
| 6. Outputs and daily.py | done | Summaries, results/latest JSON, prediction history, daily.py, run.py. |
| 7. Backtesting | done | Walk-forward includes log loss, CRPS, PIT alongside MAE/Brier. |
| Validation (post-backfill) | done | Position defense, single-game check, full 2024-25/2025-26 backtest, tune. |
| Fix 1. Scoring bias | done | Pace exact; PPG within ~2.3% (was ~−12%). |
| Fix 2. As-of rosters | done | `team_rosters` stints; MIN MAE 5.41; coverage 0.70. |
| Fix 3. Minutes → 240 | done | Coverage **0.79**; MAE MIN 7.14 (worse); PTS MAE improved. |
| Fix 4. Variance ~80% | done | Met by Fix 3 (coverage 0.790 vs ~0.80 target). |
| Fix 5. Team strength / HCA | done | Brier **0.227** (was 0.237); prior-season ORtg/DRtg + home FG. |
| Fix 6. Minutes MAE + roster strength | done | MIN MAE **5.61** (was 7.16); roster-weighted ORtg/DRtg; usage pseudo-possessions. |
| U1. Tuning → calibration | done | Log loss / CRPS / PIT metrics; tune scores calibration not MAE. |
| U2. Stint-based rotations | done | PBP `lineup_stints`; margin×period lineups; depth multipliers. |
| U3–U8 | not started | Game-state, RAPM, overdispersion, Kalman, clusters, incentives. |
| Preseason storage | done | `season_type=Preseason` hive partition; excluded from default reads. |

## Phase 3

`ingest/injuries.py` downloads and parses the official NBA injury PDF in memory. `overrides.yaml` wins on status and minutes caps. Nothing is written under `DATA_DIR`.

## Phase 4

`projections/` builds per-game player rates and minutes from stored logs/rates with an `as_of` cutoff. Blend window uses configured `seasons_back` only (no longer appends every older season once the full history is present).

Opponent defense:

- Zone FG% allowed (existing `team_zone_defense` + as_of scan from rates/logs).
- **Position defense (new):** stats allowed to PG/SG/SF/PF/C from player game logs (`team_position_defense` table + as_of `position_defense_from_bundles`). Listed positions are usually G/F/C; `five_position()` maps those onto the five traditional slots using that appearance’s reb/ast.

## Phase 5

`sim/engine.py` vectorizes possessions across runs. Steals, turnovers, FTs, zone shots, blocks, assists, rebounds, pace noise, overtime.

## Phase 6

Summaries → `results/latest/*.json` and `prediction_history` (actuals filled after finals). `run.py` for single games/slates. `daily.py` for ingest → injuries → sim → storage report.

## Validation (2026-10-16)

Full history is on disk under `DATA_DIR` (2015-16 … 2025-26). Storage ~8.6 MiB, well under the 2 GB cap; storage report still prints after runs.

### 1. Position defense

Added `team_position_defense` (replace policy) and wired as_of-aware position adjustments into projections (`opponent_position_defense_weight: 0.5`).

### 2. Single-game check — 0022400061 NYK @ BOS 2024-10-22

Walk-forward as_of the game date (opening night → prior seasons only). 5000 runs, seed 42:

| | NYK | BOS |
| --- | --- | --- |
| Actual | 109 | 132 |
| Sim mean | 93.8 | 95.7 |
| Home win P | — | 0.551 |

Roster is prior-season (e.g. DiVincenzo/Randle still on NYK projections; several 2024-25 rotation players under-minuted). Side-by-side player table saved under `results/validation/` (gitignored).

### 3. Walk-forward backtest — 2024-25 + 2025-26

`--runs 200 --seed 1`, 2627 games, 51365 player rows.

| Metric | Before tune | After tune |
| --- | --- | --- |
| Brier (home win) | 0.2322 | 0.2315 |
| MAE PTS | 5.75 | 5.74 |
| MAE REB | 2.52 | 2.52 |
| MAE AST | 1.85 | 1.85 |
| MAE 3PM | 0.95 | 0.95 |
| MAE MIN | 5.47 | 5.47 |
| 10th–90th coverage | 0.651 | 0.652 |

Calibration: mid bins slightly under-confident (e.g. pred ~0.45 → actual ~0.53); extremes thin. Artifacts: `results/backtest/before/`, `results/backtest/after/` (gitignored).

### 4. Tuning

Grid on early 2024-25 (`--max-games 24`). Best → `weights [0.40, 0.30, 0.20, 0.10]`, `form_decay 0.04` (written to `config.yaml`). Full-season lift was tiny; blend knobs are not the main error source.

### 5. Biggest weaknesses (fix first)

1. **Minutes / rotation model** — MAE MIN ~5.5; benches often near-zero projected minutes/usage while stars soak minutes. Opening-night and trade/roster lag make this worse.
2. **Too-narrow distributions** — 10–90 coverage ~65–67% vs ~80% target.
3. ~~**Scoring level / pace**~~ — **fixed in Step 1** (see below).
4. **Win-prob calibration** — Brier ~0.23; home favorites under-separated.
5. **Position labels** — source logs are mostly G/F/C/None; PG–C mapping is heuristic.

Storage cap and storage report remain in place.

## Upgrade 1 — Tuning objective: calibration (2026-10-17)

- Metrics: `log_loss_win`, `crps_pts` (empirical CRPS from sim draws), `pit_pts_mean`.
- `backtest/tune.py` `score_report` optimizes log loss + CRPS + coverage≈0.80 + PIT≈0.5 (MAE tiebreaker only).
- Same model as Fix 6; this step adds calibration metrics and retargets the tuner.

| Metric | Fix 6 (no logloss/CRPS) | Upgrade 1 |
| --- | ---: | ---: |
| Brier | 0.222 | 0.222 |
| Log loss | — | **0.634** |
| CRPS PTS | — | **4.38** |
| PIT mean | — | **0.669** (ideal ~0.50) |
| MAE PTS | 5.47 | 5.47 |
| MAE MIN | 5.61 | 5.61 |
| 10–90 coverage | 0.750 | 0.750 |
| Sim / actual PPG | 117.74 / 114.29 | 117.74 / 114.29 |

PIT > 0.5 and coverage ~75% show remaining underdispersion (addressed in U5). Artifacts: `results/backtest/upgrade1_calibration/`.

## Upgrade 2 — Stint-based rotations (2026-10-17)

- New `lineup_stints` table from PlayByPlayV3 (duration, possessions, margin bucket, 5-man lineup).
- Rebuild: `python -m ingest.rebuild_stints --seasons 2023-24,2024-25,2025-26` (~40k stints/season).
- `projections/rotations.py`: depth×margin multipliers + co-appearance; box-score fallback if stints missing.
- Minutes: scale by expected abs margin (close → shorten rotation; blowout → bench).
- Sim: period×margin lineup grid; live score switches buckets late (blowout bench / close Q4 stars).

| Metric | Upgrade 1 | Upgrade 2 |
| --- | ---: | ---: |
| Brier | 0.222 | 0.224 |
| Log loss | **0.634** | 0.639 |
| CRPS PTS | **4.38** | 4.59 |
| PIT mean | 0.669 | 0.680 |
| MAE PTS | **5.47** | 5.74 |
| MAE MIN | **5.61** | 5.94 |
| 10–90 coverage | **0.750** | 0.692 |
| Sim / actual PPG | 117.74 / 114.29 | 117.51 / 114.29 |

Regression vs U1: margin reallocation hurt MIN MAE and narrowed coverage (lineup grid concentrates floor time). Kept as the structural floor for U3–U4 (game-state + RAPM on stints). Artifacts: `results/backtest/upgrade2_stints/`.

## Phase 7 (updated)

- `backtest/metrics.py`: Brier, **log loss**, MAE, **CRPS**, **PIT**, 10th–90th coverage, calibration bins.
- `backtest/tune.py`: calibration objective (log loss + CRPS + coverage/PIT), not MAE-first.

## Fix Step 6 — Minutes MAE + roster team strength (2026-10-17)

Root cause of Fix 3 MIN MAE regression: forcing means/draws onto the 240 simplex redistributed minutes from rotation players to ghost DNPs. Fix:

- Team-aligned recent minutes (inactive ghosts → 0); `normalize_gap_close: 0` keeps Step-2-like means.
- Sim draws no longer hard-normalize to 240 when gap_close=0 (soft clip only).
- Usage blend treats `regression_strength` as pseudo-possessions (stars keep high usage).
- Roster-weighted ORtg/DRtg blended with as-of current-season results (`team_strength_half_life`).
- Multi-stint lineups + per-run FG hot/cold for PTS coverage without inflated minutes noise.

| Metric | Step 5 | Step 6 |
| --- | ---: | ---: |
| Brier | 0.227 | **0.222** |
| MAE PTS | 5.61 | **5.47** |
| MAE REB | 2.45 | **2.35** |
| MAE AST | 1.78 | 1.78 |
| MAE 3PM | 0.96 | **0.94** |
| MAE MIN | 7.16 | **5.61** |
| 10–90 coverage | 0.752 | 0.750 |
| Sim / actual PPG | 117.63 / 114.29 | 117.74 / 114.29 |

Artifacts: `results/backtest/step6_minutes_roster/`.

## Fix Step 5 — Team strength / HCA (2026-10-16)

Prior-season ORtg/DRtg scale FG%/FT% vs league; soft home FG edge (`home_fg_factor` 0.015). No same-season aggregate leakage.

| Metric | Step 3 | Step 5 |
| --- | ---: | ---: |
| Brier | 0.237 | **0.227** |
| MAE PTS | 5.75 | **5.61** |
| MAE REB | 2.51 | **2.45** |
| MAE AST | 1.84 | **1.78** |
| MAE 3PM | 1.00 | **0.96** |
| MAE MIN | 7.14 | 7.16 |
| 10–90 coverage | **0.790** | 0.752 |
| Sim / actual PPG | 117.16 / 114.29 | 117.63 / 114.29 |

Artifacts: `results/backtest/step5_hca/`.

## Fix Step 4 — Variance ~80% (2026-10-16)

No separate code change. Step 3 minutes dispersion delivered 10–90 coverage **0.790** (target ~0.80).

## Fix Step 3 — Minutes → 240 (2026-10-16)

- Team means + sim draws normalize to 240; rotation priors; usage among players above `play_threshold`.
- Tests: `tests/test_minutes.py`.

| Metric | Step 2 | Step 3 |
| --- | ---: | ---: |
| Brier | 0.238 | **0.237** |
| MAE PTS | 6.02 | **5.75** |
| MAE MIN | **5.41** | 7.14 |
| 10–90 coverage | 0.699 | **0.790** |

Artifacts: `results/backtest/step3_minutes/`.

## Fix Step 2 — As-of rosters (2026-10-16)

`team_rosters` (replace policy) stores player stints per season: `from_date` / exclusive `to_date` built from `player_game_logs`, plus optional `CommonTeamRoster` merge for the current season (players signed/traded before their first box score).

- Rebuild: `rebuild_team_rosters(settings, season)` (also called from `_rewrite_derived` / backfill/daily). Historical seasons need no network (`refresh_common=False`).
- Projections: `_roster_for_team` uses active stints with `from_date < as_of` and open/`to_date > as_of`; opening night falls back to prior season open stints; then last-known team from logs only for players with no stint row (stints win so leavers are not re-added on debut day).
- ProjectionCache caches roster Parquet + as_of appearance indexes so walk-forward stays fast.
- Limitation: `CommonTeamRoster` is a live snapshot, not a historical archive — mid-season backtest accuracy comes from game-log stints (trade debut night has a one-day gap by design to avoid leakage). Summer trades before opening night still look like the prior-season roster until the first box score (or a current-season CommonTeamRoster refresh).

Full walk-forward vs Step 1 (`--seasons 2024-2025 --runs 200 --seed 1`):

| Metric | Step 1 | Step 2 |
| --- | ---: | ---: |
| Brier | 0.233 | 0.238 |
| MAE PTS | 5.88 | 6.02 |
| MAE REB | 2.68 | 2.74 |
| MAE AST | 1.77 | 1.82 |
| MAE 3PM | 0.98 | 1.02 |
| MAE MIN | 5.47 | **5.41** |
| 10–90 coverage | 0.669 | **0.699** |
| Sim / actual PPG | 116.95 / 114.29 | 117.05 / 114.29 |
| Sim / actual poss | 98.91 / 98.92 | 98.91 / 98.92 |

Artifacts: `results/backtest/step2_rosters/`.

## Fix Step 1 — Scoring bias (2026-10-16)

Root causes and fixes:

1. **OREB consumed pace trips** — possession endings were ~10% short. Engine now only advances the ending budget on dead balls / makes / FT / DREB; OREB retries without consuming pace.
2. **Rate denominators** — `used = usage * (possessions/2)` because stored possessions are off+def; stl/blk use defensive half; non-steal TOV share for the separate steal path.
3. **FT semantics** — `ft_rate` is FTA/use. Replaced pure FT-trip substitution with shooting fouls / and-ones on FGAs (plus a rare bonus FT trip).
4. Softened stacked zone+position defense weights (`0.35` / `0.15`).

Full walk-forward `--seasons 2024-2025 --runs 200 --seed 1` (2627 games):

| Metric | Before (validation) | After Step 1 |
| --- | ---: | ---: |
| Brier | 0.232 | 0.233 |
| MAE PTS | 5.75 | 5.88 |
| MAE REB | 2.52 | 2.68 |
| MAE AST | 1.85 | 1.77 |
| MAE 3PM | 0.95 | 0.98 |
| MAE MIN | 5.47 | 5.47 |
| 10–90 coverage | 0.651 | 0.669 |
| Sim PPG | ~94–100 | **116.95** |
| Actual PPG | ~114 | **114.29** |
| Sim possessions | — | **98.91** |
| Actual possessions | — | **98.92** |

PPG delta **+2.3%** (target ~1%; was ~−12%). Pace delta **−0.02%**. Artifacts: `results/backtest/step1_scoring/`.

## Commands

```bash
python backfill.py --seasons 2015-2025 --log-file /Users/deanlourcey/nba_archive/backfill.log
python daily.py --log-file /Users/deanlourcey/nba_archive/daily.log
python run.py --date 2026-10-21 --game BOS-NYK --runs 10000
python run.py --date 2026-10-21 --all
python backtest/evaluate.py --seasons 2024-2025 --runs 200
python backtest/tune.py --seasons 2024-25 --max-games 24 --write
```
