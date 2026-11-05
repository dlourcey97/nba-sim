"""Decision run for help defense.

The other four defenders move make rate as a residual against the team's
usual defenders. The primary is unchanged and is not counted again. Lineup
defense and matchup shares stay off. Reconcile first. This script does not
edit config.yaml.
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

STEP = "help"


def main() -> None:
    settings = load_settings(ROOT)
    base_cfg = _config(settings, {})
    on_cfg = _config(settings, {"context": {"help_defense_enabled": True}})
    if base_cfg.get("context", {}).get("help_defense_enabled"):
        raise SystemExit("baseline config has help defense on")
    if on_cfg.get("context", {}).get("lineup_defense_enabled"):
        raise SystemExit("help run must not stack lineup defense")
    if on_cfg.get("context", {}).get("matchup_shares_enabled"):
        raise SystemExit("help run must not stack matchup shares")
    print("RECONCILE help defense on", flush=True)
    _guardrail(settings, on_cfg)
    for season in SEASONS:
        out = _out(season, STEP)
        row = _run(settings, on_cfg, season, out)
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
        print(f"PLAYER {STEP} {season} variant-minus-base {_fmt(player[season])}", flush=True)
        print(f"GAME {STEP} {season} variant-minus-base {_fmt(game[season])}", flush=True)
    print(f"CALL {STEP} {_call(player, game)}", flush=True)
    print("HELP DECISION DONE", flush=True)


if __name__ == "__main__":
    main()
