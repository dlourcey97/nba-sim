"""Backtest metric helpers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class MetricReport:
    games: int
    player_rows: int
    brier_win: float
    log_loss_win: float
    mae_pts: float
    mae_reb: float
    mae_ast: float
    mae_fg3m: float
    mae_min: float
    crps_pts: float
    pit_pts_mean: float
    coverage_10_90: float
    calibration_bins: list[dict[str, float]]
    sim_ppg: float = float("nan")
    actual_ppg: float = float("nan")
    sim_possessions: float = float("nan")
    actual_possessions: float = float("nan")
    mae_margin: float = float("nan")
    mae_total: float = float("nan")
    winner_accuracy: float = float("nan")

    def as_dict(self) -> dict:
        return {
            "games": self.games,
            "player_rows": self.player_rows,
            "brier_win": _json_float(self.brier_win),
            "log_loss_win": _json_float(self.log_loss_win),
            "winner_accuracy": _json_float(self.winner_accuracy),
            "mae_pts": _json_float(self.mae_pts),
            "mae_reb": _json_float(self.mae_reb),
            "mae_ast": _json_float(self.mae_ast),
            "mae_fg3m": _json_float(self.mae_fg3m),
            "mae_min": _json_float(self.mae_min),
            "mae_margin": _json_float(self.mae_margin),
            "mae_total": _json_float(self.mae_total),
            "crps_pts": _json_float(self.crps_pts),
            "pit_pts_mean": _json_float(self.pit_pts_mean),
            "coverage_10_90": _json_float(self.coverage_10_90),
            "sim_ppg": _json_float(self.sim_ppg),
            "actual_ppg": _json_float(self.actual_ppg),
            "sim_possessions": _json_float(self.sim_possessions),
            "actual_possessions": _json_float(self.actual_possessions),
            "calibration_bins": [
                {key: _json_float(value) for key, value in row.items()}
                for row in self.calibration_bins
            ],
        }


def _json_float(value: float):
    if value != value:  # NaN
        return None
    return float(value)


def brier_score(probs: np.ndarray, outcomes: np.ndarray) -> float:
    if probs.size == 0:
        return float("nan")
    return float(np.mean((probs - outcomes) ** 2))


def log_loss(probs: np.ndarray, outcomes: np.ndarray, *, eps: float = 1e-15) -> float:
    """Binary cross-entropy for home-win probability."""
    if probs.size == 0:
        return float("nan")
    p = np.clip(np.asarray(probs, dtype=float), eps, 1.0 - eps)
    y = np.asarray(outcomes, dtype=float)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def mean_abs_error(pred: np.ndarray, actual: np.ndarray) -> float:
    if pred.size == 0:
        return float("nan")
    return float(np.mean(np.abs(pred - actual)))


def crps_from_samples(samples: np.ndarray, actual: float) -> float:
    """Empirical CRPS for one observation given Monte Carlo samples.

    CRPS = E|X - y| - 0.5 E|X - X'|. Lower is better.
    """
    xs = np.asarray(samples, dtype=float).ravel()
    n = xs.size
    if n == 0:
        return float("nan")
    mae = float(np.mean(np.abs(xs - float(actual))))
    ordered = np.sort(xs)
    # sum_{i,j} |x_i - x_j| / n^2  with 1-based ranks
    ranks = np.arange(1, n + 1, dtype=float)
    pairwise = (2.0 / (n * n)) * float(np.sum((2.0 * ranks - n - 1.0) * ordered))
    return mae - 0.5 * pairwise


def pit_from_samples(samples: np.ndarray, actual: float) -> float:
    """Probability integral transform F_hat(y). Calibrated ⇒ ~Uniform(0,1)."""
    xs = np.asarray(samples, dtype=float).ravel()
    if xs.size == 0:
        return float("nan")
    return float(np.mean(xs <= float(actual)))


def percentile_coverage(actual: np.ndarray, p10: np.ndarray, p90: np.ndarray) -> float:
    if actual.size == 0:
        return float("nan")
    inside = (actual >= p10) & (actual <= p90)
    return float(np.mean(inside))


def calibration_bins(
    probs: np.ndarray,
    outcomes: np.ndarray,
    *,
    n_bins: int = 10,
) -> list[dict[str, float]]:
    if probs.size == 0:
        return []
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows: list[dict[str, float]] = []
    for index in range(n_bins):
        lo, hi = edges[index], edges[index + 1]
        if index == n_bins - 1:
            mask = (probs >= lo) & (probs <= hi)
        else:
            mask = (probs >= lo) & (probs < hi)
        count = int(mask.sum())
        if count == 0:
            rows.append(
                {
                    "bin_left": float(lo),
                    "bin_right": float(hi),
                    "count": 0.0,
                    "pred_mean": float("nan"),
                    "actual_freq": float("nan"),
                }
            )
            continue
        rows.append(
            {
                "bin_left": float(lo),
                "bin_right": float(hi),
                "count": float(count),
                "pred_mean": float(np.mean(probs[mask])),
                "actual_freq": float(np.mean(outcomes[mask])),
            }
        )
    return rows


def write_calibration_svg(bins: list[dict[str, float]], path) -> None:
    """Simple SVG scatter of predicted vs actual win frequency."""
    width, height = 480, 480
    pad = 50
    points = [
        (row["pred_mean"], row["actual_freq"])
        for row in bins
        if row["count"] > 0 and np.isfinite(row["pred_mean"]) and np.isfinite(row["actual_freq"])
    ]

    def xy(p: float, a: float) -> tuple[float, float]:
        x = pad + p * (width - 2 * pad)
        y = height - pad - a * (height - 2 * pad)
        return x, y

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="white"/>',
        f'<line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{pad}" stroke="#999" stroke-dasharray="4"/>',
        f'<line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}" stroke="#333"/>',
        f'<line x1="{pad}" y1="{height-pad}" x2="{pad}" y2="{pad}" stroke="#333"/>',
        f'<text x="{width/2}" y="{height-15}" text-anchor="middle" font-size="12">predicted home win prob</text>',
        f'<text x="15" y="{height/2}" text-anchor="middle" font-size="12" transform="rotate(-90 15 {height/2})">actual home win freq</text>',
    ]
    for pred, actual in points:
        x, y = xy(pred, actual)
        lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#1d4ed8"/>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
