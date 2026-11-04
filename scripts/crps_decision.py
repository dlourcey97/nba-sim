"""Re-judge the four minute fixes on distribution scores.

Baseline is the current engine: honest scoring, pre-debut stints on, the
15-man cap on, fringe floor off, return blend off, March-April seat off.
Each fix is one change against that baseline. A player who played and was
not projected is a point mass at 0. Lower CRPS and play Brier are better.

This does not flip config flags. The reconcile guardrail is not re-run:
cap removal, the fringe floor, and the return blend already fail it, and
daily.py would refuse a slate if those flags were turned on.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.bootstrap import paired_bootstrap, paired_player_bootstrap
from nba_sim.settings import load_settings
from scripts.fringe_decision import SEASONS, _load, _out, _run

VARIANTS = (
    ("crps_base", {}),
    ("crps_fringe", {"minutes": {"fringe_minute_floor": True}}),
    ("crps_return", {"minutes": {"return_minute_blend": True}}),
    ("crps_cap", {"minutes": {"historical_roster_cap": 0}}),
    ("crps_late", {"features": {"late_season_incentives": True}}),
)


def _config(settings, overrides: dict) -> dict:
    config = copy.deepcopy(settings.config)
    config.setdefault("context", {})["dunks_fallback_log"] = False
    config["minutes"]["historical_roster_cap"] = 15
    config["minutes"]["fringe_minute_floor"] = False
    config["minutes"]["return_minute_blend"] = False
    config["minutes"]["pre_debut_stint"] = True
    config.setdefault("features", {})["late_season_incentives"] = False
    for section, values in overrides.items():
        config.setdefault(section, {}).update(values)
    return config


def _better(row: dict) -> bool:
    return bool(row["decisive"] and row["high"] < 0.0)


def _worse(row: dict) -> bool:
    return bool(row["decisive"] and row["low"] > 0.0)


def _fmt(boot: dict) -> str:
    parts = []
    for metric, row in boot.items():
        parts.append(
            f"{metric}: {row['diff']:+.4f} [{row['low']:+.4f}, {row['high']:+.4f}] "
            f"{'decisive' if row['decisive'] else 'inside noise'}"
        )
    return "; ".join(parts)


def _bins(payload: dict) -> str:
    parts = []
    for row in payload.get("play_bins") or []:
        count = int(row.get("count") or 0)
        if not count:
            continue
        parts.append(
            f"{row['bin_left']:.1f}-{row['bin_right']:.1f} "
            f"pred {row['pred_mean']:.3f} actual {row['actual_freq']:.3f} n {count}"
        )
    return " | ".join(parts)


def _call(player: dict[str, dict], game: dict[str, dict]) -> str:
    crps_worse = any(
        _worse(boot["crps_min"]) or _worse(boot["crps_pts"]) or _worse(boot["play_brier"])
        for boot in player.values()
    )
    crps_clear = all(
        (_better(boot["crps_min"]) or _better(boot["crps_pts"]))
        and not _worse(boot["crps_min"])
        and not _worse(boot["crps_pts"])
        and _better(boot["play_brier"])
        for boot in player.values()
    )
    game_worse = any(
        _worse(boot["brier"]) or _worse(boot["mae_margin"]) or _worse(boot["mae_total"])
        for boot in game.values()
    )
    if crps_worse or game_worse or not crps_clear:
        return "REVERT"
    return "KEEP"


def main() -> None:
    settings = load_settings(ROOT)
    payloads: dict[tuple[str, str], dict] = {}
    for step, overrides in VARIANTS:
        config = _config(settings, overrides)
        for season in SEASONS:
            out = _out(season, step)
            payloads[(step, season)] = _run(settings, config, season, out)
            row = payloads[(step, season)]
            print(
                f"SCORES {out.name} CRPS min {row.get('crps_min')} "
                f"CRPS pts {row.get('crps_pts')} play {row.get('play_brier')} "
                f"cover min {row.get('coverage_min_10_90')} "
                f"cover pts {row.get('coverage_pts_10_90')} "
                f"MAE min {row.get('mae_min')}",
                flush=True,
            )
            print(f"PLAY BINS {out.name} {_bins(row)}", flush=True)

    for step, _overrides in VARIANTS[1:]:
        player: dict[str, dict] = {}
        game: dict[str, dict] = {}
        for season in SEASONS:
            base = _out(season, "crps_base") / "games.parquet"
            variant = _out(season, step) / "games.parquet"
            player[season] = paired_player_bootstrap(_load(base), _load(variant), n_boot=2000, seed=1)
            game[season] = paired_bootstrap(_load(base), _load(variant), n_boot=2000, seed=1)
            print(f"PLAYER {step} {season} variant-minus-base {_fmt(player[season])}", flush=True)
            print(f"GAME {step} {season} variant-minus-base {_fmt(game[season])}", flush=True)
        print(f"CALL {step} {_call(player, game)}", flush=True)
    print("CRPS DECISION DONE", flush=True)


if __name__ == "__main__":
    main()
