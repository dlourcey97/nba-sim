"""Paired game-level bootstrap for keep/revert decisions.

A difference in Brier, spread MAE, or total MAE counts only when the 95%
interval on the paired difference excludes zero. Games are resampled with
replacement; the two runs stay aligned on game id.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np

DECISION_METRICS = ("brier", "mae_margin", "mae_total")


def _aligned(left: Iterable[dict], right: Iterable[dict]) -> list[tuple[dict, dict]]:
    right_by_id = {str(row["game_id"]): row for row in right}
    pairs = []
    for row in left:
        other = right_by_id.get(str(row["game_id"]))
        if other is not None:
            pairs.append((row, other))
    return pairs


def _components(row: dict) -> tuple[float, float, float]:
    prob = float(row["home_win_prob"])
    outcome = float(row["home_win"])
    return (
        (prob - outcome) ** 2,
        abs(float(row["pred_margin"]) - float(row["act_margin"])),
        abs(float(row["pred_total"]) - float(row["act_total"])),
    )


def paired_bootstrap(
    left: Iterable[dict],
    right: Iterable[dict],
    *,
    n_boot: int = 10000,
    seed: int = 1,
) -> dict[str, dict[str, float]]:
    """Difference is right minus left. Interval is the 2.5 and 97.5 percentiles."""
    pairs = _aligned(left, right)
    if not pairs:
        raise ValueError("no games in common")
    left_m = np.array([_components(row)[0] for row, _ in pairs], dtype=float)
    right_m = np.array([_components(row)[0] for _, row in pairs], dtype=float)
    left_s = np.array([_components(row)[1] for row, _ in pairs], dtype=float)
    right_s = np.array([_components(row)[1] for _, row in pairs], dtype=float)
    left_t = np.array([_components(row)[2] for row, _ in pairs], dtype=float)
    right_t = np.array([_components(row)[2] for _, row in pairs], dtype=float)
    observed = {
        "brier": float(right_m.mean() - left_m.mean()),
        "mae_margin": float(right_s.mean() - left_s.mean()),
        "mae_total": float(right_t.mean() - left_t.mean()),
    }
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(pairs), size=(n_boot, len(pairs)))
    diffs = {
        "brier": right_m[draws].mean(axis=1) - left_m[draws].mean(axis=1),
        "mae_margin": right_s[draws].mean(axis=1) - left_s[draws].mean(axis=1),
        "mae_total": right_t[draws].mean(axis=1) - left_t[draws].mean(axis=1),
    }
    out: dict[str, dict[str, float]] = {}
    for name in DECISION_METRICS:
        lo, hi = np.quantile(diffs[name], [0.025, 0.975])
        out[name] = {
            "diff": observed[name],
            "low": float(lo),
            "high": float(hi),
            "decisive": bool(lo > 0.0 or hi < 0.0),
            "games": float(len(pairs)),
        }
    return out
