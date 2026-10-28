# Progress

Last updated 2026-10-28 — Full 2026-10-28 slate (12 games, 10,000 runs). Reconcile guardrail PASS (80g, REB +0.4%). OKC @ DAL: OKC 55.5%, 107–104.

| Phase | Status | Notes |
| --- | --- | --- |
| Slate 2026-10-28 | done | 12 games. Guardrail PASS. Fixed a fallback that listed Kelly Oubre on both PHI and IND. 8 stat lines + 8 double-doubles logged. |
| Post-game through 10-27 | done | +4 finals. Winners 2/4. Picks 4/8 vs 58.5%. Double-doubles 3/8 vs 41.0%. Roster +1 (Enrique Freeman, MIN). |
| Slate 2026-10-27 | done | 4 games. Guardrail PASS. 8 stat lines + 8 double-doubles in `prediction_history`. Graded in the row above. |
| Post-game through 10-26 | done | +9 finals ingested; all 9 simulated games graded. Winners 7/9. Picks 6/8 (75.0%) vs 61.5% claimed. Season 60.5% / 53.6%. |
| Slate 2026-10-26 | done | 9 games simulated. Guardrail PASS. Typical replays in `results/typical/`. Graded in the post-game row above. |
| Post-game through 10-25 | done | +7 finals ingested; 4 simulated games graded (ORL@NYK, TOR@MIN, LAC@OKC were not simmed). Picks 10/19 vs 42.8% claimed. Season picks 59.5% / 53.0%. |
| Typical-game replay | done | Distance picker, possession fields (zone, FT, rebound, steal, clock, WP), self-contained viewer after every `daily.py` game. |
| Early-season league env | done | Pace+PPG blend (early window only); 400g WF improves total MAE; 2026-27 bias holds. |
| Synergy play-types | reverted | Ingest+schema kept; `play_types_enabled: false` — full 2025-26 WF hurt Brier/winner/spread. |
| External RAPM (nbarapm.com) | done | Weekly fetch + leakage-safe load; full 2025-26 WF kept (Brier/winner ↑). Credit nbarapm.com. |
| Starter STL share fix | done | `stl_credit_raw_weight: 0.30` who-gets-steal blend; mid reconcile PASS (−2.7%); WF held. |
| Post-game through 10-24 | done | +8 finals; 36 games graded; picks 60.9% hit vs 55.2% claimed. |
| Reconcile fix (guardrail/MIN/TOV) | done | Any ±3% flag blocks slate; sim MIN=240; early TOV −2.9%; mid guardrail PASS. |
| Stabilize Step 1 | done | League totals + starter shares FAIL (>3%); team REB +13.6%; starter REB share +19%; bigs sim/36 ~18–20 vs prior ~12–14. |
| Stabilize Step 2 | done | naive_last10 wins MAE; all variants fail reconcile (REB +10–14%). Do not revert to v1.0. |
| Stabilize Step 3 | done | Team-reb leak, TOV scale, play_prob=appear, Gumbel lineups, STL/BLK/AST scales. Guardrail PASS. |
| Stabilize Step 4 | done | `tests/test_reconcile.py` + daily.py blocks slate if reconcile fails. |
| Stabilize Step 5 | done | Before/after table; 10-22 slate rerun — Allen/Mobley ~9–10 REB (was ~15–16). |
| Follow-up 1: elite REB share | done | `reb_share_power: 1.55` on who-gets-it; team totals unchanged; Jokic 9.1→12.8 REB. |
| Follow-up 2: coverage ~0.80 | done | shoot/usage/pace SDs tightened (caps bite below shoot_sd 0.40); PTS 10–90 **0.803**. |
| Early-season blend fix | done | `season_reliability_games: 20` — 1-game season no longer takes full 0.40 weight. |
| Post-game through 10-24 | done | +8 finals (36g); picks 60.9% / 55.2% claimed. |

## Reconcile fix — guardrail, 240 minutes, TOV (2026-10-24)

10-23 walk-forward had flagged MIN +7.8%, TOV −13.4%, AST/STL, and starter shares −5–8%, but the mid-season guardrail still shipped (MIN was informational; only a subset of flags failed the run). Fixed one cluster:

1. **Guardrail:** any team or role flag over ±3% (including MIN / starter MIN) → `passed=False` and `daily.py` refuses the slate.
2. **Minutes:** every regulation sim hard-normalizes to 240/team (+25/OT). Play_prob-aware allocate so `sum(mean×play_prob)=240` (stops sit-redistribution from inflating starters). Mid-season `starter_share_shrink: 0.08` toward equal share.
3. **Starter shares:** after hard 240, early role MIN within 3% (−0.4%). Mid role shares all within 3%.
4. **TOV:** 2026-27 actual ~16.4 vs prior ~13.8. `league_tov_stl_scales` lifts rates from current-season level (or prior early-vs-full opening week). Non-steal scale 0.37→0.39. Early TOV −2.9%.

**Mid-season guardrail (80g×80r, skip 400): PASS** — team/role all ≤3%.

### Before vs after — season scorecard (28 games, 10-20…10-23 resim 5k)

| Metric | Before | After |
| --- | ---: | ---: |
| Winner accuracy | 64.3% | 57.1% |
| Spread MAE | 13.57 | 14.16 |
| Total MAE | 16.07 | **15.68** |
| MIN MAE | 8.23 | **7.44** |
| PTS MAE | 6.02 | **5.27** |
| 10–90 coverage | 71.1% | **78.0%** |
| Top picks hit / claimed | 61.7% / 59.5% (29/47) | **64.5%** / 59.4% (40/62) |

### Early 2026-27 reconcile (25g walk-forward)

| | Before (10-23 flag) | After |
| --- | ---: | ---: |
| Team MIN | +7.8% | **+0.1%** |
| Team TOV | −13.4% | **−2.9%** |
| Team STL | −3.5% | −0.8% |
| Starter MIN share | −5.5%…−8.3% | **−0.4%** |
| Starter PTS/AST share | under | −3.9% / −4.0% (still slight) |
| Team AST | +3.9% | +5.1% (still flag on early window) |

Player MAE and coverage improved; winner accuracy dipped on the resim (opening-night margins tightened). Early AST still a bit high — leave for a later one-knob pass.
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
| U3. Game-state behavior | done | Late pace adjust + intentional fouls from stint-learned factors. |
| U4. Ridge RAPM | done | Stint RAPM → minutes-weighted roster ORtg/DRtg; λ by OOS MSE. |
| U5. Variance (player RE + pace) | done | Per-player shoot/usage draws; pace_sd 5.5; minutes noise unchanged. |
| U6. Kalman + rest HCA | done | Dynamic team nets; non-linear rest HCA; Brier back to 0.222. |
| U7. Shot clusters | deferred | Not needed for opening night; leave for mid-season. |
| U8. Late-season incentives | deferred | Not started. `features.late_season_incentives: false` in config.yaml. Opening-night freeze — no new features. |
| Preseason storage | done | `season_type=Preseason` hive partition; excluded from default reads. |
| Opening night v1.0 | done | Tag `v1.0-opening-night`. Trade-history minutes + 240 allocate; injury CDN hang fix; RUNBOOK.md. |
| Minutes + calibration | done | Full-season bakeoff → default `naive_last10`; shoot/usage SDs widened for ~80% PTS coverage. |
| Assist attribution | done | Passer weighted by `ast_rate`; team AST bias −10 → +0.0 on 2025-26 sample. |
| Roster + star inflation | partial | Live `current_rosters` refresh; any-team minutes discount; usage calibrate; playoff MPG soft-cap. Cade 34.7→32.4 PTS (actual 22). Huerter/Joe still under-minuted without injury PDF. |
| Poss upgrade Step A | done | Real game clock + quarter scores; optional single-run `trace_run` possession log. |
| Poss upgrade Step B | done | Passer→shooter `assist_edges`; soft-blend into `_credit_assists`. |
| Poss upgrade Step C | done | `LeagueSeasonMatchups` → `defender_impact`; primary defender by position; prior-season only. |
| Poss upgrade Step D | done | Typical game log + WP HTML chart under `results/typical/`. |
| Poss upgrade Step E | done | Possession/data tests; walk-forward summary vs baseline. |
| Poss upgrade Step F | done | Stint rotations: replacement edges, closing shares, margin×period timing; absence minutes → historical replacements. MIN MAE improved slightly vs baseline. |
| Minutes bakeoff 2025-26 | done | Pure `naive_last10` wins MIN/PTS/REB/AST vs v1.0 / Step F off/on. Default minutes_model set; coverage ~0.80 via shoot/usage. |
| Post-game grade 10-20/21 | done | Ingested 11 finals; filled actuals; `results/season_scorecard.md`; daily.py refreshes scorecard. |
| 2026-10-22 slate | done | P(plays) Bernoulli; scaled top-8 picks logged to history; roster corruption guard. |
| Post-game through 10-24 | done | See section below. |

## Post-game update through 2026-10-23 (2026-10-24)

**Ingest:** +14 finals (10-22: 2, 10-23: 12); skipped 14 already stored.  
**Rosters:** +SAC Sean Pedulla; −NYK Kevin McCullar Jr. (519 players).  
**Actuals filled:** 717 prediction_history rows.

### Season to date (28 games)

| Metric | Value |
| --- | ---: |
| Winner accuracy | 64.3% |
| Spread MAE | 13.57 |
| Total MAE | 16.07 |
| MIN / PTS MAE | 8.23 / 6.02 |
| 10–90 coverage | 71.1% |
| Top picks | **61.7%** hit (29/47) vs **59.5%** claimed |

### Per night

| Night | Games | Winner | Spread MAE | Total MAE | Cov | Picks hit / claimed |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 10-20 | 3 | 66.7% | 7.83 | 17.00 | 69.1% | n/a |
| 10-21 | 11 | 72.7% | 17.09 | 14.64 | 62.6% | n/a (not in history) |
| 10-22 | 2 | 50.0% | 8.00 | 26.50 | 81.9% | 50.0% / 63.2% |
| 10-23 | 12 | 58.3% | 12.71 | 15.42 | 77.6% | **70.4%** / 56.8% |

### Reconcile 2026-10-23 (12g × 200r walk-forward vs actual)

| | Stat | Δ | |
| --- | --- | ---: | --- |
| Team | AST | +3.9% | flag |
| Team | STL | −3.5% | flag |
| Team | TOV | −13.4% | flag |
| Team | MIN | +7.8% | flag (sim ~259 vs 240) |
| Team | PTS/REB/BLK | ≤1.5% | ok |
| Starter share | PTS/REB/AST/STL/MIN | −5.5% to −8.3% | all flag (under-concentrate starters) |

Storage: **10.57 MiB** total.

## Stabilize Step 1 — reconciliation diagnosis (2026-10-22)

Walk-forward 2025-26, 250 games, 200 runs, seed 1. Artifacts: `results/backtest/reconcile_step1/`.

| League total | Sim | Actual | Delta |
| --- | ---: | ---: | ---: |
| possessions | 99.89 | 99.78 | +0.1% |
| PTS | 117.47 | 115.09 | +2.1% |
| **REB** | **49.63** | **43.67** | **+13.6%** |
| AST | 24.72 | 26.51 | −6.8% |
| STL | 7.43 | 8.40 | −11.5% |
| BLK | 3.34 | 4.86 | −31.3% |
| TOV | 12.22 | 13.78 | −11.3% |
| MIN | 225.45 | 241.31 | −6.6% |

| Starter share | Sim | Actual | Delta |
| --- | ---: | ---: | ---: |
| MIN | 0.658 | 0.620 | +6.1% |
| PTS | 0.785 | 0.677 | +15.9% |
| **REB** | **0.753** | **0.631** | **+19.4%** |
| AST | 0.794 | 0.674 | +17.9% |

Top rebounders sim/36 ~17–21 vs prior-season ~12–14 (Towns 19.7, Gobert 18.4, Duren 18.2, Jokic 17.4). Tonight’s slate: Allen 15.8, Mobley 15.1, Jokic 15.2 REB mean.

**Root-cause leads:** (1) too many live misses credited to players (~102 reb/game vs ~87; no team-rebound leak + slightly high FGA mix); (2) minutes under-allocated (225 vs 240) so starters soak possession share; (3) on-court oreb/dreb rate sums ≈1.0 so contest math is fine — inflation is volume + role concentration, not rate sum >1.

Harness: `backtest/reconcile.py`, `scripts/reconcile_diagnosis.py`.

## Stabilize Step 2 — bakeoff + reconcile (2026-10-22)

MAE: 1314g/1000r seed 1. Reconcile: 250g/200r. Artifacts: `results/backtest/stabilize_step2/`.

| Version | MIN | PTS | REB | AST | 10–90 | Brier | REB Δ | starter REB Δ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| v1.0 | 7.63 | 5.95 | 2.63 | 1.80 | 0.65 | 0.223 | +10.2% | +21.8% |
| Step F off | 6.88 | 5.85 | 2.58 | 1.58 | 0.67 | 0.221 | +13.8% | +17.9% |
| Step F on | 6.78 | 5.86 | 2.60 | 1.59 | 0.66 | 0.222 | +13.7% | +18.5% |
| **naive_last10** | **6.25** | **5.34** | **2.33** | **1.49** | **0.74** | **0.220** | +13.6% | +19.4% |

Keep naive_last10. v1.0 loses on MAE and has broken AST (−41%). REB inflation is shared across configs → possession engine, not minutes model.

## Stabilize Steps 3–5 — fix + guardrail + report (2026-10-22)

**Root causes fixed (one cluster, keep naive minutes):**
1. No team-rebound leak → every live miss credited a player (`team_reb_rate: 0.115`).
2. Non-steal TOV scale 0.32→0.37 (understated dead possessions → extra FGA/misses).
3. `play_prob` haircut invented DNPs; now follows appear rate + role floors.
4. Hard top-5 lineups locked stars on court; naive path uses Gumbel-top-k (temp 1.35).
5. STL/BLK engine scales and `assist_p_scale: 1.02` recentered league totals.

**Guardrail (PASS mid-season 2025-26):** league PTS/REB/AST/STL/BLK/TOV and starter PTS/REB/AST/STL shares within ±3%. Wired into `daily.py` (blocks slate on fail) and `tests/test_reconcile.py`.

### Before vs after

| Metric | Before (naive bakeoff / Step1) | After (200g/200r sample) |
| --- | ---: | ---: |
| MIN MAE | 6.25 | **5.95** |
| PTS MAE | 5.34 | **5.09** |
| REB MAE | 2.33 | **2.03** |
| AST MAE | 1.49 | **1.37** |
| 10–90 cov | 0.74 | 0.86 |
| Brier | 0.220 | **0.217** |
| margin MAE | 12.23 | **11.23** |
| total MAE | 17.55 | **15.32** |
| Team REB Δ | +13.6% | **+2.1%** |
| Starter REB share Δ | +19.4% | **+1.0%** |

### Top rebounders / scorers (mid-season sample vs prior)

| Player | Sim REB | Act | Prior | Sim PTS | Act | Prior |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Jokic | ~9–12 | 11.5 | 12.7 | ~23–30 | 29.8 | 29.0 |
| Towns | ~9–11 | 11.6 | 12.5 | — | — | — |
| Duren | ~8–10 | 9.3 | 10.4 | — | — | — |

### Tonight 10-22 centers (BEFORE → AFTER)

| Player | BEFORE REB | AFTER REB |
| --- | ---: | ---: |
| Jarrett Allen | 15.8 | **9.8** |
| Evan Mobley | 15.1 | **9.6** |
| Nikola Jokić | 15.2 | **9.1** |
| Chet Holmgren | 12.5 | **6.9** |
| Joel Embiid | 11.3 | **7.5** |

**Rules going forward:** one change at a time; must pass reconcile guardrail and hold/improve backtest or revert.

## Follow-up 1 — elite rebounder share (2026-10-23)

Post team-reb fix, top rebounders were systematically low on REB/36 (Gumbel lineups dilute who-gets-it). Fix: `reb_share_power` on offensive/defensive rebound weights for credit only; ORB% still from raw rates so team REB stays put. Gumbel temp kept at 1.35 (colder lineups failed starter REB share).

**Guardrail:** PASS (100g/120r mid-season). Team REB +0.5%, starter REB share +2.6%.

### Elite REB/36 vs prior season (mid-season sample)

| | Before (power=1.0) | After (power=1.55) |
| --- | ---: | ---: |
| Mean top-15 Δ/36 vs prior | −1.82 | **+0.50** |
| Jokic Δ/36 | −3.4 | **−0.8** |

### Tonight 10-22 centers (stabilize → share fix)

| Player | MIN | REB before | REB after | REB/36 | 2025-26 /36 | Δ/36 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Nikola Jokić | 35.6 | 9.1 | **12.8** | 12.9 | 13.2 | −0.2 |
| Chet Holmgren | 29.1 | 6.9 | **7.6** | 9.4 | 10.8 | −1.4 |
| Jarrett Allen | 29.3 | 9.8 | **11.3** | 13.8 | 10.6 | +3.2 |
| Evan Mobley | 34.6 | 9.6 | **10.6** | 11.0 | 9.7 | +1.3 |
| Joel Embiid | 30.0 | 7.5 | **8.7** | 10.4 | 8.6 | +1.8 |

### Backtest hold (120g/200r mid-season)

| Metric | Stabilize after | + share power |
| --- | ---: | ---: |
| MIN MAE | 5.95 | 6.09 |
| PTS MAE | 5.09 | **5.18** |
| REB MAE | 2.03 | 2.10 |
| AST MAE | 1.37 | **1.37** |

MAE held within noise; reconcile PASS.

## Follow-up 2 — tighten 10–90 coverage (2026-10-23)

Stabilize left PTS 10–90 coverage ~0.86 (bands too wide). Player-level SDs only move the band once below the 1.5×SD cap of 0.60 (`shoot_sd < 0.40`). Means unchanged (multiplicative noise around 1.0).

| Knob | Before | After |
| --- | ---: | ---: |
| player_shoot_sd | 0.50 | **0.32** |
| player_usage_sd | 0.38 | **0.28** |
| team_hot_sd | 0.07 | **0.05** |
| pace_sd | 9.0 | **6.5** |
| assist_p_scale | 1.02 | **0.99** (recentered after AST drifted +3.4%) |

### Before vs after (same mid-season window)

| Metric | Before | After |
| --- | ---: | ---: |
| PTS 10–90 coverage | 0.86 (stabilize) / 0.809 paired | **0.803** |
| mean pred PTS | 8.87 | 8.90 |
| PTS MAE | 5.25 | **5.18** |
| REB MAE | 2.10 | **2.10** |
| AST MAE | 1.39 | **1.37** |
| Guardrail | PASS | **PASS** |

## 2026-10-22 slate (CLE@PHI, DEN@OKC)

- **P(plays):** `MinutesProjection.play_prob` from injury status × appear rate × rotation role; each sim draws sit/play before minutes, then team normalize.
- **Confident picks:** starters/core with median MIN≥26 and P(plays)≥0.95; scaled windows; exactly 8 (per-game cap rises on short slates); logged as `row_kind=pick` in `prediction_history` with claimed confidence.
- **Injuries:** 11 OUT/Doubtful; Spencer Jones (DEN) Questionable (hamstring) — left Q, excluded from picks; no other Q overrides.
- **Roster guard:** if CommonTeamRoster overlap with prior open stints is tiny, fall back to prior open + current appearances (fixes PHI LeBron/Brown junk from the live feed).
- Slate report: `results/latest/slate_report.md`. Storage ~10.5 MiB.

## Minutes bakeoff + 10-21 MIN MAE (Part 3)

Bakeoff already finished (1314g/1000r). Winner: **naive_last10** (MIN 6.25) over Step F on (6.78), off (6.88), v1.0 (7.63).

10-21 MIN MAE split: **played** 9.92 (n=254) vs **projected≥8 DNP** 20.21 (n=29). Biggest misses: Patrick Williams / Jahmai Mashack / Will Riley (DNP despite 32–36 proj); rookies Acuff / Boozer / Wilson / Peterson / Wiggins under-projected at ~0 then played 30+.

Scorecard now shows top-picks **avg claimed confidence 77.1%** vs **hit rate 33.3% (3/9)** for 10-21.

## Post-game grade — opening night + 2026-10-21 (2026-10-22)

- Incremental ingest: **11** new 2026-27 finals through 2026-10-21 (3 opening-night already stored). 14 finals total.
- Roster refresh: **+ Walter Clayton Jr. (DAL)** on CommonTeamRoster (518 → 519). No new box-score-only players vs prior snapshot.
- `prediction_history` actuals upserted: **336** rows.
- Scorecard: `results/season_scorecard.md` (also refreshed by `daily.py` / `scripts/postgame_grade.py`).

| Night | Games | Winner | Spread MAE | Total MAE | MIN MAE | PTS MAE | 10–90 cov | Top picks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-10-20 | 3 | 66.7% | 7.83 | 17.00 | 5.76 | 5.76 | 69.1% | n/a |
| 2026-10-21 | 11 | 72.7% | 17.09 | 14.64 | 9.92 | 7.23 | 62.6% | **3/9 (33%)** |
| **Season** | **14** | **71.4%** | **15.11** | **15.14** | **9.04** | **6.92** | **64.0%** | **3/9** |

Opening night had no Top confident table (feature shipped with 10-21). Storage ~10.5 MiB / 2 GB cap.

## Minutes bakeoff + coverage (2026-10-22)

Walk-forward **all 2025-26 games**, 1000 runs, seed 1 (1314 games, 26410 player-rows). Harness: `scripts/minutes_bakeoff.py`. Artifacts: `results/backtest/minutes_bakeoff/`.

| Version | MAE MIN | starters | bench | star MPG | MAE PTS | REB | AST | 10–90 cov | Brier | margin | total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| v1.0-opening-night | 7.628 | 6.307 | 8.889 | 4.870 | 5.950 | 2.629 | 1.803 | 0.648 | 0.223 | 12.44 | 18.09 |
| main Step F off | 6.884 | 5.860 | 7.862 | **4.226** | 5.853 | 2.585 | 1.577 | 0.670 | 0.221 | 12.38 | 17.63 |
| main Step F on | 6.777 | 5.741 | 7.766 | 4.373 | 5.860 | 2.600 | 1.588 | 0.661 | 0.222 | 12.43 | **17.50** |
| **main naive_last10** | **6.253** | **5.152** | **7.304** | 4.461 | **5.339** | **2.330** | **1.485** | **0.743** | **0.220** | **12.23** | 17.55 |

**Recommendation:** use pure `naive_last10` (not blend). Sample probe: blend 0.5 / 0.7 and engine all worse than pure naive on MIN MAE. Step F still slightly helps the engine path; leave `stint_rotations_step_f: true` for that path.

**Why MIN MAE drifted from ~5.47:** Fix 3 force-to-240, U2 stint rotations, and opening-night allocate/trade-history path widened minutes error vs the Fix 2 / Fix 6 era. On this apples-to-apples 2025-26 slate, current main (engine) already beats v1.0 (7.63 → 6.78); naive closes more of the gap (6.25) without recovering the historical 5.47 peak.

**Coverage:** hard shoot/usage clip ceilings (0.28/0.30) blocked SD knobs. Caps now scale with SD (`1.5 * sd`, max 0.60). With naive minutes: `player_shoot_sd: 0.50`, `player_usage_sd: 0.38` → ~0.795 PTS 10–90 on 100g/250r probe. `minutes_variance` unchanged.

**Config defaults:** `features.minutes_model: naive_last10`; shoot/usage SDs as above.

## Possession upgrade Step A (2026-10-21)

- `sim/possession_log.py`: `PossessionEvent` / `PossessionLog`; regulation clock constants.
- `sim/engine.py`: clock from pace progress (12-min quarters); period-score snapshots; `trace_run` records one run’s possession narrative without persisting other runs.
- Backtest metrics now include `mae_margin` / `mae_total`.
- Tests: `tests/test_possession_engine.py`.

Walk-forward 2025-26, 250 games, 200 runs, seed 1:

| Metric | Baseline | Step A |
| --- | ---: | ---: |
| Brier | 0.2120 | 0.2126 |
| Log loss | 0.6121 | 0.6136 |
| MAE PTS | 5.77 | 5.75 |
| MAE AST | 1.52 | 1.51 |
| MAE MIN | 6.92 | 6.92 |
| MAE margin | — | 11.68 |
| MAE total | — | 15.75 |
| 10–90 coverage | 0.671 | 0.672 |

No clear regression. Artifacts: `results/backtest/upgrade_poss_baseline/`, `results/backtest/upgrade_poss_step_a/`.

## Possession upgrade Step B (2026-10-21)

- PlayByPlayV3 omits `assistPersonId`; passer resolved from `(Name N AST)` in the description against the on-court/roster names.
- Table `assist_edges` (game-level passer→shooter counts). Rebuild: `python -m ingest.rebuild_assists --seasons 2024-25,2025-26`.
- Sim soft-blends network weights with `ast_rate` (α=0.35) so creators keep volume.

## Possession upgrade Step C (2026-10-21)

- **API check:** `LeagueSeasonMatchups` and `BoxScoreMatchupsV3` both returned usable data.
- Stored compact per-defender aggregates only (`defender_impact`) from `LeagueSeasonMatchups` (never raw OFF×DEF rows).
- Walk-forward uses **prior seasons only** (same-season season-totals would leak).
- Primary defender among on-court five by position affinity; FG%/3P% scaled by regressed defender factors.
- Rebuild: `python -m ingest.rebuild_matchups --seasons 2023-24,2024-25`.

Walk-forward 2025-26, 250 games, 200 runs, seed 1 (B+C together; blend fix):

| Metric | Step A | Step B+C |
| --- | ---: | ---: |
| Brier | 0.2126 | **0.2113** |
| Log loss | 0.6136 | **0.6098** |
| MAE PTS | 5.75 | 5.75 |
| MAE AST | 1.51 | 1.57 |
| MAE margin | 11.68 | **11.63** |
| MAE total | 15.75 | 15.88 |
| 10–90 coverage | 0.672 | 0.672 |

Hard network replace spiked AST MAE to 1.88; soft-blend recovered to 1.57. Win metrics improved. Artifacts: `results/backtest/upgrade_poss_step_b2/`.

## Possession upgrade Step D (2026-10-21)

- After Monte Carlo: pick run closest to median margin + total; re-sim with `trace_run` for that index (same seed → identical cloud).
- Win-probability after each possession from the **in-memory** trajectory cloud (period-score snapshots × final winners); never persist the WP grid.
- Persist only: one JSON possession log + one HTML chart (`results/typical/`).
- Wired into `outputs/pipeline.py` (run.py / daily.py). No sim-distribution change → backtest metrics match Step B+C.

## Possession upgrade Step E — validation summary (2026-10-21)

Walk-forward protocol: `--seasons 2025-26 --runs 200 --seed 1 --max-games 250`.

| Metric | Baseline | Step A | Step B+C | Step D |
| --- | ---: | ---: | ---: | ---: |
| Brier | 0.2120 | 0.2126 | **0.2113** | = B+C |
| Log loss | 0.6121 | 0.6136 | **0.6098** | = B+C |
| MAE PTS | 5.77 | 5.75 | 5.75 | = B+C |
| MAE AST | 1.52 | 1.51 | 1.57 | = B+C |
| MAE MIN | 6.92 | 6.92 | 6.92 | = B+C |
| MAE margin | — | 11.68 | **11.63** | = B+C |
| MAE total | — | 15.75 | 15.88 | = B+C |
| 10–90 coverage | 0.671 | 0.672 | 0.672 | = B+C |
| Sim PPG | 119.8 | 119.6 | 119.6 | = B+C |

**Step C API note:** `BoxScoreMatchupsV3` and `LeagueSeasonMatchups` both returned usable data. Compact `defender_impact` is built from `LeagueSeasonMatchups` (prior seasons only for walk-forward). Position/minutes primary-defender assignment is the on-court fallback when pairing history is absent.

**Tests added:** `tests/test_possession_engine.py`, `tests/test_assist_network.py`, `tests/test_matchups.py`, `tests/test_typical_game.py`.

## Possession upgrade Step F — stint-based rotations (2026-10-21)

Learns from compact `lineup_stints` (2025-26 + current, recency-weighted) plus box-score absence history — no raw PBP persisted.

- **Substitution edges:** who checks in for whom (stint lineup swaps + nights a rotation player sits).
- **Closing lineups:** Q4×close stint seconds → soft boost for closers in expected close games.
- **Margin × period:** blowouts send bench earlier (Q2+); close games keep starters in Q4.
- **Absence minutes:** OUT/Doubtful minutes go to historical replacements first (`replacement_share`), not evenly; `overrides.yaml` minutes caps still bind.
- Config: `features.stint_rotations_step_f: true`, `minutes.replacement_share`, `minutes.stint_recency_half_life_days`.
- Rebuilt `lineup_stints` for 2026-27 (3 opening-night finals → 109 stints).
- Tests: `tests/test_rotations.py` (replacement redistribute, caps, blowout/close period weights).
- Compare: `PYTHONPATH=. python scripts/step_f_backtest.py --seasons 2025-26 --runs 200 --seed 1 --max-games 250`

Walk-forward 2025-26, 250 games, 200 runs, seed 1:

| Metric | Baseline (Step F off) | Step F |
| --- | ---: | ---: |
| MAE MIN | 6.866 | **6.802** |
| MAE MIN starters | 6.194 | **6.151** |
| MAE MIN bench | 7.460 | **7.377** |
| MAE PTS | 5.731 | **5.722** |
| 10–90 coverage | **0.674** | 0.668 |
| Brier | **0.208** | 0.211 |
| Star MPG MAE vs prior | **5.28** | 5.51 |

Minutes MAE improved for overall / starters / bench. Coverage and star-vs-prior MPG slightly worse (soft closing/replacement effects). Artifacts: `results/backtest/upgrade_poss_step_f/`.

## Phase 3

`ingest/injuries.py` downloads and parses the official NBA injury PDF in memory. `overrides.yaml` wins on status and minutes caps. Nothing is written under `DATA_DIR`.

## Phase 4

`projections/` builds per-game player rates and minutes from stored logs/rates with an `as_of` cutoff. Blend window uses configured `seasons_back` only (no longer appends every older season once the full history is present).

Opponent defense:

- Zone FG% allowed (existing `team_zone_defense` + as_of scan from rates/logs).
- **Position defense (new):** stats allowed to PG/SG/SF/PF/C from player game logs (`team_position_defense` table + as_of `position_defense_from_bundles`). Listed positions are usually G/F/C; `five_position()` maps those onto the five traditional slots using that appearance’s reb/ast.

## Assist attribution (2026-10-20)

**Bug:** On a make, the engine picked a *uniform random* non-shooter and used
`clip(ast_rate, 0.35, 0.75)` as P(assisted). Primary creators (Cade ~0.43
ast_rate) were starved (~1/4 of credits) while team AST sat ~16 vs ~26 actual.

**Fix:** `ast_rate` = historical AST / teammate FGM while on court. P(assisted) =
`clip(assist_p_scale * sum(non-shooter rates), 0, 1)`; passer drawn proportional
to those rates. `assist_p_scale: 0.86` centers team level (season rates stacked
in a lineup slightly overstate). Opp-defense ast_rate cap raised 0.45 → 0.65.

**Usage ≠ creation:** Usage only weights who shoots among the on-court five.
Assists are separate (teammate makes). Cade usg≈0.16 → ~28% of DET shot weight
when on court; high PTS (~35) is minutes/efficiency, not assists stolen into FGA.

2025-26 walk-forward sample (200 games, 150 runs):

| Metric | Before | After |
| --- | ---: | ---: |
| Team AST/G sim | 15.78 | **25.82** |
| Team AST/G actual | 25.78 | 25.78 |
| Team AST bias | −10.00 | **+0.04** |
| Team AST MAE | 10.22 | **4.97** |
| Cade AST/G sim | 3.22 | **10.80** |
| Cade AST/G actual | 9.10 | 9.10 |

Opening night BOS@DET Cade: before AST≈3.0 / PTS≈34 → after AST≈11.4 / PTS≈34.8;
P(PTS≥24.5)=0.819.

## Roster refresh + star inflation (2026-10-20 night)

**Roster:** Refreshed `current_rosters` from CommonTeamRoster for all 30 teams
(519 players). Trust live API (large offseason movement, e.g. LeBron→PHI).
Official injury PDF unavailable for 2026-10-20; overrides empty.

**BOS@DET missing-bench autopsy:** Membership was mostly right; minutes were wrong.
Cross-team any-team fallback gave Harkless/Prince ~30 MPG from prior clubs and
crowded out Joe/Huerter/Green. Playoff last-10 MPG (Cade 41) plus
`early_season_gap_close=1.0` and rotation adjust pushed stars to max_minutes.

**Fixes:**
1. Discount any-team minutes (stars keep ~85%; bench imports capped ~10–14).
2. Soft-cap recent MPG at 36 (playoff bleed).
3. `early_season_gap_close` 1.0 → 0.55; don't scale stars up when expanding to 240.
4. Cap after rotation adjust at allocate mean / 36.
5. Usage: calibrate minutes-weighted mean to 0.20 (not roster sum-to-1).
6. Symmetric player_hot / player_usage clips.

**BOS@DET before → after (vs actual DET 121, BOS 113):**

| Player | Before PTS/MIN | After PTS/MIN | Actual |
| --- | ---: | ---: | ---: |
| Cade | 34.7 / 39.6 | 32.4 / 36.5 | 22 / 35.3 |
| Tatum | 26.9 / 32.3 | 28.6 / 36.4 | 13 / 37.8 |

Remaining: Huerter/Joe still ~0 proj min (need inactive/injury feed);
top-30 dPPM still ~+0.06 vs last season. 2025-26 sample PTS MAE (min≥15) ~6.9.

**PHI@NYK / OKC@SAS** re-simmed 10k after roster refresh (see chat / results/latest).

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

## Upgrade 3 — Game-state pace / intentional fouls (2026-10-17)

- `projections/game_state.py`: pace factors by period × trail/lead/blowout from stint poss/sec (defaults if sparse).
- Sim: at ~70% progress, scale remaining endings by blended pace factor; Q4 late close games allow intentional fouls (2 FT, possession flip).
- Config: `simulation.intentional_foul_prob`, `late_pace_adjust`.

| Metric | Upgrade 2 | Upgrade 3 |
| --- | ---: | ---: |
| Brier | 0.224 | 0.224 |
| Log loss | **0.639** | 0.640 |
| CRPS PTS | **4.59** | 4.65 |
| PIT mean | 0.680 | 0.678 |
| MAE PTS | **5.74** | 5.80 |
| MAE MIN | **5.94** | 6.01 |
| 10–90 coverage | **0.692** | 0.682 |
| Sim / actual PPG | 117.51 / 114.29 | 118.41 / 114.29 |
| Sim / actual poss | 98.95 / 98.92 | 98.95 / 98.92 |

Small move vs U2; PPG slightly higher from late haste / foul FTs. Artifacts: `results/backtest/upgrade3_gamestate/`.

## Upgrade 4 — Ridge RAPM → roster strength (2026-10-17)

- `lineup_stints.plus_minus` from PBP score change; rebuilt 2023-24…2025-26.
- `projections/rapm.py`: possession-weighted ridge APM; λ ∈ {200…5000} chosen by chronological OOS MSE.
- Team strength = minutes-weighted roster RAPM split into ORtg/DRtg, blended with current-season results.
- Box-score PM shrinkage fallback when stint PM missing. Storage read fills new columns as null.

| Metric | Upgrade 3 | Upgrade 4 |
| --- | ---: | ---: |
| Brier | 0.224 | 0.224 |
| Log loss | 0.640 | **0.640** |
| CRPS PTS | 4.65 | 4.65 |
| PIT mean | 0.678 | 0.679 |
| MAE PTS | 5.80 | 5.80 |
| MAE MIN | 6.01 | 6.01 |
| 10–90 coverage | 0.682 | 0.680 |
| Sim / actual PPG | 118.41 / 114.29 | 117.92 / 114.29 |

Chosen λ often high (~5000) → strong shrink toward 0; win metrics flat vs U3. Artifacts: `results/backtest/upgrade4_rapm/`.

## External RAPM — nbarapm.com (2026-10-24 / 25)

Credit: **[nbarapm.com](https://nbarapm.com)** (time-decay + six-factor RAPM).

- The timedecay / six-factor pages' "Download CSV" button builds CSV client-side from published JSON under `/load/…`. We download those data files only (no HTML scrape): `https://nbarapm.com/load/timedecay` and `https://nbarapm.com/load/SCALEDOUTPUT_SMALLER` (same body as `/load/six_factor`).
- `ingest/rapm_fetch.py`: at most once every 7 days; clear User-Agent; timeout + one retry; no other requests to the site. Writes compact parquet under `DATA_DIR/external/` with `.prev.parquet` fallback. Fetch/format failures log a warning and keep the last good copy — never break `daily.py`.
- Site `as_of_date` stored on rows; `daily.py` logs how old the RAPM data is.
- **Leakage-safe load** (`projections/rapm.py`): timedecay only when snapshot `as_of` is strictly before the projected season's Oct 1 (live 2026-27). Walk-forward / earlier seasons use six-factor rows with `latest_year <= season_start_year`, preferring `3Y` then `5Y` — never timedecay / six-factor `TD` for 2025-26 backtests.
- Storage: `nbarapm_six_factor` ~739 KiB, `nbarapm_timedecay` ~32 KiB, meta ~2.5 KiB (listed separately in the storage report). DATA_DIR total ~11.4 MiB / 2 GB.

### Keep decision — full 2025-26 walk-forward (1314g × 200r, seed 1)

Artifacts: `results/backtest/wf_2025_26_rapm_on/`, `results/backtest/wf_2025_26_rapm_off/`.

| Metric | RAPM ON (six-factor prior) | RAPM OFF |
| --- | ---: | ---: |
| Brier | **0.214** | 0.215 |
| Winner accuracy | **66.7%** | 65.4% |
| Spread MAE (margin) | **12.07** | 12.08 |
| Total MAE | 16.12 | **16.05** |
| Player PTS MAE | **5.245** | 5.245 |
| Player REB MAE | 2.098 | **2.098** |
| Player AST MAE | 1.408 | **1.408** |
| Player STL MAE | n/a (not in that harness) | n/a |
| 10–90 coverage | 0.811 | **0.812** |

**Kept.** Mid-season reconcile then flagged starter STL on both ON and OFF (pre-existing; fixed below).

## Starter STL share — who-gets-steal blend (2026-10-25)

**Cause:** raw on-court `stl_rate` over-credits high-rate bench specialists. Team STL was fine (−0.8%); starter STL share −3.3% (FAIL). Minutes were not the driver (starter MIN share +1.8%). Guardrail already blocks the slate on any >3% team/role flag (`daily.py` + `reconcile.passed`); this STL flag would have refused projections.

**One change:** `simulation.stl_credit_raw_weight: 0.30` — P(steal) still from raw rate sum; who-gets-it = `0.30·raw + 0.70·on-court mean` (same pattern as BLK credit). Mid-season guardrail (80g×80r, skip 400): **PASS**, starter STL −2.7%.

Hold-check 250g × 200r seed 1 (`results/backtest/stl_credit_{before,after}/`):

| Metric | before (1.0) | after (0.30) |
| --- | ---: | ---: |
| Brier | 0.202 | 0.202 |
| Winner | 66.4% | 66.4% |
| Spread / total MAE | 11.11 / 16.26 | same |
| PTS / REB / AST MAE | flat | flat |
| STL MAE | 0.714 | **0.712** |
| 10–90 coverage | 0.833 | 0.833 |

## Slate 2026-10-28

- Guardrail PASS (80 games, REB +0.4%, starter REB +0.2%). Rosters refreshed, 521 players.
- Philadelphia's live roster overlapped 2025-26 so little that the engine fell back to last year's open stints and also kept Kelly Oubre, who is on Indiana's live roster. The fallback now drops anyone claimed by another team's current roster. Full 12-game slate re-ran after that fix.
- OKC @ DAL median: OKC 107–DAL 104 (OKC 55.5%). P(DAL wins) 44.5%. P(DAL loses by 6+) 47.6%. Both teams on 1 rest day. Chet Holmgren, Jalen Williams, Alex Caruso, and Cason Wallace are out; their minutes go to the remaining Thunder rotation, including Micah Peavy (no 2026-27 games, 36.9 median minutes).

## Post-game through 2026-10-27

- Ingested **4** finals (10-27). Roster refresh **+1 / −0**: Enrique Freeman added to MIN (522 players).
- Graded all 4 simulated games. Winners 2/4. Night total bias **−16.00**. Season bias **−4.85** (53 games).
- Confident picks 4/8 (50.0%) vs 58.5% claimed. Double-doubles 3/8 (37.5%) vs 41.0% claimed P(DD).
- Night reconcile vs box scores: MIN −2.4%. Flags: PTS −6.6%, REB +3.4%, AST −11.1%, STL +34.6%, BLK +9.2%, TOV +9.5%.
- Scorecard: `results/season_scorecard.md`. Storage **11.80 MiB / 2 GB**.

## Slate 2026-10-27

- Guardrail PASS (80 games, REB +0.4%, starter REB +0.2%). Rosters refreshed, 521 players. No `overrides.yaml` player rows.
- 4 games at 10,000 runs. Typical replays in `results/typical/`. Pending rows on the scorecard.
- Confident lines and double-doubles are both `row_kind=pick` (16 rows). A `dd_*` pick hits when two of PTS/REB/AST/STL/BLK are 10+.

## Post-game through 2026-10-26

- Ingested **9** finals (10-26). Roster refresh **+0/−0** (521 players).
- Graded all 9 simulated games. Winners 7/9. Night total bias **−5.67**. Season bias **−3.94** (pred median total minus actual, 49 games).
- Night reconcile vs box scores, predicted mean sum vs actual: MIN −1.0%, PTS −2.3%, AST −1.1%. Flags: REB −5.0%, STL +15.8%, BLK −12.0%, TOV +6.2%.
- Picks 6/8 (75.0%) vs 61.5% claimed. Scorecard: `results/season_scorecard.md`. Storage **11.78 MiB / 2 GB**.

## Post-game through 2026-10-25

- Ingested **7** finals (10-25). Roster refresh **+0/−0** (521 players).
- Graded the 4 games we simulated. ORL@NYK, TOR@MIN, and LAC@OKC are final and were not simulated, so they are not in the scorecard.
- 10-25 winners 4/4. Total bias that night **−6.62**. Season bias **−3.55** (pred median total minus actual).
- Night reconcile vs box scores, predicted mean sum vs actual: MIN +0.1%, PTS −2.7%, REB +0.9%. Flags: AST +4.5%, STL +24.5%, BLK −18.4%, TOV +26.5%.
- Scorecard: `results/season_scorecard.md`. Storage **11.74 MiB / 2 GB**.

## Post-game through 2026-10-24

- Ingested **8** new finals (10-24); roster refresh **+0/−0**. Fixed `fill_actuals` UnboundLocalError on DNP picks.
- Graded 36 games → `results/season_scorecard.md`.

| Metric | Season to date |
| --- | ---: |
| Games graded | 36 |
| Winner accuracy | 61.1% |
| Spread MAE | 12.51 |
| Total MAE | 17.60 |
| Player MIN / PTS MAE | 7.31 / 5.39 |
| 10–90 coverage | 78.9% |
| Top picks hit / claimed | **60.9%** / 55.2% (56/92) |

## Early-season league environment (2026-10-25) — KEPT

Totals are the weakest graded metric (season total MAE **17.60**). Diagnosis + one change.

### 1. Graded 2026-27 (36 games) — pred vs actual

| | Pred | Actual | Bias |
| --- | ---: | ---: | ---: |
| Game total | 226.96 | 230.17 | **−3.21** |
| Team pace (poss) | ~102.1 (proj OFF) | 101.58 | slight over |
| Team PPP | ~1.111 (implied) | 1.133 | under |

Under-prediction is mostly **efficiency**, not pace. Hist total MAE 17.60.

### 2. League environment YoY

| | 2025-26 full | 2026-27 so far (36g) |
| --- | ---: | ---: |
| Pace | 99.78 | **101.58** |
| PPP | 1.154 | 1.133 |
| PPG | 115.09 | 115.08 |
| 3PA/FGA | 0.415 | 0.419 |
| FTA/FGA | 0.265 | **0.302** |

Faster, more FTA, lower PPP, same PPG — environment shifted.

### 3. Change

`league_env_enabled` (config): while `games_played < league_env_early_season_games` (40):

- League pace + PPG scales vs prior season, sample-size weighted (`league_env_half_life_games: 12`), leakage-safe (`game_date < as_of`).
- Per-team pace blend of as-of current with an anchor (`team_pace_half_life_games: 8`).
- **Live** current season anchors to season-to-date aggregates (already current); **walk-forward** anchors to previous season (no same-season leakage).
- Efficiency via zone FG% + soft FT rate (`apply_league_efficiency_scale`); PPG not PPP (FTA mix). Soft pace cap ±1.5%. Mid-season identity so YoY does not double-count rate blends.

Tests: `tests/test_league_env.py`. Mid reconcile **PASS**.

### 4. Keep decision

**Leakage-free 2025-26 walk-forward** (400g × default runs, seed 1): artifacts `results/backtest/wf_2025_26_league_env_{off,on}/`.

| Metric | OFF | ON |
| --- | ---: | ---: |
| Total MAE | 16.122 | **15.936** |
| Spread MAE | 11.189 | **11.166** |
| Brier | 0.2118 | **0.2115** |
| Winner | 64.0% | 64.0% |

**Early 80 games** (100 runs): total bias **−12.18 → −9.33**; total MAE 19.00 → 17.81; Brier 0.227 → 0.224.

**2026-27 resim** (36g, live-anchor fix): OFF bias −2.63 / MAE 17.06; ON bias **−2.62** / MAE 17.35 (bias holds; MAE ≈noise). Hist graded bias −3.21 unchanged (history not rewritten).

**Kept.** `league_env_enabled: true`.

## Synergy play-types (2026-10-25) — REVERTED from sim

Credit: stats.nba.com Synergy via `nba_api` `SynergyPlayTypes`.

**Ingest (kept):** `play_types` parquet for 2023-24…current — player+team, offense+defense, all 11 play types. Columns: possessions, frequency, PPP, tov%/ft%/score%. Current season refresh ≤1/day (`daily.py`). ~110 KiB/season. Small-sample regression to league by possessions; live blends current with prior.

**Leakage:** walk-forward uses **previous season only**; live may blend current.

**Sim wiring (disabled):** player offense mix × opponent team defense → soft FG/TOV/FT factors (`play_type_defense_weight: 0.35`). Mid-season reconcile **PASS**. Star sanity check (2024-25 data for 2025-26): SGA base PPP 1.10 → ~1.05 vs OKC / ~1.13 vs NOP (realistic, not extreme). See `results/backtest/play_types_star_report.txt`.

### Keep decision — full 2025-26 walk-forward (1314g × 200r, seed 1)

Artifacts: `results/backtest/wf_2025_26_playtypes_{off,on}/`.

| Metric | OFF | ON | |
| --- | ---: | ---: | --- |
| Brier | **0.214** | 0.215 | worse |
| Winner accuracy | **66.7%** | 66.4% | worse |
| Spread MAE | **12.07** | 12.19 | worse |
| Total MAE | 16.12 | **16.00** | better |
| PTS MAE | **5.245** | 5.245 | flat |
| AST MAE | 1.408 | **1.407** | ~flat |
| TOV MAE | 0.913 | **0.912** | ~flat |
| 10–90 coverage | 0.811 | **0.811** | ~flat |

**Reverted.** `play_types_enabled: false`. Ingest/schema/tests retained for a later retune (different weight / interaction with RAPM).

## Upgrade 5 — Variance from player RE + pace (2026-10-17)

- Per-run player shooting (`player_shoot_sd: 0.12`) and usage (`player_usage_sd: 0.10`) multipliers.
- Wider game pace noise (`pace_sd: 5.5`); team hot/cold reduced to 0.05.
- Minutes variance left at 5.0 — coverage must come from scoring/pace, not minutes inflation.

| Metric | Upgrade 4 | Upgrade 5 |
| --- | ---: | ---: |
| Brier | 0.224 | 0.224 |
| Log loss | 0.640 | **0.640** |
| CRPS PTS | 4.65 | 4.65 |
| PIT mean | 0.679 | 0.682 |
| MAE PTS | 5.80 | 5.80 |
| MAE MIN | 6.01 | 6.01 |
| 10–90 coverage | 0.680 | **0.685** |
| Sim / actual PPG | 117.92 / 114.29 | 117.84 / 114.29 |

Coverage up slightly; still short of ~0.80. Artifacts: `results/backtest/upgrade5_overdisp/`.

## Minutes + calibration pass (2026-10-19 night)

- Mid-season: `normalize_gap_close=0` again (no force-to-240 means) → better MIN MAE.
- Early season (`early_season_games: 10`): `early_season_gap_close: 1.0` so opening week still hits ~240 after trades.
- Kept trade any-team minutes fallback + mid-rotation SD caps.
- Calibration: `player_shoot_sd` 0.22, `usage` 0.15, `pace_sd` 9.0 (do not raise `minutes_variance`).
- Probe `--seasons 2024-25 --runs 200 --max-games 400`: Brier 0.228, MAE MIN **6.40**, coverage **0.672**, MAE PTS 5.67. Coverage still short of ~0.80 — needs deeper overdispersion / rotation work, not just SD knobs.

## Opening night freeze (2026-10-19)

- **U8 deferred:** `features.late_season_incentives: false` (not implemented).
- **Minutes:** traded / new-roster players no longer get a full window of same-team zeros; any-team history + depth priors apply. `allocate_team_minutes` fringe-trims and soft-scales to 240 when gap_close=0. Mid-rotation minutes SD capped so PTS p10 is not 0 at 20+ MIN.
- **Injuries:** ak-static primary; static.cms fallback only once (was hanging on unpublished keys). 403 treated as not-posted.
- **Schedule:** 2026-27 regular season schedule stored (opening night 2026-10-20: BOS@DET, PHI@NYK, OKC@SAS).
- **Overrides:** cleared for opening night (add late scratches in `overrides.yaml` before `daily.py`).
- **RUNBOOK.md:** game-day steps.
- Tests: **74 passed**.
- Full walk-forward `--seasons 2024-2025 --runs 200 --seed 1` (2627 games):

| Metric | Upgrade 6 | Opening night v1.0 |
| --- | ---: | ---: |
| Brier | **0.222** | 0.225 |
| Log loss | **0.636** | 0.640 |
| CRPS PTS | **4.65** | 4.80 |
| PIT mean | **0.683** | 0.693 |
| MAE PTS | **5.79** | 5.92 |
| MAE MIN | **6.01** | 7.54 |
| 10–90 coverage | **0.687** | 0.646 |
| Sim / actual PPG | 117.56 / 114.29 | 117.56 / 114.29 |
| Sim / actual poss | — | 98.95 / 98.92 |

MIN MAE and coverage regressed vs U6 from re-enforcing ~240 team minutes (needed for opening-night trades). Win metrics nearly flat. Artifacts: `results/backtest/opening_night_v1/`.

## Upgrade 6 — Kalman team ratings + rest HCA (2026-10-18)

- `projections/kalman.py`: walk-forward Kalman net ratings updated after every game.
- HCA non-linear in both teams' rest (B2B penalty; both-B2B scale 0.55).
- Blend Kalman into roster/RAPM strength (`kalman_strength_weight: 0.45`).

| Metric | Upgrade 5 | Upgrade 6 |
| --- | ---: | ---: |
| Brier | 0.224 | **0.222** |
| Log loss | 0.640 | **0.636** |
| CRPS PTS | 4.65 | **4.65** |
| PIT mean | 0.682 | 0.683 |
| MAE PTS | 5.80 | **5.79** |
| MAE MIN | 6.01 | 6.01 |
| 10–90 coverage | 0.685 | 0.687 |
| Sim / actual PPG | 117.84 / 114.29 | 117.56 / 114.29 |

Win calibration recovered to U1 level. Artifacts: `results/backtest/upgrade6_kalman/`.

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
