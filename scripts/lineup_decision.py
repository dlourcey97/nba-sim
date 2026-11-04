"""Decision run for on-court six-factor lineup defense.

Reconcile first (mid-season 2025-26, 80 games, 80 sims, skip 400, seed 1,
±3%). A failure stops the script before the long seasons. The long run is
2025-26 and the 2024-25 holdout, 1,000 sims, seed 1, four workers. The
baseline is the CRPS re-score base (same engine, flag off). Difference is
lineup minus base. This script does not flip config.yaml.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.bootstrap import paired_bootstrap, paired_player_bootstrap
from nba_sim.settings import load_settings
from scripts.crps_decision import _bins, _config, _fmt
from scripts.fringe_decision import SEASONS, _guardrail, _load, _out, _run

STEP = "lineup"


def _lineup_config(settings) -> dict:
    config = _config(settings, {"context": {"lineup_defense_enabled": True}})
    return config


def _better(row: dict) -> bool:
    return bool(row["decisive"] and row["high"] < 0.0)


def _worse(row: dict) -> bool:
    return bool(row["decisive"] and row["low"] > 0.0)


def _call(player: dict[str, dict], game: dict[str, dict]) -> str:
    """Drop a decisive loss. Keep a decisive gain on both seasons. Else noise."""
    watched = ("crps_min", "crps_pts")
    game_keys = ("brier", "mae_margin", "mae_total")
    worse = False
    better = {season: False for season in player}
    for season, boot in player.items():
        for key in watched:
            if _worse(boot[key]):
                worse = True
            if _better(boot[key]):
                better[season] = True
    for season, boot in game.items():
        for key in game_keys:
            if _worse(boot[key]):
                worse = True
            if _better(boot[key]):
                better[season] = True
    if worse:
        return "DROP"
    if all(better.values()):
        return "KEEP"
    return "NOISE"


def main() -> None:
    settings = load_settings(ROOT)
    base_cfg = _config(settings, {})
    on_cfg = _lineup_config(settings)
    if base_cfg.get("context", {}).get("lineup_defense_enabled"):
        raise SystemExit("baseline config has lineup defense on")
    print("RECONCILE lineup defense on", flush=True)
    _guardrail(settings, on_cfg)
    payloads = {}
    for season in SEASONS:
        base_metrics = _out(season, "crps_base") / "metrics.json"
        if not base_metrics.exists():
            print(f"BASE missing; running {season} crps_base", flush=True)
            _run(settings, base_cfg, season, _out(season, "crps_base"))
        out = _out(season, STEP)
        payloads[season] = _run(settings, on_cfg, season, out)
        row = payloads[season]
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
        base = _out(season, "crps_base") / "games.parquet"
        variant = _out(season, STEP) / "games.parquet"
        player[season] = paired_player_bootstrap(_load(base), _load(variant), n_boot=2000, seed=1)
        game[season] = paired_bootstrap(_load(base), _load(variant), n_boot=2000, seed=1)
        print(f"PLAYER {STEP} {season} lineup-minus-base {_fmt(player[season])}", flush=True)
        print(f"GAME {STEP} {season} lineup-minus-base {_fmt(game[season])}", flush=True)
    print(f"CALL {STEP} {_call(player, game)}", flush=True)
    print("LINEUP DECISION DONE", flush=True)


if __name__ == "__main__":
    main()
