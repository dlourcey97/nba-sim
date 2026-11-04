"""Paired game-level bootstrap for keep/revert decisions.

A difference in Brier, spread MAE, or total MAE counts only when the 95%
interval on the paired difference excludes zero. Games are resampled with
replacement; the two runs stay aligned on game id.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np

DECISION_METRICS = ("brier", "mae_margin", "mae_total")
# Player scores are totals and counts, so a resample stays weighted by players.
PLAYER_METRICS = ("crps_min", "crps_pts", "play_brier", "cover_min", "cover_pts")


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


def _ratio(total: np.ndarray, count: np.ndarray) -> float:
    denom = float(count.sum())
    if denom <= 0.0:
        return float("nan")
    return float(total.sum() / denom)


def paired_player_bootstrap(
    left: Iterable[dict],
    right: Iterable[dict],
    *,
    n_boot: int = 2000,
    seed: int = 1,
) -> dict[str, dict[str, float]]:
    """Player-weighted difference, right minus left. Lower CRPS and play Brier are better.

    Coverage differences are right minus left too; higher coverage is better,
    so a negative coverage interval is a worse distribution.
    """
    pairs = _aligned(left, right)
    if not pairs:
        raise ValueError("no games in common")
    specs = {
        "crps_min": ("crps_min_sum", "played_n"),
        "crps_pts": ("crps_pts_sum", "played_n"),
        "play_brier": ("play_brier_sum", "play_n"),
        "cover_min": ("cover_min_hits", "played_n"),
        "cover_pts": ("cover_pts_hits", "played_n"),
    }
    columns: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
    for name, (total_key, count_key) in specs.items():
        columns[name] = (
            np.array([float(row.get(total_key) or 0.0) for row, _ in pairs], dtype=float),
            np.array([float(row.get(count_key) or 0.0) for row, _ in pairs], dtype=float),
            np.array([float(row.get(total_key) or 0.0) for _, row in pairs], dtype=float),
            np.array([float(row.get(count_key) or 0.0) for _, row in pairs], dtype=float),
        )
    observed = {
        name: _ratio(right_total, right_count) - _ratio(left_total, left_count)
        for name, (left_total, left_count, right_total, right_count) in columns.items()
    }
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(pairs), size=(n_boot, len(pairs)))
    out: dict[str, dict[str, float]] = {}
    for name, (left_total, left_count, right_total, right_count) in columns.items():
        diffs = (
            right_total[draws].sum(axis=1) / np.maximum(right_count[draws].sum(axis=1), 1e-9)
            - left_total[draws].sum(axis=1) / np.maximum(left_count[draws].sum(axis=1), 1e-9)
        )
        lo, hi = np.quantile(diffs, [0.025, 0.975])
        out[name] = {
            "diff": float(observed[name]),
            "low": float(lo),
            "high": float(hi),
            "decisive": bool(lo > 0.0 or hi < 0.0),
            "games": float(len(pairs)),
        }
    return out
