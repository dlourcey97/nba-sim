"""Decision runs for honest scoring and the fringe-minute fixes.

Each step is a full 2025-26 season and the 2024-25 holdout. 1,000 sims, seed
1, four workers, one BLAS thread. Tonight's box score is not an input. A step
is kept only when reconcile passes and the paired bootstrap holds or improves.

Step 0 changes scoring only. The sim is the current engine (15-man historical
cap, fringe floor off, return blend off, pre-debut stint off).
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pyarrow.parquet as pq

from backtest.bootstrap import paired_bootstrap
from backtest.evaluate import _write_game_rows, evaluate_seasons
from backtest.reconcile import check_reconcile_guardrail
from nba_sim.settings import load_settings

RUNS = 1000
SEED = 1
WORKERS = 4
SEASONS = ("2025-26", "2024-25")


def _base_config(settings) -> dict:
    config = copy.deepcopy(settings.config)
    config.setdefault("context", {})["dunks_fallback_log"] = False
    config["minutes"]["historical_roster_cap"] = 15
    config["minutes"]["fringe_minute_floor"] = False
    config["minutes"]["return_minute_blend"] = False
    config["minutes"]["pre_debut_stint"] = False
    return config


def _out(season: str, step: str) -> Path:
    label = season.replace("-", "_")
    return ROOT / "results" / "backtest" / f"wf_{label}_{step}_1000"


def _load(path: Path) -> list[dict]:
    return pq.read_table(path).to_pylist()


def _total_bias(rows: list[dict]) -> float:
    if not rows:
        return float("nan")
    diffs = [float(row["pred_total"]) - float(row["act_total"]) for row in rows]
    return float(sum(diffs) / len(diffs))


def _run(settings, config: dict, season: str, out: Path) -> dict:
    metrics_path = out / "metrics.json"
    games_path = out / "games.parquet"
    if metrics_path.exists() and games_path.exists():
        print(f"SKIP {out.name}", flush=True)
        return json.loads(metrics_path.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    print(f"START {out.name}", flush=True)
    report = evaluate_seasons(
        settings,
        [season],
        runs=RUNS,
        seed=SEED,
        workers=WORKERS,
        config_override=config,
        progress_every=100,
    )
    elapsed = time.perf_counter() - started
    payload = report.as_dict()
    payload["elapsed_seconds"] = elapsed
    payload["total_bias"] = _total_bias(report.game_rows or [])
    metrics_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _write_game_rows(games_path, report.game_rows or [])
    print(
        f"FINISHED {out.name} games={report.games} seconds={elapsed:.1f} "
        f"MIN {report.mae_min:.3f} PTS {report.mae_pts:.3f} "
        f"REB {report.mae_reb:.3f} AST {report.mae_ast:.3f} "
        f"causes {report.cause_a}/{report.cause_b}/{report.cause_c}/{report.cause_d}/{report.cause_e} "
        f"spread {report.mae_margin:.3f} total {report.mae_total:.3f} "
        f"bias {payload['total_bias']:.2f} brier {report.brier_win:.4f}",
        flush=True,
    )
    return payload


def _format(boot: dict) -> str:
    parts = []
    for metric, row in boot.items():
        parts.append(
            f"{metric}: {row['diff']:+.4f} [{row['low']:+.4f}, {row['high']:+.4f}] "
            f"{'decisive' if row['decisive'] else 'inside noise'}"
        )
    return "; ".join(parts)


def _compare_old(season: str, new: dict, new_games: Path) -> None:
    label = season.replace("-", "_")
    old_dir = ROOT / "results" / "backtest" / f"wf_{label}_rotation_on_1000"
    old_path = old_dir / "metrics.json"
    if not old_path.exists():
        print(f"NO OLD BASELINE {old_path}", flush=True)
        return
    old = json.loads(old_path.read_text(encoding="utf-8"))
    print(
        f"OLD {season} rows={old.get('player_rows')} "
        f"MIN {old.get('mae_min'):.3f} PTS {old.get('mae_pts'):.3f} "
        f"REB {old.get('mae_reb'):.3f} AST {old.get('mae_ast'):.3f}",
        flush=True,
    )
    print(
        f"NEW {season} rows={new.get('player_rows')} "
        f"MIN {new.get('mae_min'):.3f} PTS {new.get('mae_pts'):.3f} "
        f"REB {new.get('mae_reb'):.3f} AST {new.get('mae_ast'):.3f} "
        f"causes {new.get('cause_a')}/{new.get('cause_b')}/{new.get('cause_c')}/"
        f"{new.get('cause_d')}/{new.get('cause_e')} "
        f"bias {new.get('total_bias')} spread {new.get('mae_margin')} "
        f"brier {new.get('brier_win')}",
        flush=True,
    )
    old_games = old_dir / "games.parquet"
    if old_games.exists() and new_games.exists():
        boot = paired_bootstrap(_load(old_games), _load(new_games), n_boot=2000, seed=SEED)
        print(f"PAIRED {season} new-minus-old {_format(boot)}", flush=True)


def _guardrail(settings, config: dict) -> None:
    local = replace(settings, config=config)
    report = check_reconcile_guardrail(
        local,
        runs=80,
        max_games=80,
        skip_games=400,
        seed=SEED,
        threshold_pct=3.0,
        config=config,
    )
    print(f"RECONCILE passed={report.passed} games={report.games}", flush=True)
    print(f"team_flags={report.team_flags}", flush=True)
    print(f"role_flags={report.role_flags}", flush=True)
    keys = ("min", "pts", "reb", "ast", "tov", "stl", "blk")
    print(
        "team "
        + " ".join(f"{key}={report.team_delta_pct.get(key, 0):+.2f}%" for key in keys),
        flush=True,
    )
    print(
        "role "
        + " ".join(f"{key}={report.role_delta_pct.get(key, 0):+.2f}%" for key in keys),
        flush=True,
    )
    if not report.passed:
        raise SystemExit("reconcile failed; long sim not started")


def _paired(season: str, step: str, baseline: str) -> None:
    new_games = _out(season, step) / "games.parquet"
    old_games = _out(season, baseline) / "games.parquet"
    boot = paired_bootstrap(_load(old_games), _load(new_games), n_boot=2000, seed=SEED)
    print(f"PAIRED {season} {step}-minus-{baseline} {_format(boot)}", flush=True)


def step1() -> None:
    """Drop the 15-man historical cap. Compare to the honest-scoring baseline."""
    settings = load_settings()
    config = _base_config(settings)
    config["minutes"]["historical_roster_cap"] = 0
    local = replace(settings, config=config)
    _guardrail(settings, config)
    for season in SEASONS:
        out = _out(season, "cap")
        _run(local, config, season, out)
        _paired(season, "cap", "honest")
    print("STEP 1 DONE", flush=True)


def step2() -> None:
    """Stop wiping fringe players to 0. The 15-man cap stays on."""
    settings = load_settings()
    config = _base_config(settings)
    config["minutes"]["fringe_minute_floor"] = True
    local = replace(settings, config=config)
    _guardrail(settings, config)
    for season in SEASONS:
        out = _out(season, "fringe")
        _run(local, config, season, out)
        _paired(season, "fringe", "honest")
    print("STEP 2 DONE", flush=True)


def step3() -> None:
    """Blend a returner's pre-sit minutes with his recent zeros. Cap stays at 15."""
    settings = load_settings()
    config = _base_config(settings)
    config["minutes"]["return_minute_blend"] = True
    local = replace(settings, config=config)
    _guardrail(settings, config)
    for season in SEASONS:
        out = _out(season, "return")
        _run(local, config, season, out)
        _paired(season, "return", "honest")
    print("STEP 3 DONE", flush=True)


def step0() -> None:
    settings = load_settings()
    config = _base_config(settings)
    local = replace(settings, config=config)
    for season in SEASONS:
        out = _out(season, "honest")
        payload = _run(local, config, season, out)
        _compare_old(season, payload, out / "games.parquet")
    print("STEP 0 DONE", flush=True)


def main() -> None:
    step = sys.argv[1] if len(sys.argv) > 1 else "0"
    if step in {"0", "step0", "honest"}:
        step0()
        return
    if step in {"1", "step1", "cap"}:
        step1()
        return
    if step in {"2", "step2", "fringe"}:
        step2()
        return
    if step in {"3", "step3", "return"}:
        step3()
        return
    raise SystemExit(f"unknown step {step}")


if __name__ == "__main__":
    main()
