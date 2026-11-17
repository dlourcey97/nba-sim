"""Paired decision for quieter lineup noise on high-usage players.

Baseline is the current engine (star_lineup_scale 1). The variant scales only
the centered Gumbel deviation for players with usage at or above star_usage_min
and a minutes mean of at least 20. Everyone else keeps full lineup noise.

Both seasons, 1,000 sims, seed 1, four workers. The interval is variant minus
baseline. Keep only when, on both seasons, points CRPS and the star bust rate
improve and those intervals exclude zero, and the Brier, spread MAE, and total
MAE intervals include zero.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from backtest.bootstrap import _aligned, paired_bootstrap, paired_player_bootstrap
from nba_sim.settings import load_settings
from scripts.fringe_decision import SEASONS, _guardrail, _load, _out, _run

SEED = 1


def _config(settings, scale: float) -> dict:
    config = copy.deepcopy(settings.config)
    config["simulation"]["star_lineup_scale"] = float(scale)
    config["simulation"]["lineup_model"] = "gumbel"
    config.setdefault("context", {})["dunks_fallback_log"] = False
    return config


def _scale_arg() -> float:
    for arg in sys.argv[1:]:
        if arg.startswith("--scale="):
            return float(arg.split("=", 1)[1])
    raise SystemExit("pass --scale=0.45")


def _fmt(boot: dict) -> str:
    parts = []
    for metric, row in boot.items():
        parts.append(
            f"{metric}: {row['diff']:+.4f} [{row['low']:+.4f}, {row['high']:+.4f}] "
            f"{'decisive' if row['decisive'] else 'inside noise'}"
        )
    return "; ".join(parts)


def _ratio_boot(left, right, total_key: str, count_key: str) -> dict:
    pairs = _aligned(left, right)
    if not pairs:
        raise ValueError("no games in common")
    left_total = np.array([float(row.get(total_key) or 0.0) for row, _ in pairs])
    left_count = np.array([float(row.get(count_key) or 0.0) for row, _ in pairs])
    right_total = np.array([float(row.get(total_key) or 0.0) for _, row in pairs])
    right_count = np.array([float(row.get(count_key) or 0.0) for _, row in pairs])

    def _ratio(total: np.ndarray, count: np.ndarray) -> float:
        denom = float(count.sum())
        if denom <= 0.0:
            return float("nan")
        return float(total.sum() / denom)

    observed = _ratio(right_total, right_count) - _ratio(left_total, left_count)
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, len(pairs), size=(2000, len(pairs)))
    diffs = (
        right_total[draws].sum(axis=1) / np.maximum(right_count[draws].sum(axis=1), 1e-9)
        - left_total[draws].sum(axis=1) / np.maximum(left_count[draws].sum(axis=1), 1e-9)
    )
    lo, hi = np.quantile(diffs, [0.025, 0.975])
    return {
        "diff": float(observed),
        "low": float(lo),
        "high": float(hi),
        "decisive": bool(lo > 0.0 or hi < 0.0),
        "games": float(len(pairs)),
    }


def _better(row: dict) -> bool:
    return bool(row["decisive"] and row["high"] < 0.0)


def _inside(row: dict) -> bool:
    return not bool(row["decisive"])


def _probe(settings) -> None:
    scales = [1.0, 0.65, 0.45, 0.25]
    for arg in sys.argv[1:]:
        if arg.startswith("--scales="):
            scales = [float(part) for part in arg.split("=", 1)[1].split(",") if part]
    for scale in scales:
        print(f"GUARDRAIL scale={scale:.2f}", flush=True)
        try:
            _guardrail(settings, _config(settings, scale))
        except SystemExit as exc:
            print(f"scale={scale:.2f} BLOCKED {exc}", flush=True)
    print("RECONCILE PROBE DONE", flush=True)


def main() -> None:
    settings = load_settings()
    if "--probe" in sys.argv:
        _probe(settings)
        return
    scale = _scale_arg()
    tag = f"bust_s{scale:.2f}".replace(".", "")
    before = _config(settings, 1.0)
    after = _config(settings, scale)
    if "--skip-guardrail" not in sys.argv:
        print(f"GUARDRAIL scale={scale:.2f}", flush=True)
        _guardrail(settings, after)
    player: dict[str, dict] = {}
    game: dict[str, dict] = {}
    bust: dict[str, dict] = {}
    stopped = False
    for season in SEASONS:
        base_dir = _out(season, "bust_base")
        var_dir = _out(season, tag)
        _run(replace(settings, config=before), before, season, base_dir)
        _run(replace(settings, config=after), after, season, var_dir)
        left = _load(base_dir / "games.parquet")
        right = _load(var_dir / "games.parquet")
        player[season] = paired_player_bootstrap(left, right, n_boot=2000, seed=SEED)
        game[season] = paired_bootstrap(left, right, n_boot=2000, seed=SEED)
        bust[season] = _ratio_boot(left, right, "star_bust", "star_bust_draws")
        print(f"PLAYER {season} variant-minus-base {_fmt(player[season])}", flush=True)
        print(f"BUST {season} variant-minus-base {_fmt({'bust': bust[season]})}", flush=True)
        print(f"GAME {season} variant-minus-base {_fmt(game[season])}", flush=True)
        (var_dir / "paired.json").write_text(
            json.dumps(
                {"player": player[season], "bust": bust[season], "game": game[season]},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        season_ok = (
            _better(player[season]["crps_pts"])
            and _better(bust[season])
            and _inside(game[season]["brier"])
            and _inside(game[season]["mae_margin"])
            and _inside(game[season]["mae_total"])
        )
        if not season_ok:
            print(f"CALL {tag} REVERT after {season}", flush=True)
            stopped = True
            break
    if stopped:
        print("BUST DECISION DONE", flush=True)
        return
    crps_ok = all(_better(player[season]["crps_pts"]) for season in SEASONS)
    bust_ok = all(_better(bust[season]) for season in SEASONS)
    game_ok = all(
        _inside(game[season]["brier"])
        and _inside(game[season]["mae_margin"])
        and _inside(game[season]["mae_total"])
        for season in SEASONS
    )
    call = "KEEP" if crps_ok and bust_ok and game_ok else "REVERT"
    print(
        f"CALL {tag} {call} crps_ok={crps_ok} bust_ok={bust_ok} game_ok={game_ok}",
        flush=True,
    )
    print("BUST DECISION DONE", flush=True)


if __name__ == "__main__":
    main()
