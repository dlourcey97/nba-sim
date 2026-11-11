"""Decision run for the budget lineup and separate star noise.

Before draws one independent top five each quarter and uses one shooting
and usage SD for every player. After spends each quarter's minutes in four
substints, and high-usage players get a tighter SD than the bench.
Both seasons, 1,000 sims, seed 1, four workers. The paired interval is
after minus before.
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

from backtest.bootstrap import paired_bootstrap
from scripts.fringe_decision import SEASONS, _guardrail, _load, _out, _run

from nba_sim.settings import load_settings


def _config(settings, *, budget: bool) -> dict:
    config = copy.deepcopy(settings.config)
    sim = config["simulation"]
    if budget:
        sim["lineup_model"] = "budget"
        sim["lineup_substints"] = 4
        sim["lineup_budget_noise"] = 0.40
        sim["player_shoot_sd"] = 0.32
        sim["player_usage_sd"] = 0.28
        sim["star_usage_min"] = 0.24
        sim["star_shoot_sd"] = 0.14
        sim["star_usage_sd"] = 0.10
    else:
        sim["lineup_model"] = "gumbel"
        sim["player_shoot_sd"] = 0.32
        sim["player_usage_sd"] = 0.28
        sim["star_usage_min"] = 0.24
        sim["star_shoot_sd"] = 0.32
        sim["star_usage_sd"] = 0.28
    config["context"]["dunks_fallback_log"] = False
    return config


def main() -> None:
    settings = load_settings()
    before = _config(settings, budget=False)
    after = _config(settings, budget=True)
    print("GUARDRAIL after", flush=True)
    try:
        _guardrail(settings, after)
    except SystemExit as exc:
        print(f"GUARDRAIL FAILED {exc}", flush=True)
    for season in SEASONS:
        _run(replace(settings, config=before), before, season, _out(season, "lineup_before"))
        _run(replace(settings, config=after), after, season, _out(season, "lineup_after"))
        boot = paired_bootstrap(
            _load(_out(season, "lineup_before") / "games.parquet"),
            _load(_out(season, "lineup_after") / "games.parquet"),
            n_boot=2000,
            seed=1,
        )
        print(f"PAIRED {season} after-minus-before {boot}", flush=True)
        (_out(season, "lineup_after") / "paired.json").write_text(
            json.dumps(boot, indent=2) + "\n",
            encoding="utf-8",
        )
    print("LINEUP DECISION DONE", flush=True)


if __name__ == "__main__":
    main()
