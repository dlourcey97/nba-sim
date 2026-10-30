"""Run the remaining one-flag re-judges against the frozen current-engine baseline.

Each job is the current config with one switch changed. A variant is adopted
only when 2025-26 shows a decisive improvement and no decisive worsening, and
the 2024-25 holdout shows the same kind of call. Lower Brier, spread MAE, and
total MAE are better. The difference is variant minus baseline.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
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
HOLDOUT = "2024-25"
TUNE = "2025-26"


def _job(name: str, changes: dict, adopt: dict[str, str]) -> dict:
    return {"name": name, "changes": changes, "adopt": adopt}


JOBS = [
    _job(
        "referees",
        {("context", "referees_enabled"): True},
        {"referees_enabled: false": "referees_enabled: true"},
    ),
    _job(
        "play_types",
        {("context", "play_types_enabled"): True},
        {"play_types_enabled: false": "play_types_enabled: true"},
    ),
    _job(
        "rapm_off",
        {("context", "nbarapm_enabled"): False},
        {"nbarapm_enabled: true": "nbarapm_enabled: false"},
    ),
    _job(
        "step_f_off",
        {("features", "stint_rotations_step_f"): False},
        {"stint_rotations_step_f: true": "stint_rotations_step_f: false"},
    ),
    _job(
        "minutes_engine",
        {("features", "minutes_model"): "engine"},
        {"minutes_model: naive_last10": "minutes_model: engine"},
    ),
    _job(
        "bball_roles",
        {("context", "bball_roles_enabled"): True},
        {"bball_roles_enabled: false": "bball_roles_enabled: true"},
    ),
    _job(
        "bball_defense",
        {("context", "bball_defense_enabled"): True},
        {"bball_defense_enabled: false": "bball_defense_enabled: true"},
    ),
    _job(
        "bball_play_types",
        {("context", "bball_play_types_enabled"): True},
        {"bball_play_types_enabled: false": "bball_play_types_enabled: true"},
    ),
    _job(
        "bball_matchups",
        {("context", "bball_matchups_enabled"): True},
        {"bball_matchups_enabled: false": "bball_matchups_enabled: true"},
    ),
]


def _out_dir(name: str, season: str) -> Path:
    label = season.replace("-", "_")
    return ROOT / "results" / "backtest" / f"wf_{label}_{name}_1000"


def _baseline(season: str) -> Path:
    label = season.replace("-", "_")
    return ROOT / "results" / "backtest" / f"wf_{label}_current_1000" / "games.parquet"


def _load_games(path: Path) -> list[dict]:
    return pq.read_table(path).to_pylist()


def _sides(boot: dict) -> tuple[list[str], list[str]]:
    better: list[str] = []
    worse: list[str] = []
    for metric, row in boot.items():
        if float(row["high"]) < 0.0:
            better.append(metric)
        elif float(row["low"]) > 0.0:
            worse.append(metric)
    return better, worse


def _format_boot(boot: dict) -> str:
    lines = []
    for metric, row in boot.items():
        lines.append(
            f"{metric}: {row['diff']:+.4f} [{row['low']:+.4f}, {row['high']:+.4f}] "
            f"{'decisive' if row['decisive'] else 'inside noise'}"
        )
    return "; ".join(lines)


def _running_override() -> bool:
    found = subprocess.run(
        ["pgrep", "-f", "run_override.py"],
        check=False,
        capture_output=True,
        text=True,
    )
    return found.returncode == 0 and bool(found.stdout.strip())


def _wait_for_referees() -> None:
    metrics = _out_dir("referees", TUNE) / "metrics.json"
    games = _out_dir("referees", TUNE) / "games.parquet"
    if metrics.is_file() and games.is_file() and not _running_override():
        return
    if not _running_override() and not metrics.is_file():
        return
    print("waiting for the referees run already in progress", flush=True)
    while _running_override():
        time.sleep(20)
    for _ in range(30):
        if metrics.is_file() and games.is_file():
            return
        time.sleep(2)


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
    (out / "metrics.json").write_text(
        json.dumps(report.as_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    _write_game_rows(out / "games.parquet", report.game_rows or [])
    (out / "elapsed.txt").write_text(f"{elapsed:.1f}\n", encoding="utf-8")
    print(f"FINISHED {out.name} games={report.games} seconds={elapsed:.1f}", flush=True)
    return elapsed


def _mutate(base: dict, changes: dict) -> dict:
    config = copy.deepcopy(base)
    for (section, key), value in changes.items():
        config[section][key] = value
    return config


def _append(log_path: Path, text: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")
    print(text, flush=True)


def _apply_adoptions(adoptions: list[dict[str, str]]) -> list[str]:
    path = ROOT / "config.yaml"
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []
    for mapping in adoptions:
        for old, new in mapping.items():
            count = text.count(old)
            if count != 1:
                applied.append(f"skipped {old!r} (found {count})")
                continue
            text = text.replace(old, new, 1)
            applied.append(f"{old} -> {new}")
    path.write_text(text, encoding="utf-8")
    return applied


def main() -> None:
    settings = load_settings()
    log_path = ROOT / "results" / "backtest" / "decision_log.md"
    _wait_for_referees()
    decisions: list[dict] = []
    adoptions: list[dict[str, str]] = []
    for job in JOBS:
        name = job["name"]
        tune_out = _out_dir(name, TUNE)
        tune_games = tune_out / "games.parquet"
        if not tune_games.is_file():
            print(f"START {name} {TUNE}", flush=True)
            _run(settings, _mutate(settings.config, job["changes"]), TUNE, tune_out)
        boot = paired_bootstrap(_load_games(_baseline(TUNE)), _load_games(tune_games), n_boot=10000, seed=1)
        better, worse = _sides(boot)
        line = f"## {name} {TUNE}\n{_format_boot(boot)}\n"
        call = "leave"
        if worse and better:
            call = "mixed"
        elif worse:
            call = "worse"
        elif better:
            hold_out = _out_dir(name, HOLDOUT)
            hold_games = hold_out / "games.parquet"
            if not hold_games.is_file():
                print(f"START {name} {HOLDOUT}", flush=True)
                _run(settings, _mutate(settings.config, job["changes"]), HOLDOUT, hold_out)
            hold = paired_bootstrap(
                _load_games(_baseline(HOLDOUT)),
                _load_games(hold_games),
                n_boot=10000,
                seed=1,
            )
            hold_better, hold_worse = _sides(hold)
            line += f"## {name} {HOLDOUT}\n{_format_boot(hold)}\n"
            if hold_worse:
                call = "holdout contradicts"
            elif hold_better:
                call = "adopt"
                adoptions.append(job["adopt"])
            else:
                call = "holdout not decisive"
        line += f"call: {call}\n"
        _append(log_path, line)
        decisions.append({"name": name, "call": call, "tune": boot})
    applied = _apply_adoptions(adoptions) if adoptions else []
    summary = {
        "decisions": [{k: v for k, v in item.items() if k != "tune"} for item in decisions],
        "config_edits": applied,
    }
    (ROOT / "results" / "backtest" / "decision_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    _append(log_path, "config edits:\n" + "\n".join(applied or ["none"]))
    print("QUEUE_DONE", flush=True)


if __name__ == "__main__":
    main()
