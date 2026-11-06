"""Decision run for the March-April stack.

The 20% return blend and the March-April bench seat were each kept on
their own. March and April currently run both. That pair was not measured.
October through February are the blend alone either way, so this comparison
is the seat on top of the blend.

Baseline is the 20% blend with the seat off. Difference is stack minus
blend. Reconcile first. The mid-season window does not include March or
April. This script does not edit config.yaml.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.bootstrap import paired_bootstrap, paired_player_bootstrap
from nba_sim.settings import load_settings
from scripts.crps_decision import _bins, _config, _fmt
from scripts.fringe_decision import SEASONS, _guardrail, _load, _out, _run
from scripts.lineup_decision import _call

STEP = "stack"
BASE = "mild_return_20"


def _stack(settings) -> dict:
    return _config(
        settings,
        {
            "minutes": {"return_minute_blend": True, "return_blend_scale": 0.20},
            "features": {"late_season_incentives": True},
        },
    )


def main() -> None:
    settings = load_settings(ROOT)
    stack = _stack(settings)
    minutes = stack["minutes"]
    if not minutes.get("return_minute_blend") or float(minutes.get("return_blend_scale", 0)) != 0.20:
        raise SystemExit("stack run must be the 20% return blend")
    if not stack.get("features", {}).get("late_season_incentives"):
        raise SystemExit("stack run must turn the March-April seat on")
    if stack.get("minutes", {}).get("fringe_minute_floor"):
        raise SystemExit("stack run must not turn the fringe floor on")
    for season in SEASONS:
        base = _out(season, BASE) / "games.parquet"
        if not base.exists():
            raise SystemExit(f"missing blend baseline {base}")
    print("RECONCILE return blend 20% plus March-April seat", flush=True)
    _guardrail(settings, stack)
    for season in SEASONS:
        out = _out(season, STEP)
        row = _run(settings, stack, season, out)
        print(
            f"SCORES {out.name} CRPS min {row.get('crps_min')} "
            f"CRPS pts {row.get('crps_pts')} play {row.get('play_brier')} "
            f"spread {row.get('mae_margin')} total {row.get('mae_total')} "
            f"brier {row.get('brier_win')}",
            flush=True,
        )
        print(f"PLAY BINS {out.name} {_bins(row)}", flush=True)
    player: dict[str, dict] = {}
    game: dict[str, dict] = {}
    for season in SEASONS:
        base = _out(season, BASE) / "games.parquet"
        variant = _out(season, STEP) / "games.parquet"
        player[season] = paired_player_bootstrap(_load(base), _load(variant), n_boot=2000, seed=1)
        game[season] = paired_bootstrap(_load(base), _load(variant), n_boot=2000, seed=1)
        print(f"PLAYER {STEP} {season} stack-minus-blend {_fmt(player[season])}", flush=True)
        print(f"GAME {STEP} {season} stack-minus-blend {_fmt(game[season])}", flush=True)
    print(f"CALL {STEP} {_call(player, game)}", flush=True)
    print("STACK DECISION DONE", flush=True)


if __name__ == "__main__":
    main()
