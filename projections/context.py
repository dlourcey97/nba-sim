"""Opponent, pace, rest, home/away, and teammate-absence adjustments."""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Sequence

from nba_sim.schema import POSITIONS_5, ZONES
from nba_sim.settings import Settings
from nba_sim.storage import read_rows

from ingest.injuries import InjuryEntry
from projections.rates import RateVector, five_position


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


def zone_defense_from_bundles(
    bundles: Sequence[Any],
    *,
    as_of: date,
    defender_team_id: int | None = None,
) -> dict[str, float]:
    """Opponent zone FG% allowed before as_of. League-wide when defender_team_id is None."""
    fga: dict[str, float] = defaultdict(float)
    fgm: dict[str, float] = defaultdict(float)
    for bundle in bundles:
        log_rows = _defense_log_rows(bundle, defender_team_id)
        rates_by_key = bundle.rates_by_key or {}
        for log in log_rows:
            if log["game_date"] >= as_of:
                # Indexed defender lists and logs_sorted are date-ordered.
                if bundle.logs_sorted is not None or bundle.logs_by_defender is not None:
                    break
                continue
            rate = rates_by_key.get((str(log["game_id"]), int(log["player_id"])))
            if rate is None:
                continue
            for zone in ZONES:
                fga[zone] += float(rate.get(f"{zone}_fga") or 0.0)
                fgm[zone] += float(rate.get(f"{zone}_fgm") or 0.0)
    out: dict[str, float] = {}
    for zone in ZONES:
        attempts = fga[zone]
        out[zone] = (fgm[zone] / attempts) if attempts > 0 else getattr(RateVector(), f"{zone}_fg_pct")
    return out


def position_defense_from_bundles(
    bundles: Sequence[Any],
    *,
    as_of: date,
    defender_team_id: int | None = None,
) -> dict[str, dict[str, float]]:
    """Per-36 stats allowed to PG/SG/SF/PF/C before as_of (league or one defender)."""
    totals: dict[str, dict[str, float]] = {
        pos: {"minutes": 0.0, "pts": 0.0, "reb": 0.0, "ast": 0.0, "fg3m": 0.0}
        for pos in POSITIONS_5
    }
    for bundle in bundles:
        log_rows = _defense_log_rows(bundle, defender_team_id)
        for row in log_rows:
            if row["game_date"] >= as_of:
                if bundle.logs_sorted is not None or bundle.logs_by_defender is not None:
                    break
                continue
            position = five_position(
                None if row.get("position") is None else str(row.get("position")),
                reb=float(row.get("reb") or 0),
                ast=float(row.get("ast") or 0),
                minutes=float(row.get("minutes") or 0),
            )
            bucket = totals[position]
            bucket["minutes"] += float(row.get("minutes") or 0)
            bucket["pts"] += float(row.get("pts") or 0)
            bucket["reb"] += float(row.get("reb") or 0)
            bucket["ast"] += float(row.get("ast") or 0)
            bucket["fg3m"] += float(row.get("fg3m") or 0)
    out: dict[str, dict[str, float]] = {}
    for pos, bucket in totals.items():
        minutes = bucket["minutes"]
        scale = 36.0 / minutes if minutes > 0 else 0.0
        out[pos] = {
            "pts_per_36": bucket["pts"] * scale,
            "reb_per_36": bucket["reb"] * scale,
            "ast_per_36": bucket["ast"] * scale,
            "fg3m_per_36": bucket["fg3m"] * scale,
            "minutes": minutes,
        }
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


@dataclass(frozen=True)
class TeamStrength:
    ortg: float
    drtg: float


_THREE_ZONES = frozenset({"left_corner_3", "right_corner_3", "above_break_3"})


def team_strength_map(settings: Settings, season: str) -> dict[int, TeamStrength]:
    """Offensive/defensive rating (pts per 100 possessions) from season aggregates."""
    out: dict[int, TeamStrength] = {}
    for row in read_rows(settings, "team_season_aggregates", season):
        pf = float(row.get("points_for") or 0.0)
        pa = float(row.get("points_against") or 0.0)
        poss_f = float(row.get("possessions_for") or 0.0)
        poss_a = float(row.get("possessions_against") or 0.0)
        if poss_f <= 0 or poss_a <= 0:
            continue
        out[int(row["team_id"])] = TeamStrength(
            ortg=100.0 * pf / poss_f,
            drtg=100.0 * pa / poss_a,
        )
    return out


def team_strength_as_of(
    settings: Settings,
    season: str,
    team_id: int,
    as_of: date,
) -> tuple[TeamStrength | None, int]:
    """Current-season ORtg/DRtg from team games strictly before ``as_of``."""
    pts_for = 0.0
    pts_against = 0.0
    poss_for = 0.0
    poss_against = 0.0
    games = 0
    for row in read_rows(settings, "team_game_results", season):
        if int(row["team_id"]) != team_id:
            continue
        if row["game_date"] >= as_of:
            continue
        games += 1
        pts_for += float(row.get("pts") or 0.0)
        pts_against += float(row.get("opp_pts") or 0.0)
        pace = row.get("pace")
        if pace is not None and float(pace) > 0:
            poss_for += float(pace)
            # Opponent pace row is not joined here; use this team's pace as proxy
            # for possessions on both ends (same game pace).
            poss_against += float(pace)
    if games <= 0:
        return None, 0
    if poss_for <= 0:
        # Pace missing: fall back to points-per-game scaled to league ~100 poss.
        poss_for = float(games) * 100.0
        poss_against = float(games) * 100.0
    return (
        TeamStrength(
            ortg=100.0 * pts_for / poss_for,
            drtg=100.0 * pts_against / poss_against,
        ),
        games,
    )


def points_per_use(rates: RateVector) -> float:
    """Expected points when a player uses a possession (shot/TO/FT proxy)."""
    shot_pts = 0.0
    for zone in ZONES:
        share = float(getattr(rates, f"{zone}_share"))
        fg = float(getattr(rates, f"{zone}_fg_pct"))
        mult = 3.0 if zone in _THREE_ZONES else 2.0
        shot_pts += share * fg * mult
    # Non-TO uses: field-goal attempt value + FT rate * FT%.
    return (1.0 - float(rates.tov_rate)) * shot_pts + float(rates.ft_rate) * float(rates.ft_pct)


def roster_team_strength(
    players: Sequence[tuple[RateVector, float]],
    *,
    prior: TeamStrength | None,
    current: TeamStrength | None,
    current_games: int,
    league: TeamStrength,
    config: dict[str, Any],
) -> TeamStrength:
    """Minutes-weighted roster ORtg/DRtg blended with current-season results.

    Offense: usage-weighted expected points per team possession from tonight's
    projected rotation. Defense: minutes-weighted steal/block proxy blended
    toward prior-season team DRtg (player DRtg is not stored).
    """
    ctx = config.get("context", {})
    half_life = float(ctx.get("team_strength_half_life", 20.0))
    def_prior_w = float(ctx.get("roster_defense_prior_weight", 0.35))

    total_min = 0.0
    usage_sum = 0.0
    scored = 0.0
    stl_w = 0.0
    blk_w = 0.0
    for rates, minutes in players:
        minutes = float(max(0.0, minutes))
        if minutes <= 0:
            continue
        total_min += minutes
        usage = float(max(0.0, rates.usage))
        usage_sum += usage
        scored += usage * points_per_use(rates)
        stl_w += minutes * float(rates.stl_rate)
        blk_w += minutes * float(rates.blk_rate)

    if total_min <= 0 or usage_sum <= 1e-9:
        roster_ortg = prior.ortg if prior is not None else league.ortg
        roster_drtg = prior.drtg if prior is not None else league.drtg
    else:
        # Usages are later normalized to 1 among playing players; scale now.
        roster_ortg = 100.0 * scored / usage_sum
        # League-average ~0.015 stl + 0.010 blk per def poss on court; map a
        # soft DRtg shift from the minutes-weighted rates.
        stl_rate = stl_w / total_min
        blk_rate = blk_w / total_min
        stop_rate = stl_rate + 0.7 * blk_rate
        league_stop = 0.015 + 0.7 * 0.010
        # Higher stop rate → lower (better) DRtg. Keep most of prior team DRtg
        # because player-level defense is a thin proxy.
        delta = 8.0 * (league_stop - stop_rate) / max(league_stop, 1e-6)
        base_drtg = prior.drtg if prior is not None else league.drtg
        roster_drtg = base_drtg + delta * (1.0 - def_prior_w)

    # Blend roster estimate with current-season results as games accumulate.
    if current is not None and current_games > 0 and half_life > 0:
        w = current_games / (current_games + half_life)
        ortg = (1.0 - w) * roster_ortg + w * current.ortg
        drtg = (1.0 - w) * roster_drtg + w * current.drtg
    else:
        ortg = roster_ortg
        drtg = roster_drtg
    return TeamStrength(ortg=float(ortg), drtg=float(drtg))


def league_strength(strength: dict[int, TeamStrength]) -> TeamStrength:
    if not strength:
        return TeamStrength(ortg=112.0, drtg=112.0)
    ortg = sum(item.ortg for item in strength.values()) / len(strength)
    drtg = sum(item.drtg for item in strength.values()) / len(strength)
    return TeamStrength(ortg=ortg, drtg=drtg)


def apply_team_strength_and_hca(
    rates: RateVector,
    *,
    team: TeamStrength | None,
    opponent: TeamStrength | None,
    league: TeamStrength,
    home_away: str,
    config: dict[str, Any],
    rest_home: int | None = None,
    rest_away: int | None = None,
) -> RateVector:
    """Scale FG%/FT% from team offense, opponent defense, and home-court edge.

    Soft multiplicative shifts so strong offenses / weak defenses / home court
    separate win probabilities without blowing up scoring level. When both
    teams' rest days are provided, HCA is non-linear in rest (B2B penalty).
    """
    ctx = config.get("context", {})
    off_w = float(ctx.get("team_offense_weight", 0.0))
    def_w = float(ctx.get("team_defense_weight", 0.0))
    home_fg = float(ctx.get("home_fg_factor", 0.0))
    away_fg = float(ctx.get("away_fg_factor", 0.0))
    factor = 1.0
    if team is not None and league.ortg > 0 and off_w != 0:
        factor *= (team.ortg / league.ortg) ** off_w
    if opponent is not None and league.drtg > 0 and def_w != 0:
        # Higher opponent DRtg = worse defense = boost our FG%.
        factor *= (opponent.drtg / league.drtg) ** def_w
    if rest_home is not None and rest_away is not None:
        from projections.kalman import rest_fg_adjustment

        factor *= 1.0 + rest_fg_adjustment(
            rest_home, rest_away, home_away=home_away, config=config
        )
    elif home_away == "H":
        factor *= 1.0 + home_fg
    else:
        factor *= 1.0 + away_fg
    if abs(factor - 1.0) < 1e-9:
        return rates
    updates = {}
    for zone in ZONES:
        base = getattr(rates, f"{zone}_fg_pct")
        updates[f"{zone}_fg_pct"] = min(0.85, max(0.15, base * factor))
    updates["ft_pct"] = min(0.95, max(0.50, rates.ft_pct * (1.0 + (factor - 1.0) * 0.35)))
    return replace(rates, **updates)


def _defense_log_rows(bundle: Any, defender_team_id: int | None) -> list[dict]:
    """Opponent player-log rows for defense scans; works with partial test bundles."""
    if defender_team_id is None:
        if bundle.logs_sorted is not None:
            return bundle.logs_sorted
        return [row for rows in bundle.logs_by_player.values() for row in rows]
    if bundle.logs_by_defender is not None:
        return bundle.logs_by_defender.get(defender_team_id, [])
    return [
        row
        for rows in bundle.logs_by_player.values()
        for row in rows
        if int(row["opponent_team_id"]) == defender_team_id
    ]


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


def apply_opponent_position_defense(
    rates: RateVector,
    *,
    position: str | None,
    opp_allowed: dict[str, dict[str, float]],
    league_allowed: dict[str, dict[str, float]],
    weight: float,
    reb: float = 0.0,
    ast: float = 0.0,
    minutes: float = 0.0,
) -> RateVector:
    """Shift FG% / rates from how much the opponent allows to this position vs league."""
    if weight == 0:
        return rates
    pos = five_position(position, reb=reb, ast=ast, minutes=minutes)
    league = league_allowed.get(pos) or {}
    opp = opp_allowed.get(pos) or league
    league_pts = float(league.get("pts_per_36") or 0.0)
    opp_pts = float(opp.get("pts_per_36") or league_pts)
    if league_pts <= 0:
        return rates
    factor = (opp_pts / league_pts) ** weight
    updates = {}
    for zone in ZONES:
        base = getattr(rates, f"{zone}_fg_pct")
        updates[f"{zone}_fg_pct"] = min(0.85, max(0.15, base * factor))
    league_ast = float(league.get("ast_per_36") or 0.0)
    opp_ast = float(opp.get("ast_per_36") or league_ast)
    if league_ast > 0:
        ast_factor = (opp_ast / league_ast) ** (weight * 0.5)
        # Elite creators can exceed ~0.45 AST/teammate-FGM; keep room above that.
        updates["ast_rate"] = min(0.65, max(0.02, rates.ast_rate * ast_factor))
    league_reb = float(league.get("reb_per_36") or 0.0)
    opp_reb = float(opp.get("reb_per_36") or league_reb)
    if league_reb > 0:
        reb_factor = (opp_reb / league_reb) ** (weight * 0.5)
        updates["oreb_rate"] = min(0.25, max(0.01, rates.oreb_rate * reb_factor))
        updates["dreb_rate"] = min(0.45, max(0.02, rates.dreb_rate * reb_factor))
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
    """Fill player_id on name-only injury rows when a unique log match exists.

    Prefer (normalized name, team_abbr). If that misses — common after trades
    when meta still has last season's team — fall back to a unique name-only
    match across the meta map. Names are ASCII-folded so Porziņģis ≈ Porzingis.
    """
    by_team: dict[tuple[str, str], list[int]] = {}
    by_name: dict[str, list[int]] = {}
    for player_id, meta in meta_by_id.items():
        norm = _norm(str(meta["player_name"]))
        team = str(meta.get("team_abbr") or "").upper()
        by_team.setdefault((norm, team), []).append(player_id)
        by_name.setdefault(norm, []).append(player_id)
    resolved: list[InjuryEntry] = []
    for entry in entries:
        if entry.player_id is not None:
            resolved.append(entry)
            continue
        norm = _norm(entry.player_name)
        team = str(entry.team_abbr or "").upper()
        matches = by_team.get((norm, team), [])
        if len(matches) != 1:
            name_hits = list(dict.fromkeys(by_name.get(norm, [])))
            matches = name_hits if len(name_hits) == 1 else []
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
    folded = unicodedata.normalize("NFKD", name or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return "".join(ch for ch in folded.lower() if ch.isalnum())
