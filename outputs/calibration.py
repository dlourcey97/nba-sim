"""Probability calibration for prop lines. Fitted off the sim, applied after it."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOTS_PATH = ROOT / "outputs" / "calibration_knots.json"

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "pra")
TIERS = ("top", "starter", "bench")
STRONG_EDGE = 0.05
WEAK_EDGE = 0.08


@dataclass(frozen=True)
class CalibrationCell:
    stat: str
    tier: str
    xs: tuple[float, ...]
    ys: tuple[float, ...]
    quality: str
    holdout_n: int
    holdout_bias: float
    fit_n: int

    def adjust(self, probability: float) -> float:
        if self.quality == "unusable" or len(self.xs) < 2:
            return probability
        return _interp(self.xs, self.ys, probability)


@dataclass(frozen=True)
class CalibrationTable:
    cells: dict[tuple[str, str], CalibrationCell]
    source: str

    def cell(self, stat: str, tier: str) -> CalibrationCell:
        found = self.cells.get((stat, tier))
        if found is not None:
            return found
        return CalibrationCell(stat, tier, (), (), "unusable", 0, 0.0, 0)

    def adjust(self, stat: str, tier: str, probability: float) -> float:
        return self.cell(stat, tier).adjust(probability)

    def edge_floor(self, stat: str, tier: str) -> float:
        quality = self.cell(stat, tier).quality
        if quality == "strong":
            return STRONG_EDGE
        return WEAK_EDGE

    def star_points_ok(self) -> bool:
        cell = self.cell("pts", "top")
        return cell.quality == "strong" and abs(cell.holdout_bias) <= 0.04


def load_calibration(path: Path | None = None) -> CalibrationTable:
    target = path or KNOTS_PATH
    if not target.is_file():
        return _default_table("no holdout fit yet")
    payload = json.loads(target.read_text(encoding="utf-8"))
    cells: dict[tuple[str, str], CalibrationCell] = {}
    for row in payload.get("cells") or []:
        cell = CalibrationCell(
            stat=str(row["stat"]),
            tier=str(row["tier"]),
            xs=tuple(float(value) for value in row.get("xs") or ()),
            ys=tuple(float(value) for value in row.get("ys") or ()),
            quality=str(row.get("quality") or "unusable"),
            holdout_n=int(row.get("holdout_n") or 0),
            holdout_bias=float(row.get("holdout_bias") or 0.0),
            fit_n=int(row.get("fit_n") or 0),
        )
        cells[(cell.stat, cell.tier)] = cell
    return CalibrationTable(cells=cells, source=str(payload.get("source") or target.name))


def _default_table(source: str) -> CalibrationTable:
    """Identity map. Star points stay off until a holdout fit says the bias is gone."""
    cells = {}
    for stat in STATS:
        for tier in TIERS:
            quality = "unusable" if stat == "pts" and tier == "top" else "strong"
            cells[(stat, tier)] = CalibrationCell(stat, tier, (), (), quality, 0, 0.0, 0)
    return CalibrationTable(cells=cells, source=source)


def fit_isotonic(pairs: list[tuple[float, float]]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Pool-adjacent-violators on (predicted probability, outcome)."""
    if len(pairs) < 2:
        return (), ()
    ordered = sorted(pairs, key=lambda item: item[0])
    blocks: list[list[float]] = []
    for pred, outcome in ordered:
        blocks.append([float(pred), float(outcome), 1.0])
        while len(blocks) >= 2 and _mean(blocks[-2]) > _mean(blocks[-1]) + 1e-12:
            left, right = blocks[-2], blocks[-1]
            weight = left[2] + right[2]
            blocks[-2] = [
                (left[0] * left[2] + right[0] * right[2]) / weight,
                (left[1] * left[2] + right[1] * right[2]) / weight,
                weight,
            ]
            blocks.pop()
    xs = tuple(min(max(block[0], 0.02), 0.98) for block in blocks)
    ys = tuple(min(max(block[1], 0.02), 0.98) for block in blocks)
    return xs, ys


def reliability(pairs: list[tuple[float, float]], xs: tuple[float, ...], ys: tuple[float, ...]) -> dict[str, float]:
    if not pairs:
        return {"n": 0, "brier_raw": float("nan"), "brier_cal": float("nan"), "bias": float("nan")}
    raw = 0.0
    cal = 0.0
    bias = 0.0
    for pred, outcome in pairs:
        adjusted = _interp(xs, ys, pred) if len(xs) >= 2 else pred
        raw += (pred - outcome) ** 2
        cal += (adjusted - outcome) ** 2
        bias += adjusted - outcome
    n = float(len(pairs))
    return {"n": n, "brier_raw": raw / n, "brier_cal": cal / n, "bias": bias / n}


def judge_quality(holdout: dict[str, float]) -> str:
    n = holdout["n"]
    if n < 80 or holdout["brier_cal"] != holdout["brier_cal"]:
        return "unusable"
    if holdout["brier_cal"] > holdout["brier_raw"] + 0.01:
        return "unusable"
    if n >= 200 and holdout["brier_cal"] <= holdout["brier_raw"] + 0.005 and abs(holdout["bias"]) <= 0.04:
        return "strong"
    return "weak"


def _mean(block: list[float]) -> float:
    return block[1]


def _interp(xs: tuple[float, ...], ys: tuple[float, ...], probability: float) -> float:
    if not xs:
        return probability
    if probability <= xs[0]:
        return ys[0]
    if probability >= xs[-1]:
        return ys[-1]
    for left, right in zip(range(len(xs) - 1), range(1, len(xs))):
        if xs[left] <= probability <= xs[right]:
            span = xs[right] - xs[left]
            if span <= 1e-9:
                return ys[right]
            t = (probability - xs[left]) / span
            return ys[left] + t * (ys[right] - ys[left])
    return ys[-1]
