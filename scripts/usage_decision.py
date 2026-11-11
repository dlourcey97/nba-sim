"""Decision run for box-usage alignment.

Before is the old path: play-by-play usage, a 0.45 EPM ceiling, and usage
scaled by tonight's point line. After is pace × minutes and the box line,
a 0.60 ceiling, and no point-line scale. Both seasons, 1,000 sims, seed 1,
four workers. The paired interval is after minus before.
"""

from __future__ import annotations

import copy
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


def _config(settings, *, align: bool, cap: float, scale_points: bool) -> dict:
    config = copy.deepcopy(settings.config)
    config["blending"]["align_box_usage"] = align
    config["context"]["dunks_usage_hi"] = cap
    config["context"]["dunks_scale_usage_by_points"] = scale_points
    config["context"]["dunks_fallback_log"] = False
    return config


def main() -> None:
    settings = load_settings()
    before = _config(settings, align=False, cap=0.45, scale_points=True)
    after = _config(settings, align=True, cap=0.60, scale_points=False)
    print("GUARDRAIL after", flush=True)
    try:
        _guardrail(settings, after)
    except SystemExit as exc:
        print(f"GUARDRAIL FAILED {exc}", flush=True)
    for season in SEASONS:
        _run(replace(settings, config=before), before, season, _out(season, "usage_before"))
        _run(replace(settings, config=after), after, season, _out(season, "usage_after"))
        boot = paired_bootstrap(
            _load(_out(season, "usage_before") / "games.parquet"),
            _load(_out(season, "usage_after") / "games.parquet"),
            n_boot=2000,
            seed=1,
        )
        print(f"PAIRED {season} after-minus-before {boot}", flush=True)
        (_out(season, "usage_after") / "paired.json").write_text(
            __import__("json").dumps(boot, indent=2) + "\n",
            encoding="utf-8",
        )
    print("USAGE DECISION DONE", flush=True)


if __name__ == "__main__":
    main()
