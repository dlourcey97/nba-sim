"""Seat a scorer for his minute share, and keep his shot share.

Before is the shot-share engine (usage rebase, calibration, star minutes).
After also seats him when a draw at minutes/48 says he is on the floor, and
gives him his own usage as his shot share instead of dividing by the five.
The lineup scale stays 1.0. Calibration power stays 0.65, the measured setting.

A game metric fails only when its interval lies entirely on the worse side.
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

from backtest.bootstrap import paired_bootstrap, paired_player_bootstrap
from nba_sim.settings import load_settings
from scripts.bust_decision import _better, _fmt, _ratio_boot
from scripts.fringe_decision import SEASONS, _guardrail, _load, _out, _run
from scripts.shot_share_decision import _bias, _cond_line, _tier_line

SEED = 1


def _not_worse(row: dict) -> bool:
    """Positive is worse. Fail only when the whole interval is positive."""
    return not (float(row["low"]) > 0.0)


def _over_line(rows: list[dict]) -> str:
    draws = sum(float(row.get("over_draws") or 0.0) for row in rows)
    wins = sum(float(row.get("over_wins") or 0.0) for row in rows)
    actual_n = sum(float(row.get("over_actual_n") or 0.0) for row in rows)
    actual_w = sum(float(row.get("over_actual_wins") or 0.0) for row in rows)
    sim = wins / draws if draws else float("nan")
    act = actual_w / actual_n if actual_n else float("nan")
    if draws <= 0 and actual_n <= 0:
        return "n/a"
    return f"sim {sim:.3f} ({int(wins)}/{int(draws)}) actual {act:.3f} ({int(actual_w)}/{int(actual_n)})"


def _config(settings, anchor: bool) -> dict:
    config = copy.deepcopy(settings.config)
    config["blending"]["align_box_usage"] = True
    sim = config["simulation"]
    sim["calibrate_shot_shares"] = True
    sim["usage_calibrate_runs"] = 250
    sim["usage_calibrate_rounds"] = 2
    sim["usage_calibrate_tol"] = 0.03
    sim["usage_calibrate_power"] = 0.65
    sim["star_lineup_scale"] = 1.0
    sim["anchor_star_usage"] = bool(anchor)
    config.setdefault("minutes", {})["protect_star_minutes"] = True
    config["minutes"]["star_minute_floor"] = 34.0
    config["minutes"]["star_protect_blk_max"] = 0.02
    config.setdefault("context", {})["dunks_fallback_log"] = False
    return config


def main() -> None:
    settings = load_settings()
    before = _config(settings, False)
    after = _config(settings, True)
    print("GUARDRAIL after", flush=True)
    _guardrail(settings, after)
    for season in SEASONS:
        base_dir = _out(season, "shot_share")
        var_dir = _out(season, "star_anchor")
        if not (base_dir / "metrics.json").exists():
            raise SystemExit(f"missing before side {base_dir}")
        print(f"SKIP {base_dir.name}", flush=True)
        _run(replace(settings, config=after), after, season, var_dir)
        left = _load(base_dir / "games.parquet")
        right = _load(var_dir / "games.parquet")
        player = paired_player_bootstrap(left, right, n_boot=2000, seed=SEED)
        game = paired_bootstrap(left, right, n_boot=2000, seed=SEED)
        bust = _ratio_boot(left, right, "star_bust", "star_bust_draws")
        base_metrics = json.loads((base_dir / "metrics.json").read_text(encoding="utf-8"))
        var_metrics = json.loads((var_dir / "metrics.json").read_text(encoding="utf-8"))
        bias = (_bias(base_metrics), _bias(var_metrics))
        print(f"PLAYER {season} variant-minus-base {_fmt(player)}", flush=True)
        print(f"BUST {season} variant-minus-base {_fmt({'bust': bust})}", flush=True)
        print(
            f"BIAS {season} before {bias[0]:+.2f} after {bias[1]:+.2f} "
            f"star_pts {base_metrics.get('star_pred_mean'):.2f}->{var_metrics.get('star_pred_mean'):.2f} "
            f"actual {var_metrics.get('star_act_mean'):.2f}",
            flush=True,
        )
        print(f"GAME {season} variant-minus-base {_fmt(game)}", flush=True)
        print(
            f"TIER {season} top {_tier_line(right, 'crps_top', 'crps_top_n')} "
            f"starter {_tier_line(right, 'crps_start', 'crps_start_n')} "
            f"bench {_tier_line(right, 'crps_bench', 'crps_bench_n')}",
            flush=True,
        )
        print(f"COND UNDER {season} before {_cond_line(left)}", flush=True)
        print(f"COND UNDER {season} after {_cond_line(right)}", flush=True)
        print(f"COND OVER {season} before {_over_line(left)}", flush=True)
        print(f"COND OVER {season} after {_over_line(right)}", flush=True)
        (var_dir / "paired.json").write_text(
            json.dumps(
                {"player": player, "bust": bust, "game": game, "bias_before": bias[0], "bias_after": bias[1]},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        bias_ok = abs(bias[1]) < abs(bias[0]) - 0.05
        season_ok = (
            bias_ok
            and _better(player["crps_pts"])
            and _better(bust)
            and _not_worse(game["brier"])
            and _not_worse(game["mae_margin"])
            and _not_worse(game["mae_total"])
        )
        if not season_ok:
            print(f"CALL star_anchor REVERT after {season} bias_ok={bias_ok}", flush=True)
            print("STAR ANCHOR DECISION DONE", flush=True)
            return
    print("CALL star_anchor KEEP", flush=True)
    print("STAR ANCHOR DECISION DONE", flush=True)


if __name__ == "__main__":
    main()
