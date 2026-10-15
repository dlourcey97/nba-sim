"""Opponent, pace, rest, home/away, and teammate-absence adjustments."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any, Sequence

from nba_sim.schema import ZONES
from nba_sim.settings import Settings
from nba_sim.storage import read_rows

from ingest.injuries import InjuryEntry
from projections.rates import RateVector


def rest_days_before(
    game_dates: Sequence[date],
    game_date: date,
) -> int:
    prior = [value for value in game_dates if value < game_date]
    if not prior:
        return 3
    last = max(prior)
    return max(0, (game_date - last).days - 1)


def team_pace_map(settings: Settings, season: str) -> dict[int, float]:
    rows = read_rows(settings, "team_season_aggregates", season)
    return {int(row["team_id"]): float(row["pace"]) for row in rows if row.get("pace") is not None}


def league_zone_fg_pct(settings: Settings, season: str) -> dict[str, float]:
    rows = read_rows(settings, "team_zone_defense", season)
    totals: dict[str, list[float]] = {zone: [0.0, 0.0] for zone in ZONES}
    for row in rows:
        zone = str(row["zone"])
        if zone not in totals:
            continue
        totals[zone][0] += float(row["fgm"] or 0.0)
        totals[zone][1] += float(row["fga"] or 0.0)
    out: dict[str, float] = {}
    for zone, (fgm, fga) in totals.items():
        out[zone] = (fgm / fga) if fga > 0 else getattr(RateVector(), f"{zone}_fg_pct")
    return out


def opponent_zone_fg_pct(settings: Settings, season: str, team_id: int) -> dict[str, float]:
    rows = [
        row
        for row in read_rows(settings, "team_zone_defense", season)
        if int(row["team_id"]) == team_id
    ]
    out: dict[str, float] = {}
    for row in rows:
        zone = str(row["zone"])
        fga = float(row["fga"] or 0.0)
        fgm = float(row["fgm"] or 0.0)
        out[zone] = (fgm / fga) if fga > 0 else getattr(RateVector(), f"{zone}_fg_pct")
    return out


def expected_possessions(
    *,
    team_pace: float,
    opp_pace: float,
    home_away: str,
    rest_days: int,
    config: dict[str, Any],
) -> float:
    ctx = config["context"]
    pace = 0.5 * (team_pace + opp_pace)
    if home_away == "H":
        pace *= 1.0 + float(ctx["home_pace_factor"])
    else:
        pace *= 1.0 + float(ctx["away_pace_factor"])
    rest_factors = {int(key): float(value) for key, value in ctx["rest_day_factors"].items()}
    if rest_days in rest_factors:
        factor = rest_factors[rest_days]
    elif rest_days > max(rest_factors):
        factor = rest_factors[max(rest_factors)]
    else:
        factor = rest_factors[min(rest_factors)]
    return pace * (1.0 + factor)


def apply_opponent_defense(
    rates: RateVector,
    *,
    opp_zone_pct: dict[str, float],
    league_zone_pct: dict[str, float],
    weight: float,
) -> RateVector:
    if weight == 0:
        return rates
    updates = {}
    for zone in ZONES:
        league = league_zone_pct.get(zone) or getattr(rates, f"{zone}_fg_pct")
        opp = opp_zone_pct.get(zone) or league
        if league <= 0:
            continue
        # Soft multiplicative shift toward opponent environment.
        factor = (opp / league) ** weight
        base = getattr(rates, f"{zone}_fg_pct")
        updates[f"{zone}_fg_pct"] = min(0.85, max(0.15, base * factor))
    return replace(rates, **updates)


def redistribute_for_absences(
    team_rates: dict[int, RateVector],
    *,
    out_player_ids: set[int],
    usage_share: float,
) -> dict[int, RateVector]:
    """Move usage from out players onto remaining teammates."""
    if not out_player_ids:
        return team_rates
    active = {pid: rates for pid, rates in team_rates.items() if pid not in out_player_ids}
    if not active:
        return team_rates
    freed = sum(team_rates[pid].usage for pid in out_player_ids if pid in team_rates) * usage_share
    active_usage = sum(rates.usage for rates in active.values()) or 1.0
    updated = dict(team_rates)
    for pid in out_player_ids:
        if pid in updated:
            updated[pid] = replace(updated[pid], usage=0.0)
    for pid, rates in active.items():
        bump = freed * (rates.usage / active_usage)
        updated[pid] = replace(rates, usage=min(0.45, rates.usage + bump))
    return updated


def match_injury_player_ids(
    entries: Sequence[InjuryEntry],
    meta_by_id: dict[int, dict[str, Any]],
) -> list[InjuryEntry]:
    """Fill player_id on name-only injury rows when a unique log match exists."""
    by_name: dict[tuple[str, str], list[int]] = {}
    for player_id, meta in meta_by_id.items():
        key = (_norm(meta["player_name"]), str(meta.get("team_abbr") or "").upper())
        by_name.setdefault(key, []).append(player_id)
    resolved: list[InjuryEntry] = []
    for entry in entries:
        if entry.player_id is not None:
            resolved.append(entry)
            continue
        key = (_norm(entry.player_name), str(entry.team_abbr or "").upper())
        matches = by_name.get(key, [])
        if len(matches) == 1:
            resolved.append(
                InjuryEntry(
                    game_date=entry.game_date,
                    matchup=entry.matchup,
                    team_name=entry.team_name,
                    team_abbr=entry.team_abbr,
                    player_name=entry.player_name,
                    player_id=matches[0],
                    status=entry.status,
                    reason=entry.reason,
                    minutes_cap=entry.minutes_cap,
                    source=entry.source,
                )
            )
        else:
            resolved.append(entry)
    return resolved


def _norm(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())
