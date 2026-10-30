"""Apply prior-season BBall Index grades. Flags default off.

Roles replace the G/F/C position heuristic in ``projections.context``.
Defense and play-type PPP are soft FG adjustments, clipped so a single
grade cannot move a zone FG% by more than 3%.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from nba_sim.schema import ZONES
from projections.rates import RateVector

PERIMETER_ZONES = ("midrange", "left_corner_3", "right_corner_3", "above_break_3")
INTERIOR_ZONES = ("restricted_area", "paint_non_ra")


def _clip_factor(raw: float) -> float:
    return min(1.03, max(0.97, float(raw)))


def _scale_zones(rates: RateVector, zones: tuple[str, ...], factor: float) -> RateVector:
    if abs(factor - 1.0) < 1e-9:
        return rates
    updates = {}
    for zone in zones:
        base = float(getattr(rates, f"{zone}_fg_pct"))
        updates[f"{zone}_fg_pct"] = min(0.85, max(0.15, base * factor))
    return replace(rates, **updates)


def minutes_weighted_grade(
    players: dict[int, Any],
    grades: dict[int, float],
    *,
    play_threshold: float = 1.0,
) -> float | None:
    total = 0.0
    weight = 0.0
    for pid, player in players.items():
        grade = grades.get(int(pid))
        if grade is None:
            continue
        minutes = float(getattr(player.minutes, "mean", 0.0) or 0.0)
        if minutes <= play_threshold or getattr(player.minutes, "out", False):
            continue
        total += minutes * float(grade)
        weight += minutes
    if weight <= 0:
        return None
    return total / weight


def apply_opponent_defense_grades(
    players: dict[int, Any],
    opponent: dict[int, Any],
    *,
    perimeter: dict[int, float],
    interior: dict[int, float],
    weight: float,
) -> None:
    """Lower FG% against a roster with positive (better) defensive grades."""
    if weight == 0 or not players:
        return
    per = minutes_weighted_grade(opponent, perimeter)
    inn = minutes_weighted_grade(opponent, interior)
    per_factor = _clip_factor(1.0 - weight * per) if per is not None else 1.0
    int_factor = _clip_factor(1.0 - weight * inn) if inn is not None else 1.0
    if abs(per_factor - 1.0) < 1e-9 and abs(int_factor - 1.0) < 1e-9:
        return
    for pid, player in list(players.items()):
        rates = player.rates
        if not isinstance(rates, RateVector):
            continue
        rates = _scale_zones(rates, INTERIOR_ZONES, int_factor)
        rates = _scale_zones(rates, PERIMETER_ZONES, per_factor)
        players[pid] = replace(player, rates=rates)


def apply_play_type_ppp(
    players: dict[int, Any],
    *,
    play_ppp: dict[int, dict[str, float]],
    league_ppp: dict[str, float],
    weight: float,
) -> None:
    """Nudge every zone FG% by prior-season stable PPP relative to the league."""
    if weight == 0 or not play_ppp or not league_ppp:
        return
    for pid, player in list(players.items()):
        values = play_ppp.get(int(pid))
        rates = player.rates
        if not values or not isinstance(rates, RateVector):
            continue
        ratios: list[float] = []
        for column, value in values.items():
            league = league_ppp.get(column)
            if league is None or league <= 0:
                continue
            ratios.append(float(value) / float(league))
        if not ratios:
            continue
        factor = _clip_factor((sum(ratios) / len(ratios)) ** weight)
        players[pid] = replace(player, rates=_scale_zones(rates, ZONES, factor))
