"""Minutes projection with injury caps, foul trouble, and blowout variance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence

import numpy as np

from projections.blend import SeasonBundle


@dataclass(frozen=True)
class MinutesProjection:
    mean: float
    sd: float
    min_minutes: float
    max_minutes: float
    out: bool

    def sample(self, rng: np.random.Generator, size: int = 1) -> np.ndarray:
        if self.out or self.mean <= 0:
            return np.zeros(size, dtype=float)
        draws = rng.normal(self.mean, self.sd, size=size)
        return np.clip(draws, self.min_minutes, self.max_minutes)


def recent_minutes(
    bundles: Sequence[SeasonBundle],
    *,
    player_id: int,
    team_id: int,
    as_of: date,
    current_season: str,
    window: int = 10,
) -> tuple[float, float, list[date]]:
    """Return mean minutes, sample sd, and prior game dates for rest calc."""
    values: list[float] = []
    dates: list[date] = []
    for bundle in bundles:
        if bundle.season != current_season and values:
            continue
        rows = [
            row
            for row in bundle.logs_by_player.get(player_id, [])
            if row["game_date"] < as_of and int(row["team_id"]) == team_id
        ]
        for row in rows:
            values.append(float(row["minutes"] or 0.0))
            dates.append(row["game_date"])
    if not values:
        # Fall back to any team in the window.
        for bundle in bundles:
            rows = [
                row
                for row in bundle.logs_by_player.get(player_id, [])
                if row["game_date"] < as_of
            ]
            for row in rows:
                values.append(float(row["minutes"] or 0.0))
                dates.append(row["game_date"])
    if not values:
        return 0.0, 0.0, []
    recent = values[-window:]
    mean = float(sum(recent) / len(recent))
    if len(recent) == 1:
        sd = 4.0
    else:
        sd = float(np.std(recent, ddof=1))
    return mean, sd, dates


def project_minutes(
    *,
    base_mean: float,
    base_sd: float,
    config: dict[str, Any],
    status: str | None,
    minutes_cap: float | None,
    started: bool,
) -> MinutesProjection:
    minutes_cfg = config["minutes"]
    min_minutes = float(minutes_cfg["min_minutes"])
    max_minutes = float(minutes_cfg["max_minutes"])
    variance = float(minutes_cfg["minutes_variance"])
    foul_prior = float(minutes_cfg["foul_trouble_rate_prior"])

    status_norm = (status or "available").lower()
    if status_norm in {"out", "doubtful"}:
        return MinutesProjection(0.0, 0.0, 0.0, 0.0, True)

    mean = base_mean
    if status_norm == "questionable":
        mean *= 0.85
    elif status_norm == "probable":
        mean *= 0.95
    if not started and mean > 0:
        mean = min(mean, max(12.0, mean * 0.85))

    # Expected minutes lost to foul trouble / blowouts (applied to the mean).
    mean *= 1.0 - 0.5 * foul_prior
    if minutes_cap is not None:
        mean = min(mean, float(minutes_cap))
        max_minutes = min(max_minutes, float(minutes_cap))
    mean = float(np.clip(mean, min_minutes, max_minutes))
    sd = max(variance * 0.5, (base_sd if base_sd > 0 else variance))
    if minutes_cap is not None:
        sd = min(sd, max(1.0, float(minutes_cap) * 0.15))
    return MinutesProjection(mean, sd, min_minutes, max_minutes, False)
