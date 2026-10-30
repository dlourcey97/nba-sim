"""Decision-run rules: holdout season and bootstrap intervals."""

from __future__ import annotations

import numpy as np

from backtest.bootstrap import paired_bootstrap
from backtest.tune import HOLDOUT_SEASON, main as tune_main


def _games(prob: float, margin_error: float, total_error: float, n: int = 40) -> list[dict]:
    rows = []
    for index in range(n):
        rows.append(
            {
                "game_id": f"g{index}",
                "home_win_prob": prob,
                "home_win": 1.0 if index % 2 == 0 else 0.0,
                "pred_margin": 0.0,
                "act_margin": margin_error if index % 2 == 0 else -margin_error,
                "pred_total": 220.0,
                "act_total": 220.0 + (total_error if index % 2 == 0 else -total_error),
            }
        )
    return rows


def test_identical_runs_are_inside_the_noise() -> None:
    rows = _games(0.6, 8.0, 12.0)
    result = paired_bootstrap(rows, rows, n_boot=2000, seed=1)
    for name in ("brier", "mae_margin", "mae_total"):
        assert result[name]["diff"] == 0.0
        assert result[name]["low"] <= 0.0 <= result[name]["high"]
        assert result[name]["decisive"] is False


def test_a_large_total_shift_is_outside_the_noise() -> None:
    base = _games(0.55, 10.0, 5.0, n=80)
    worse = []
    for row in base:
        copied = dict(row)
        copied["pred_total"] = float(row["pred_total"]) + 30.0
        worse.append(copied)
    result = paired_bootstrap(base, worse, n_boot=2000, seed=1)
    assert result["mae_total"]["diff"] > 20.0
    assert result["mae_total"]["low"] > 0.0
    assert result["mae_total"]["decisive"] is True
    assert result["brier"]["decisive"] is False


def test_tune_refuses_the_holdout_season() -> None:
    code = tune_main(["--seasons", HOLDOUT_SEASON, "--max-games", "1", "--runs", "1"])
    assert code == 2


def test_bootstrap_uses_the_paired_game_ids() -> None:
    left = _games(0.5, 1.0, 1.0, n=5)
    right = _games(0.5, 1.0, 1.0, n=5)
    right[0]["game_id"] = "missing"
    result = paired_bootstrap(left, right, n_boot=100, seed=1)
    assert result["brier"]["games"] == 4
    assert np.isfinite(result["mae_margin"]["diff"])
