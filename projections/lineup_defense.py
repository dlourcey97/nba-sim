"""On-court defensive lineup effects from six-factor RAPM.

Each defender carries three prior-season components, in points per 100
possessions, shrunk toward zero when he has few possessions:

- ``tov``: positive means he forces more opponent turnovers
- ``ts``: positive means opponents shoot worse
- ``reb``: positive means his team rebounds more of opponent misses

The possession engine sums the five defenders on the floor and subtracts
five times the team's minutes-weighted mean. An average lineup therefore
adds nothing on top of team RAPM and the primary-defender factor. Only the
mix of who is actually out there moves turnovers, shooting, and rebounds.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ingest.rapm_fetch import _read_dataset_table, prior_season_end_year
from nba_sim.settings import Settings

# One point per 100 possessions, converted at ~1.1 points per turnover or shot.
_POINTS_PER_EVENT = 110.0


@dataclass(frozen=True)
class DefenseFactors:
    tov: float
    ts: float
    reb: float
    possessions: float


def shrink_component(value: float | None, possessions: float | None, prior: float) -> float:
    """Pull a low-sample rating toward zero. A missing rating is zero."""
    if value is None:
        return 0.0
    poss = max(0.0, float(possessions or 0.0))
    if poss <= 0.0 or prior < 0.0:
        return 0.0
    return float(value) * poss / (poss + float(prior))


def load_defensive_factors(
    settings: Settings,
    season: str,
    *,
    prior_poss: float = 4000.0,
) -> dict[int, DefenseFactors]:
    """Prior-season six-factor defense. ``latest_year`` never reaches ``season``."""
    table = _read_dataset_table(
        settings,
        "nbarapm_six_factor",
        columns=[
            "player_id",
            "latest_year",
            "year_interval",
            "off_poss",
            "sc_def_ts",
            "sc_def_tov",
            "sc_def_reb",
        ],
    )
    if table is None:
        return {}
    cap = prior_season_end_year(season)
    interval_rank = {"3Y": 0, "5Y": 1}
    best: dict[int, tuple[tuple[int, int], DefenseFactors]] = {}
    columns = {name: table.column(name).to_pylist() for name in table.column_names}
    for pid, year, interval, poss, ts, tov, reb in zip(
        columns["player_id"],
        columns["latest_year"],
        columns["year_interval"],
        columns["off_poss"],
        columns["sc_def_ts"],
        columns["sc_def_tov"],
        columns["sc_def_reb"],
    ):
        iv = str(interval or "")
        if iv not in interval_rank or pid is None or year is None:
            continue
        latest = int(year)
        if latest > cap:
            continue
        key = (interval_rank[iv], -latest)
        player_id = int(pid)
        prev = best.get(player_id)
        if prev is not None and key >= prev[0]:
            continue
        poss_f = float(poss or 0.0)
        best[player_id] = (
            key,
            DefenseFactors(
                tov=shrink_component(tov, poss_f, prior_poss),
                ts=shrink_component(ts, poss_f, prior_poss),
                reb=shrink_component(reb, poss_f, prior_poss),
                possessions=poss_f,
            ),
        )
    return {pid: row[1] for pid, row in best.items()}


def minutes_weighted_mean(
    weights: list[float],
    values: list[float],
) -> float:
    """Mean of ratings, weighted by expected minutes. Missing ratings are zero."""
    num = 0.0
    den = 0.0
    for weight, value in zip(weights, values):
        w = max(0.0, float(weight))
        if w <= 0.0:
            continue
        num += w * float(value)
        den += w
    if den <= 0.0:
        return 0.0
    return num / den


def lineup_adjustments(
    tov_residual: np.ndarray | float,
    ts_residual: np.ndarray | float,
    reb_residual: np.ndarray | float,
    weight: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Map a points-per-100 residual into steal, dead-ball turnover, FG, and ORB.

    Positive defense lowers opponent shooting and offensive rebounds and
    raises turnovers. About 55% of the extra turnovers are steals. The rest
    are dead-ball turnovers. Returns ``(steal_delta, tov_delta, fg_mult, orb_mult)``.
    """
    scale = float(weight)
    tov_rate = np.clip(scale * np.asarray(tov_residual, dtype=float) / _POINTS_PER_EVENT, -0.04, 0.04)
    steal_delta = tov_rate * 0.55
    tov_delta = tov_rate - steal_delta
    fg_mult = np.clip(1.0 - scale * np.asarray(ts_residual, dtype=float) / _POINTS_PER_EVENT, 0.85, 1.15)
    orb_mult = np.clip(1.0 - scale * np.asarray(reb_residual, dtype=float) / 8.0, 0.75, 1.25)
    return steal_delta, tov_delta, fg_mult, orb_mult
