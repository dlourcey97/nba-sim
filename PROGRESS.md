# Progress

Last updated after Phase 5 (possession simulation engine).

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Project setup and storage | done | Config, schema, ignore files, cap, and storage report. |
| 2. Ingestion and backfill | done | nba_api, PlayByPlayV3 possessions, live-feed fallback, backfill.py. |
| 3. Injury report and overrides | done | Official PDF parse via pypdf, overrides.yaml precedence. |
| 4. Projections | done | Blend, context, absence redistribution, minutes model. |
| 5. Simulation | done | Vectorized possession engine; ~5s for 10k runs on sample game. |
| 6. Outputs and daily.py | not started | JSON summaries, prediction history, nightly pipeline. |
| 7. Backtesting | not started | Walk-forward metrics and tuning. |

## Phase 5

`sim/engine.py` simulates each game possession-by-possession, vectorized across runs with numpy.

- Minutes sampled per player per run; lineups are the top five by noisy minutes once per run.
- Each possession: steal / turnover / free throws / zone shot / block / make+assist / rebound (ORB keeps possession).
- Pace noise on team possessions; overtime when tied (up to 5 periods).
- Seed reproduces arrays. Raw run matrices are returned in memory only; nothing is written under `DATA_DIR`.

Checked on `0022400102` with 10,000 runs: home ~97.7, away ~96.7, about 5 seconds on this Mac.

## Next

Phase 6: output summaries, `results/latest/` JSON, prediction history, `daily.py`, and `run.py`.
