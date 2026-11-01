"""Judge the rotation minute prior on 2025-26 and the 2024-25 holdout.

Both sides use this tree. The only switch is minutes.role_prior_enabled.
Tonight's box score is not an input: the Dunks fallback log is off, and EPM
files for these seasons do not exist. 1,000 sims, seed 1, four workers.
The difference is prior-on minus prior-off. Lower is better.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time
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
from nba_sim.settings import load_settings

RUNS = 1000
SEED = 1
WORKERS = 4
SEASONS = ("2025-26", "2024-25")


def _config(base: dict, enabled: bool) -> dict:
    config = copy.deepcopy(base)
    config["minutes"]["role_prior_enabled"] = enabled
    config.setdefault("context", {})["dunks_fallback_log"] = False
    return config


def _out(season: str, enabled: bool) -> Path:
    label = season.replace("-", "_")
    side = "on" if enabled else "off"
    return ROOT / "results" / "backtest" / f"wf_{label}_role_prior_{side}_1000"


def _load(path: Path) -> list[dict]:
    return pq.read_table(path).to_pylist()


def _run(settings, config: dict, season: str, out: Path) -> float:
    out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
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
    (out / "metrics.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _write_game_rows(out / "games.parquet", report.game_rows or [])
    print(
        f"FINISHED {out.name} games={report.games} seconds={elapsed:.1f} "
        f"zero_played={report.projected_zero_played}",
        flush=True,
    )
    return elapsed


def _sides(boot: dict) -> tuple[list[str], list[str]]:
    better: list[str] = []
    worse: list[str] = []
    for metric, row in boot.items():
        if float(row["high"]) < 0.0:
            better.append(metric)
        elif float(row["low"]) > 0.0:
            worse.append(metric)
    return better, worse


def _format(boot: dict) -> str:
    parts = []
    for metric, row in boot.items():
        parts.append(
            f"{metric}: {row['diff']:+.4f} [{row['low']:+.4f}, {row['high']:+.4f}] "
            f"{'decisive' if row['decisive'] else 'inside noise'}"
        )
    return "; ".join(parts)


def _road(rows: list[dict]) -> dict[str, float]:
    home = [float(row["pred_home_pts"]) - float(row["act_home_pts"]) for row in rows if row.get("pred_home_pts") is not None]
    away = [float(row["pred_away_pts"]) - float(row["act_away_pts"]) for row in rows if row.get("pred_away_pts") is not None]
    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else float("nan")
    return {
        "home_bias": _mean(home),
        "away_bias": _mean(away),
        "games": float(len(home)),
    }


def reference() -> None:
    """Regrade the 2026-27 finals. Not used for the keep call."""
    settings = load_settings()
    summary: dict = {}
    for enabled in (False, True):
        out = ROOT / "results" / "backtest" / f"ref_2026_27_role_prior_{'on' if enabled else 'off'}_1000"
        if not (out / "metrics.json").is_file():
            print(f"START reference role_prior={enabled}", flush=True)
            _run(settings, _config(settings.config, enabled), "2026-27", out)
        metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
        rows = _load(out / "games.parquet")
        summary["on" if enabled else "off"] = {"metrics": metrics, "road": _road(rows)}
        print(
            f"reference {'on' if enabled else 'off'} "
            f"MIN {metrics['mae_min']:.3f} PTS {metrics['mae_pts']:.3f} "
            f"REB {metrics['mae_reb']:.3f} AST {metrics['mae_ast']:.3f} "
            f"total {metrics['mae_total']:.3f} spread {metrics['mae_margin']:.3f} "
            f"brier {metrics['brier_win']:.4f} zero {metrics['projected_zero_played']} "
            f"ppg {metrics['sim_ppg']:.2f} vs {metrics['actual_ppg']:.2f}",
            flush=True,
        )
    dest = ROOT / "results" / "backtest" / "role_prior_reference.json"
    dest.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {dest}", flush=True)


def main() -> None:
    settings = load_settings()
    summary: dict = {"seasons": {}, "call": "leave"}
    for season in SEASONS:
        for enabled in (False, True):
            out = _out(season, enabled)
            if not (out / "games.parquet").is_file() or not (out / "metrics.json").is_file():
                print(f"START {season} role_prior={enabled}", flush=True)
                _run(settings, _config(settings.config, enabled), season, out)
        off_games = _load(_out(season, False) / "games.parquet")
        on_games = _load(_out(season, True) / "games.parquet")
        boot = paired_bootstrap(off_games, on_games, n_boot=10000, seed=1)
        better, worse = _sides(boot)
        off_metrics = json.loads((_out(season, False) / "metrics.json").read_text(encoding="utf-8"))
        on_metrics = json.loads((_out(season, True) / "metrics.json").read_text(encoding="utf-8"))
        summary["seasons"][season] = {
            "bootstrap": boot,
            "better": better,
            "worse": worse,
            "off": off_metrics,
            "on": on_metrics,
            "road_off": _road(off_games),
            "road_on": _road(on_games),
            "line": _format(boot),
        }
        print(f"{season} {_format(boot)}", flush=True)

    tune = summary["seasons"]["2025-26"]
    hold = summary["seasons"]["2024-25"]
    call = "leave"
    if tune["worse"] and tune["better"]:
        call = "mixed"
    elif tune["worse"]:
        call = "worse"
    elif tune["better"]:
        if hold["worse"]:
            call = "holdout contradicts"
        elif hold["better"]:
            call = "adopt"
        else:
            call = "holdout inside noise"
    summary["call"] = call
    dest = ROOT / "results" / "backtest" / "role_prior_decision.json"
    dest.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"CALL {call}", flush=True)
    print(f"wrote {dest}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "reference":
        reference()
    else:
        main()
