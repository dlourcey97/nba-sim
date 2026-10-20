# Opening-night runbook (2026-27)

Tag: `v1.0-opening-night`. Season opens **2026-10-20** (BOS@DET, PHI@NYK, OKC@SAS).

Engine only simulates and writes results. No odds or betting logic.

## Prerequisites

```bash
cd /Users/deanlourcey/Documents/nba-sim
source .venv/bin/activate
# .env must have absolute DATA_DIR and ARCHIVE_DIR outside the repo
```

Confirm:

```bash
python -c "from nba_sim.settings import load_settings; s=load_settings(); print(s.current_season, s.data_dir)"
# expect: 2026-27 /Users/deanlourcey/nba_data
```

`features.late_season_incentives` stays `false` in `config.yaml` (U8 not shipped).

## Game-day steps

### 1. Pull latest (optional)

```bash
git fetch --tags
git checkout v1.0-opening-night   # or main if you have only post-tag fixes you trust
```

### 2. Late scratches → `overrides.yaml`

Edit `overrides.yaml` **before** running the pipeline. Overrides win over the official injury PDF.

```yaml
players:
  - player_id: 1629029   # look up id if needed
    player_name: "Example Player"
    team_abbr: BOS
    game_date: "2026-10-20"
    status: out
    reason: "late scratch"
    minutes_cap: null
```

Statuses: `out`, `doubtful`, `questionable`, `probable`, `available`.  
Use `minutes_cap` for a minutes limit without full OUT.  
Clear yesterday’s entries; only tonight’s date matters for the slate.

### 3. Nightly pipeline (full slate)

```bash
python daily.py --date 2026-10-20 --log-file /Users/deanlourcey/nba_archive/daily.log
```

What this does:

1. Incremental ingest for `2026-27` (no regular-season games yet on opening night — schedule refresh / empty finals OK)
2. Refresh `current_rosters` from CommonTeamRoster (all 30 teams)
3. Download + parse official injury PDF; merge `overrides.yaml`
4. Project + simulate every game on that date (`simulation.runs`, default 10,000)
5. Write `results/latest/*.json` and append prediction history
6. Print storage report; delete temps

Useful flags:

| Flag | When |
| --- | --- |
| `--skip-ingest` | Already ingested; only re-sim after override edits |
| `--skip-injury-pdf` | PDF down; trust overrides only |
| `--runs 10000` | Override config run count |
| `--seed 42` | Reproducible (default seed is null) |

Re-run after a late scratch (skip ingest):

```bash
# 1) edit overrides.yaml
# 2) re-sim only
python daily.py --date 2026-10-20 --skip-ingest --log-file /Users/deanlourcey/nba_archive/daily_resim.log
```

### 4. Single game (optional)

```bash
python run.py --date 2026-10-20 --game BOS-DET --runs 10000
python run.py --date 2026-10-20 --all --runs 10000
```

### 5. Read outputs

- Per-game JSON: `results/latest/` (gitignored)
- Prediction history: `$DATA_DIR/prediction_history/season=2026-27/`
- Log: `/Users/deanlourcey/nba_archive/daily.log`

Each JSON has win probability, score/total distributions, and per-player percentiles (MIN/PTS/REB/AST/3PM/…).

### 6. After games finish (next night)

Same `daily.py` for the next slate date. Ingest fills finals; prediction history gets actuals filled for completed games.

## Rollback

```bash
git checkout v1.0-opening-night
```

Data under `DATA_DIR` is not in git — do not delete it.

## Smoke checks (optional)

```bash
PYTHONPATH=. pytest -q
PYTHONPATH=. python scripts/opening_night_checks.py --date 2026-10-20 --runs 2000 --seed 42
```

## Opening-night slate (reference)

| Away | Home | Notes |
| --- | --- | --- |
| BOS | DET | 3:00 p.m. ET |
| PHI | NYK | 7:00 p.m. ET |
| OKC | SAS | 9:30 p.m. ET |
