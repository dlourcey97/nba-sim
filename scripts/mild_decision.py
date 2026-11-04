"""Decision runs for a milder fringe seat and a partial return blend.

The full fringe floor and the full return blend improved CRPS and failed the
±3% guardrail, so they stay off. Each family is tried from the strongest
candidate that might still pass reconcile. The first candidate that passes
gets the two-season run. A smaller dose is tried only when reconcile fails.
The two families are not stacked.

Baseline is the current engine, including pre-debut stints. Comparison is
against the CRPS baseline parquets. This script does not edit config.yaml.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.bootstrap import paired_bootstrap, paired_player_bootstrap
from scripts.crps_decision import _better, _config, _fmt, _worse
from scripts.fringe_decision import SEASONS, _guardrail, _load, _out, _run

# Strongest dose first. A later row runs only if the one above fails reconcile.
FRINGE = (
    (
        "mild_fringe",
        {
            "minutes": {
                "fringe_minute_floor": True,
                "fringe_floor_minutes": 2.0,
                "fringe_floor_play_prob": 0.10,
                "fringe_demote": False,
            }
        },
    ),
    (
        "mild_fringe_1",
        {
            "minutes": {
                "fringe_minute_floor": True,
                "fringe_floor_minutes": 1.0,
                "fringe_floor_play_prob": 0.08,
                "fringe_demote": False,
            }
        },
    ),
    (
        "mild_fringe_tiny",
        {
            "minutes": {
                "fringe_minute_floor": True,
                "fringe_floor_minutes": 1.0,
                "fringe_floor_play_prob": 0.05,
                "fringe_demote": False,
            }
        },
    ),
)
RETURN = (
    ("mild_return", {"minutes": {"return_minute_blend": True, "return_blend_scale": 0.35}}),
    ("mild_return_20", {"minutes": {"return_minute_blend": True, "return_blend_scale": 0.20}}),
    ("mild_return_10", {"minutes": {"return_minute_blend": True, "return_blend_scale": 0.10}}),
)


def _reconcile(settings, config: dict) -> bool:
    try:
        _guardrail(settings, config)
    except SystemExit as exc:
        print(exc, flush=True)
        return False
    return True


def _call(player: dict, game: dict) -> str:
    """CRPS must improve on both seasons. Game error and play Brier must not get worse."""
    crps_clear = all(
        (_better(boot["crps_min"]) or _better(boot["crps_pts"]))
        and not _worse(boot["crps_min"])
        and not _worse(boot["crps_pts"])
        and not _worse(boot["play_brier"])
        for boot in player.values()
    )
    game_worse = any(
        _worse(boot["brier"]) or _worse(boot["mae_margin"]) or _worse(boot["mae_total"])
        for boot in game.values()
    )
    if game_worse or not crps_clear:
        return "REVERT"
    return "KEEP"


def _decide(settings, step: str) -> str:
    player: dict = {}
    game: dict = {}
    for season in SEASONS:
        base = _out(season, "crps_base") / "games.parquet"
        variant = _out(season, step) / "games.parquet"
        player[season] = paired_player_bootstrap(_load(base), _load(variant), n_boot=2000, seed=1)
        game[season] = paired_bootstrap(_load(base), _load(variant), n_boot=2000, seed=1)
        print(f"PLAYER {step} {season} variant-minus-base {_fmt(player[season])}", flush=True)
        print(f"GAME {step} {season} variant-minus-base {_fmt(game[season])}", flush=True)
    call = _call(player, game)
    print(f"CALL {step} {call}", flush=True)
    return call


def _family(settings, name: str, candidates: tuple) -> None:
    for step, overrides in candidates:
        config = _config(settings, overrides)
        print(f"RECONCILE {step}", flush=True)
        if not _reconcile(settings, config):
            print(f"RECONCILE FAIL {step}", flush=True)
            continue
        print(f"RECONCILE PASS {step}", flush=True)
        for season in SEASONS:
            _run(settings, config, season, _out(season, step))
        _decide(settings, step)
        print(f"{name} DONE", flush=True)
        return
    print(f"{name} DROP no candidate passed reconcile", flush=True)


def main() -> None:
    from nba_sim.settings import load_settings

    settings = load_settings(ROOT)
    _family(settings, "FRINGE", FRINGE)
    _family(settings, "RETURN", RETURN)
    print("MILD DECISION DONE", flush=True)


if __name__ == "__main__":
    main()
