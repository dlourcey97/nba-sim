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


def kalman_blend_weight(
    base_weight: float,
    current_games: int,
    *,
    half_life: float,
) -> float:
    """Scale Kalman blend by sample size so 1–5 finals cannot dominate prior+RAPM.

    ``effective = base * games / (games + half_life)``. With half_life=15 and
    2 games, a 0.45 base weight becomes ~0.05.
    """
    if half_life <= 0:
        return float(base_weight)
    games = max(0, int(current_games))
    return float(base_weight) * (games / (games + float(half_life)))


def prior_strength_after_absences(
    prior: TeamStrength | None,
    *,
    healthy_net: float,
    available_net: float,
    weight: float = 1.0,
    out_base_minutes: float = 0.0,
    minutes_net_per_36: float = 0.0,
) -> TeamStrength | None:
    """Worsen season prior when rotation players are out.

    Two layers:
    - RAPM gap ``healthy_net - available_net`` when positive (never credit a team
      for sitting negative-RAPM stars — ridge RAPM often undersells them).
    - Minutes-based net hit: ``(out_base_minutes / 36) * minutes_net_per_36``,
      so sidelined starters move the line even when RAPM is flat/noisy.
    """
    if prior is None:
        return prior
    gap = float(healthy_net) - float(available_net)
    # Only apply RAPM gap when outs remove positive value.
    rapm_delta = 0.5 * float(weight) * gap if gap > 0 and weight else 0.0
    min_delta = 0.0
    if minutes_net_per_36 > 0 and out_base_minutes > 0:
        min_delta = 0.5 * (float(out_base_minutes) / 36.0) * float(minutes_net_per_36)
    delta = rapm_delta + min_delta
    if abs(delta) < 1e-9:
        return prior
    return TeamStrength(ortg=float(prior.ortg) - delta, drtg=float(prior.drtg) + delta)


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


def sos_adjust_game_ratings(
    raw_ortg: float,
    raw_drtg: float,
    *,
    opponent: TeamStrength,
    league: TeamStrength,
    weight: float = 1.0,
) -> tuple[float, float]:
    """Credit/debit one game's ORtg/DRtg for opponent quality.

    Scoring 110 against an elite defense (low opp DRtg) is better than 110
    against a sieve; allowing 110 to an elite offense is less damning than
    allowing 110 to a weak one.
    """
    w = float(weight)
    adj_o = float(raw_ortg) + w * (float(league.drtg) - float(opponent.drtg))
    adj_d = float(raw_drtg) + w * (float(league.ortg) - float(opponent.ortg))
    return adj_o, adj_d


def team_strength_as_of(
    settings: Settings,
    season: str,
    team_id: int,
    as_of: date,
    *,
    opponent_strength: dict[int, TeamStrength] | None = None,
    league: TeamStrength | None = None,
    sos_weight: float = 1.0,
) -> tuple[TeamStrength | None, int]:
    """Current-season ORtg/DRtg from team games strictly before ``as_of``.

    When ``opponent_strength`` (usually prior-season nets) and ``league`` are
    provided, each game is strength-of-schedule adjusted so a 0–2 against elite
    clubs is not treated like 0–2 against cupcakes, and a 2–0 vs weak teams is
    not treated like beating contenders.
    """
    pts_for = 0.0
    pts_against = 0.0
    poss_for = 0.0
    poss_against = 0.0
    adj_ortg_sum = 0.0
    adj_drtg_sum = 0.0
    games = 0
    use_sos = (
        opponent_strength is not None
        and league is not None
        and float(sos_weight) != 0.0
    )
    for row in read_rows(settings, "team_game_results", season):
        if int(row["team_id"]) != team_id:
            continue
        if row["game_date"] >= as_of:
            continue
        games += 1
        pts = float(row.get("pts") or 0.0)
        opp_pts = float(row.get("opp_pts") or 0.0)
        pts_for += pts
        pts_against += opp_pts
        pace = row.get("pace")
        if pace is not None and float(pace) > 0:
            poss = float(pace)
        else:
            poss = 100.0
        poss_for += poss
        # Opponent pace row is not joined here; use this team's pace as proxy
        # for possessions on both ends (same game pace).
        poss_against += poss
        if use_sos:
            raw_o = 100.0 * pts / poss
            raw_d = 100.0 * opp_pts / poss
            opp = opponent_strength.get(int(row["opponent_team_id"]))
            if opp is None:
                adj_ortg_sum += raw_o
                adj_drtg_sum += raw_d
            else:
                ao, ad = sos_adjust_game_ratings(
                    raw_o,
                    raw_d,
                    opponent=opp,
                    league=league,
                    weight=float(sos_weight),
                )
                adj_ortg_sum += ao
                adj_drtg_sum += ad
    if games <= 0:
        return None, 0
    if poss_for <= 0:
        # Pace missing: fall back to points-per-game scaled to league ~100 poss.
        poss_for = float(games) * 100.0
        poss_against = float(games) * 100.0
    if use_sos:
        return (
            TeamStrength(
                ortg=adj_ortg_sum / float(games),
                drtg=adj_drtg_sum / float(games),
            ),
            games,
        )
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


# Cache league TOV/STL averages so walk-forward does not re-scan Parquet per game.
_TOV_STL_AVG_CACHE: dict[tuple, tuple[float, float, int]] = {}
_TOV_STL_SCALE_CACHE: dict[tuple, tuple[float, float]] = {}


def _league_tov_stl_avg(
    settings: Settings,
    season_label: str,
    *,
    before: date | None,
    first_n_team_games: int | None = None,
) -> tuple[float, float, int]:
    key = (str(settings.data_dir), season_label, before, first_n_team_games)
    cached = _TOV_STL_AVG_CACHE.get(key)
    if cached is not None:
        return cached
    logs = read_rows(settings, "player_game_logs", season_label)
    by_gt: dict[tuple, list[float]] = {}
    order: list[tuple] = []
    seen: set[tuple] = set()
    # Only sort when we need a chronological early window.
    rows = (
        sorted(logs, key=lambda r: (r["game_date"], r["game_id"]))
        if first_n_team_games is not None
        else logs
    )
    for row in rows:
        if before is not None and row["game_date"] >= before:
            continue
        gt = (row["game_id"], int(row["team_id"]))
        if gt not in seen:
            seen.add(gt)
            order.append(gt)
            by_gt[gt] = [0.0, 0.0]
        by_gt[gt][0] += float(row.get("tov") or 0.0)
        by_gt[gt][1] += float(row.get("stl") or 0.0)
    if first_n_team_games is not None:
        keep = set(order[: int(first_n_team_games)])
        by_gt = {k: v for k, v in by_gt.items() if k in keep}
    n = len(by_gt)
    if n == 0:
        out = (0.0, 0.0, 0)
    else:
        out = (
            sum(v[0] for v in by_gt.values()) / n,
            sum(v[1] for v in by_gt.values()) / n,
            n,
        )
    _TOV_STL_AVG_CACHE[key] = out
    return out


def league_tov_stl_scales(
    settings: Settings,
    *,
    season: str,
    as_of: date,
    prior_season: str | None,
    min_team_games: int = 20,
) -> tuple[float, float]:
    """Current-season TOV/STL level vs prior season (as_of, no leakage).

    Early 2026-27 box TOV ~16.4 vs 2025-26 ~13.8. Blended player rates stay on
    the prior-season level until enough current games accumulate; this league
    scale lifts (or cuts) non-steal tov_rate and stl_rate so team totals track.

    Opening week (thin current sample): fall back to prior-season early-vs-full
    TOV/STL ratio (~+7% historically) so night-1 sims are not stuck on the
    full-season prior mean.
    """
    if not prior_season:
        return 1.0, 1.0
    cache_key = (
        str(settings.data_dir),
        season,
        as_of,
        prior_season,
        int(min_team_games),
    )
    hit = _TOV_STL_SCALE_CACHE.get(cache_key)
    if hit is not None:
        return hit

    prior_tov, prior_stl, n_prior = _league_tov_stl_avg(
        settings, prior_season, before=None
    )
    if n_prior == 0 or prior_tov <= 0 or prior_stl <= 0:
        _TOV_STL_SCALE_CACHE[cache_key] = (1.0, 1.0)
        return 1.0, 1.0

    curr_tov, curr_stl, n_curr = _league_tov_stl_avg(
        settings, season, before=as_of
    )
    if n_curr >= int(min_team_games):
        raw_tov = max(0.85, min(1.30, curr_tov / prior_tov))
        raw_stl = max(0.85, min(1.30, curr_stl / prior_stl))
        strength = min(1.0, n_curr / 20.0)
        tov_scale = 1.0 + strength * (raw_tov - 1.0)
        stl_scale = 1.0 + strength * (raw_stl - 1.0)
    else:
        early_tov, early_stl, n_early = _league_tov_stl_avg(
            settings, prior_season, before=None, first_n_team_games=60
        )
        if n_early == 0:
            _TOV_STL_SCALE_CACHE[cache_key] = (1.0, 1.0)
            return 1.0, 1.0
        tov_scale = max(0.95, min(1.20, early_tov / prior_tov))
        stl_scale = max(0.95, min(1.20, early_stl / prior_stl))

    deadband = 0.06
    if abs(tov_scale - 1.0) < deadband:
        tov_scale = 1.0
    if abs(stl_scale - 1.0) < deadband:
        stl_scale = 1.0
    if tov_scale > 1.0 + deadband and stl_scale == 1.0:
        stl_scale = 1.0 + 0.70 * (tov_scale - 1.0)
    if 0 < n_curr < 40 and tov_scale > 1.0:
        tov_scale = min(1.30, tov_scale * 1.04)
        if stl_scale > 1.0:
            stl_scale = min(1.30, stl_scale * 1.02)
    out = (float(tov_scale), float(stl_scale))
    _TOV_STL_SCALE_CACHE[cache_key] = out
    return out


def apply_tov_stl_league_scale(
    rates: RateVector,
    *,
    tov_scale: float,
    stl_scale: float,
) -> RateVector:
    """Multiply non-steal tov_rate and stl_rate by league level scales."""
    if abs(tov_scale - 1.0) < 1e-6 and abs(stl_scale - 1.0) < 1e-6:
        return rates
    return replace(
        rates,
        tov_rate=max(0.01, min(0.22, float(rates.tov_rate) * float(tov_scale))),
        stl_rate=max(0.005, min(0.05, float(rates.stl_rate) * float(stl_scale))),
    )


# Leakage-safe league pace / PPP from team_game_results (game_date < as_of).
_LEAGUE_ENV_AVG_CACHE: dict[tuple, tuple] = {}
_LEAGUE_ENV_SCALE_CACHE: dict[tuple, tuple[float, float]] = {}
_TEAM_PACE_ASOF_CACHE: dict[tuple, tuple[float, int]] = {}


def league_pace_ppp_as_of(
    settings: Settings,
    season_label: str,
    *,
    before: date | None,
) -> tuple[float, float, int]:
    """Mean team pace and points-per-possession before ``before`` (exclusive)."""
    pace, _ppg, ppp, n = league_env_as_of(settings, season_label, before=before)
    return pace, ppp, n


def league_env_as_of(
    settings: Settings,
    season_label: str,
    *,
    before: date | None,
) -> tuple[float, float, float, int]:
    """Return ``(pace, ppg, ppp, n_team_games)`` before ``before`` (exclusive)."""
    key = (str(settings.data_dir), season_label, before, "env4")
    hit = _LEAGUE_ENV_AVG_CACHE.get(key)
    if hit is not None:
        return hit  # type: ignore[return-value]
    paces: list[float] = []
    points: list[float] = []
    for row in read_rows(settings, "team_game_results", season_label):
        if before is not None and row["game_date"] >= before:
            continue
        pts = float(row.get("pts") or 0.0)
        points.append(pts)
        pace = row.get("pace")
        if pace is not None and float(pace) > 0:
            paces.append(float(pace))
    n = len(points)
    if n == 0:
        out = (0.0, 0.0, 0.0, 0)
    else:
        pace = sum(paces) / len(paces) if paces else 0.0
        ppg = sum(points) / n
        ppp = (sum(points) / sum(paces)) if paces else 0.0
        out = (pace, ppg, ppp, n)
    _LEAGUE_ENV_AVG_CACHE[key] = out  # type: ignore[assignment]
    return out


def team_pace_as_of(
    settings: Settings,
    season_label: str,
    team_id: int,
    *,
    before: date,
) -> tuple[float, int]:
    """Mean pace for one team from games strictly before ``before``."""
    key = (str(settings.data_dir), season_label, int(team_id), before)
    hit = _TEAM_PACE_ASOF_CACHE.get(key)
    if hit is not None:
        return hit
    total = 0.0
    n = 0
    for row in read_rows(settings, "team_game_results", season_label):
        if int(row["team_id"]) != int(team_id):
            continue
        if row["game_date"] >= before:
            continue
        pace = row.get("pace")
        if pace is None or float(pace) <= 0:
            continue
        total += float(pace)
        n += 1
    out = ((total / n) if n else 0.0, n)
    _TEAM_PACE_ASOF_CACHE[key] = out
    return out


def league_environment_scales(
    settings: Settings,
    *,
    season: str,
    as_of: date,
    prior_season: str | None,
    half_life_games: float = 12.0,
    early_season_games: float = 25.0,
) -> tuple[float, float]:
    """Current-season league pace/PPG vs prior, sample-size weighted.

    Returns ``(pace_scale, efficiency_scale)`` near 1.0. Active only while
    ``games_played < early_season_games``; after that, current-season rate
    blends already carry the environment (avoids mid-season double-count).
    Uses only games with ``game_date < as_of`` (no leakage).
    """
    if not prior_season:
        return 1.0, 1.0
    cache_key = (
        str(settings.data_dir),
        season,
        as_of,
        prior_season,
        float(half_life_games),
        float(early_season_games),
    )
    hit = _LEAGUE_ENV_SCALE_CACHE.get(cache_key)
    if hit is not None:
        return hit

    prior_pace, prior_ppg, _prior_ppp, n_prior = league_env_as_of(
        settings, prior_season, before=None
    )
    if n_prior == 0 or prior_pace <= 0 or prior_ppg <= 0:
        _LEAGUE_ENV_SCALE_CACHE[cache_key] = (1.0, 1.0)
        return 1.0, 1.0

    curr_pace, curr_ppg, _curr_ppp, n_curr = league_env_as_of(
        settings, season, before=as_of
    )
    half = max(1.0, float(half_life_games))
    n_games = n_curr / 2.0
    # Past the early window: identity (mid-season guardrail / rate blends own it).
    if n_games >= float(early_season_games):
        _LEAGUE_ENV_SCALE_CACHE[cache_key] = (1.0, 1.0)
        return 1.0, 1.0

    w = n_games / (n_games + half) if n_curr > 0 else 0.0

    if n_curr == 0:
        # Opening night: prior early window vs full (opening weeks often faster).
        early_pace, early_ppg, n_early = _prior_early_env(
            settings, prior_season, first_n_team_games=40
        )
        if n_early == 0:
            _LEAGUE_ENV_SCALE_CACHE[cache_key] = (1.0, 1.0)
            return 1.0, 1.0
        pace_scale = max(0.97, min(1.05, early_pace / prior_pace))
        # Efficiency from PPG (scoring level), not PPP — FTA/3PA mix shifts PPP.
        eff_scale = max(0.97, min(1.05, early_ppg / prior_ppg))
        w = 0.35
        pace_scale = 1.0 + w * (pace_scale - 1.0)
        eff_scale = 1.0 + w * (eff_scale - 1.0)
    else:
        raw_pace = max(0.94, min(1.06, curr_pace / prior_pace))
        raw_eff = max(0.94, min(1.06, curr_ppg / prior_ppg))
        pace_scale = 1.0 + w * (raw_pace - 1.0)
        eff_scale = 1.0 + w * (raw_eff - 1.0)

    # Deadband: ignore tiny drifts.
    if abs(pace_scale - 1.0) < 0.005:
        pace_scale = 1.0
    if abs(eff_scale - 1.0) < 0.005:
        eff_scale = 1.0
    out = (float(pace_scale), float(eff_scale))
    _LEAGUE_ENV_SCALE_CACHE[cache_key] = out
    return out


def _prior_early_env(
    settings: Settings,
    season_label: str,
    *,
    first_n_team_games: int,
) -> tuple[float, float, int]:
    rows = sorted(
        read_rows(settings, "team_game_results", season_label),
        key=lambda r: (r["game_date"], r["game_id"]),
    )[: int(first_n_team_games)]
    paces: list[float] = []
    points: list[float] = []
    for row in rows:
        points.append(float(row.get("pts") or 0.0))
        pace = row.get("pace")
        if pace is not None and float(pace) > 0:
            paces.append(float(pace))
    n = len(points)
    if n == 0:
        return 0.0, 0.0, 0
    pace = sum(paces) / len(paces) if paces else 0.0
    ppg = sum(points) / n
    return pace, ppg, n


def blended_team_pace_map(
    settings: Settings,
    *,
    season: str,
    as_of: date,
    prior_season: str | None,
    prior_pace: dict[int, float],
    half_life_games: float = 10.0,
    team_ids: Sequence[int] | None = None,
) -> dict[int, float]:
    """Per-team pace: blend as-of current with prior, regressed by games played."""
    ids = list(team_ids) if team_ids is not None else list(prior_pace.keys())
    if not ids and prior_season:
        ids = list(team_pace_map(settings, prior_season).keys())
    half = max(1.0, float(half_life_games))
    out: dict[int, float] = {}
    for tid in ids:
        prior = float(prior_pace.get(tid) or 100.0)
        curr, n = team_pace_as_of(settings, season, tid, before=as_of)
        if n <= 0 or curr <= 0:
            out[tid] = prior
            continue
        w = float(n) / (float(n) + half)
        out[tid] = w * curr + (1.0 - w) * prior
    return out


def apply_league_efficiency_scale(
    rates: RateVector,
    *,
    efficiency_scale: float,
) -> RateVector:
    """Scale zone FG% and softly FT rate by league efficiency environment."""
    if abs(efficiency_scale - 1.0) < 1e-6:
        return rates
    scale = float(efficiency_scale)
    updates: dict[str, float] = {
        "ft_rate": min(0.45, max(0.02, float(rates.ft_rate) * (1.0 + 0.5 * (scale - 1.0)))),
    }
    for zone in ZONES:
        key = f"{zone}_fg_pct"
        updates[key] = min(0.85, max(0.15, float(getattr(rates, key)) * scale))
    return replace(rates, **updates)


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
