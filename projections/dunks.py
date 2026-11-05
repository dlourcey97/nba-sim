"""Blend Dunks & Threes priors into an already-built game projection.

EPM (career rating as of that morning) supplies minutes, usage, shooting,
free throws, turnovers, steals, and blocks. The same-day box projection
nudges those rates toward tonight's line. Team ratings nudge offense and
defense. Weights stay partial so the possession model still runs the game.
Missing files are a no-op, including every date before the stored snapshots.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from nba_sim.schema import ZONES
from nba_sim.settings import Settings
from projections.context import TeamStrength
from projections.rates import RateVector

_TWO = ("restricted_area", "paint_non_ra", "midrange")
_THREE = ("left_corner_3", "right_corner_3", "above_break_3")
_FILE_DATE = re.compile(r"_(\d{4}-\d{2}-\d{2})\.parquet$")
_CACHE: dict[tuple, Any] = {}


@dataclass(frozen=True)
class EpmPrior:
    team: str
    mpg: float
    usg: float
    oepm: float
    depm: float
    pts_100: float
    fg2a_100: float
    fg2_pct: float
    fg3a_100: float
    fg3_pct: float
    fta_100: float
    ft_pct: float
    orb_100: float
    drb_100: float
    ast_100: float
    tov_100: float
    stl_100: float
    blk_100: float


@dataclass(frozen=True)
class BoxPrior:
    team: str
    minutes: float
    pts: float
    reb: float
    ast: float
    stl: float
    blk: float
    tov: float
    oreb: float
    dreb: float
    fg3a: float


def apply_dunks_blend(
    home_players: dict,
    away_players: dict,
    *,
    settings: Settings,
    as_of: date,
    home_poss: float,
    away_poss: float,
    home_strength: TeamStrength | None,
    away_strength: TeamStrength | None,
    league: TeamStrength | None,
    config: dict,
    defender_fg_factor: dict[int, float] | None = None,
    defender_fg3_factor: dict[int, float] | None = None,
) -> list[dict[str, Any]]:
    """Pull playing players partway toward Dunks. Out players stay out.

    A healthy player whose minutes are 0 still gets the blend when EPM or
    tonight's box has a minute number. Those cases are returned so the live
    scorecard can grade them on their own. Historical dates with no file
    return an empty list and change nothing.
    """
    ctx = config.get("context") or {}
    if not bool(ctx.get("dunks_enabled", True)):
        return []
    epm_w = float(ctx.get("dunks_epm_weight", 0.30))
    box_w = float(ctx.get("dunks_box_weight", 0.25))
    team_w = float(ctx.get("dunks_team_weight", 0.20))
    if epm_w <= 0 and box_w <= 0 and team_w <= 0:
        return []
    data_dir = Path(settings.data_dir) / "external" / "dunks"
    if not data_dir.is_dir():
        return []
    epm = _epm_map(data_dir, as_of) if epm_w > 0 else {}
    box = _box_map(data_dir, as_of) if box_w > 0 else {}
    teams = _team_map(data_dir, as_of) if team_w > 0 else {}
    if not epm and not box and not teams:
        return []
    home_abbr = _side_abbr(home_players)
    away_abbr = _side_abbr(away_players)
    sides = (
        (home_players, home_poss, home_strength, away_strength, home_abbr, away_abbr),
        (away_players, away_poss, away_strength, home_strength, away_abbr, home_abbr),
    )
    fallbacks: list[dict[str, Any]] = []
    for players, poss, team_str, opp_str, team_abbr, opp_abbr in sides:
        before = {
            pid: float(player.minutes.mean)
            for pid, player in players.items()
            if not _is_out(player)
        }
        for pid, player in list(players.items()):
            epm_row = epm.get(int(player.player_id))
            box_row = box.get(int(player.player_id))
            if epm_row is not None and epm_row.team != player.team_abbr:
                epm_row = None
            if box_row is not None and box_row.team != player.team_abbr:
                box_row = None
            if _is_out(player):
                continue
            zero_fallback = float(player.minutes.mean) <= 0.0 and not player.minutes.out
            if zero_fallback and not _has_minute_number(epm_row, box_row):
                continue
            rates = player.rates
            if epm_row is not None and epm_w > 0:
                rates = _blend_epm_rates(rates, epm_row, epm_w)
            if epm_row is not None and box_row is not None and box_w > 0:
                rates = _nudge_box_rates(rates, epm_row, box_row, poss, box_w)
            minutes = _blend_minutes(player.minutes, epm_row, box_row, epm_w, box_w)
            if zero_fallback and float(minutes.mean) > 0.0:
                # The sit/play draw was built for a zero-minute player. Keep
                # him in the rotation often enough that the new mean is real.
                minutes = replace(
                    minutes,
                    play_prob=max(float(minutes.play_prob), 0.85),
                )
                fallbacks.append(
                    {
                        "player_id": int(player.player_id),
                        "player_name": str(player.player_name),
                        "team_abbr": str(player.team_abbr),
                        "minutes_before": 0.0,
                        "minutes_after": float(minutes.mean),
                        "source": _minute_source(epm_row, box_row),
                    }
                )
            if team_w > 0:
                rates = _nudge_team_rating(
                    rates,
                    team=teams.get(team_abbr),
                    opponent=teams.get(opp_abbr),
                    team_strength=team_str,
                    opponent_strength=opp_str,
                    league=league,
                    weight=team_w,
                )
            if epm_row is not None and epm_w > 0:
                _nudge_defender(
                    int(player.player_id),
                    epm_row.depm,
                    epm_w,
                    defender_fg_factor,
                    defender_fg3_factor,
                )
            players[pid] = replace(player, rates=rates, minutes=minutes)
        _hold_side_total(players, before)
        for event in fallbacks:
            player = players.get(event["player_id"])
            if player is not None and str(player.team_abbr) == str(event["team_abbr"]):
                event["minutes_after"] = float(player.minutes.mean)
    _renorm_usage(home_players, config)
    _renorm_usage(away_players, config)
    return fallbacks


def _hold_side_total(players: dict, before: dict[int, float]) -> None:
    """Put a full rotation's minute total back where the minutes model left it.

    The blend can raise one player without giving the team extra minutes.
    Sides with fewer than eight available players are left alone, so a short
    test roster does not get stretched to a game total. The sim draw still
    scales every team to 240.
    """
    active = [pid for pid in before if pid in players and not _is_out(players[pid])]
    if len(active) < 8:
        return
    goal = sum(before[pid] for pid in active)
    total = sum(float(players[pid].minutes.mean) for pid in active)
    if goal <= 1.0 or total <= 1.0 or abs(goal - total) < 0.05:
        return
    scale = goal / total
    for pid in active:
        player = players[pid]
        mean = float(player.minutes.mean) * scale
        lo = float(player.minutes.min_minutes)
        hi = float(player.minutes.max_minutes)
        if hi > 0.0:
            mean = min(hi, mean)
        mean = max(lo, mean)
        players[pid] = replace(player, minutes=replace(player.minutes, mean=float(mean)))


def _has_minute_number(epm: EpmPrior | None, box: BoxPrior | None) -> bool:
    if epm is not None and float(epm.mpg) >= 1.0:
        return True
    return box is not None and float(box.minutes) >= 1.0


def _minute_source(epm: EpmPrior | None, box: BoxPrior | None) -> str:
    has_epm = epm is not None and float(epm.mpg) >= 1.0
    has_box = box is not None and float(box.minutes) >= 1.0
    if has_epm and has_box:
        return "both"
    if has_box:
        return "box"
    return "epm"


def _is_out(player) -> bool:
    """Injury outs stay out. A healthy zero-minute player is not an out."""
    if bool(player.minutes.out):
        return True
    return str(getattr(player, "status", "") or "").lower() == "out"


def append_fallback_log(repo_root: Path, events: list[dict[str, Any]]) -> None:
    """Append live fallback rows. One JSON object per line. Not a model input."""
    if not events:
        return
    import json

    path = repo_root / "results" / "dunks_fallback.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, default=str) + "\n")


def _side_abbr(players: dict) -> str:
    for player in players.values():
        return str(player.team_abbr)
    return ""


def _blend_epm_rates(rates: RateVector, epm: EpmPrior, weight: float) -> RateVector:
    usg = float(epm.usg)
    updates: dict[str, float] = {
        "usage": _mix(rates.usage, usg, weight, 0.02, 0.45),
        "ft_pct": _mix(rates.ft_pct, epm.ft_pct, weight, 0.45, 0.95),
        "stl_rate": _mix(rates.stl_rate, epm.stl_100 / 100.0, weight, 0.002, 0.06),
        "blk_rate": _mix(rates.blk_rate, epm.blk_100 / 100.0, weight, 0.001, 0.08),
    }
    if usg >= 0.04:
        updates["ft_rate"] = _mix(
            rates.ft_rate, epm.fta_100 / (usg * 100.0), weight, 0.02, 0.45
        )
        updates["tov_rate"] = _mix(
            rates.tov_rate,
            0.39 * epm.tov_100 / (usg * 100.0),
            weight,
            0.015,
            0.18,
        )
    shot_attempts = epm.fg2a_100 + epm.fg3a_100
    merged = replace(rates, **updates)
    if shot_attempts > 0.5:
        merged = _blend_shot_profile(
            merged,
            three_share=epm.fg3a_100 / shot_attempts,
            fg2_pct=epm.fg2_pct,
            fg3_pct=epm.fg3_pct,
            weight=weight,
        )
    return merged.normalize_shares()


def _blend_shot_profile(
    rates: RateVector,
    *,
    three_share: float,
    fg2_pct: float,
    fg3_pct: float,
    weight: float,
) -> RateVector:
    current_three = sum(getattr(rates, f"{zone}_share") for zone in _THREE)
    target_three = min(0.85, max(0.0, three_share))
    new_three = (1.0 - weight) * current_three + weight * target_three
    updates: dict[str, float] = {}
    if current_three > 1e-6:
        scale = new_three / current_three
        for zone in _THREE:
            updates[f"{zone}_share"] = getattr(rates, f"{zone}_share") * scale
    elif new_three > 0:
        updates["above_break_3_share"] = new_three * 0.80
        updates["left_corner_3_share"] = new_three * 0.10
        updates["right_corner_3_share"] = new_three * 0.10
    current_two = sum(getattr(rates, f"{zone}_share") for zone in _TWO)
    new_two = max(0.0, 1.0 - new_three)
    if current_two > 1e-6:
        scale = new_two / current_two
        for zone in _TWO:
            updates[f"{zone}_share"] = getattr(rates, f"{zone}_share") * scale
    for zone in _TWO:
        key = f"{zone}_fg_pct"
        updates[key] = _mix(getattr(rates, key), fg2_pct, weight, 0.15, 0.85)
    for zone in _THREE:
        key = f"{zone}_fg_pct"
        updates[key] = _mix(getattr(rates, key), fg3_pct, weight, 0.15, 0.85)
    return replace(rates, **updates)


def _nudge_box_rates(
    rates: RateVector,
    epm: EpmPrior,
    box: BoxPrior,
    team_poss: float,
    weight: float,
) -> RateVector:
    """Move rates toward tonight's box, measured against the EPM per-100 line."""
    if box.minutes < 8.0 or team_poss <= 0:
        return rates
    updates: dict[str, float] = {}

    def pull(field: str, box_stat: float, epm_per_100: float, lo: float, hi: float) -> None:
        if epm_per_100 < 0.15:
            return
        projected = box_stat * 4800.0 / (team_poss * box.minutes)
        ratio = min(1.45, max(0.65, projected / epm_per_100))
        current = float(getattr(rates, field))
        updates[field] = min(hi, max(lo, current * ((1.0 - weight) + weight * ratio)))

    pull("usage", box.pts, epm.pts_100, 0.02, 0.45)
    pull("ast_rate", box.ast, epm.ast_100, 0.02, 0.55)
    pull("stl_rate", box.stl, epm.stl_100, 0.002, 0.06)
    pull("blk_rate", box.blk, epm.blk_100, 0.001, 0.08)
    pull("tov_rate", box.tov, epm.tov_100, 0.015, 0.18)
    pull("oreb_rate", box.oreb, epm.orb_100, 0.005, 0.25)
    pull("dreb_rate", box.dreb, epm.drb_100, 0.02, 0.40)
    merged = replace(rates, **updates) if updates else rates
    if epm.fg3a_100 >= 0.5 and box.fg3a >= 0:
        projected = box.fg3a * 4800.0 / (team_poss * box.minutes)
        ratio = min(1.45, max(0.65, projected / epm.fg3a_100))
        scale = (1.0 - weight) + weight * ratio
        merged = replace(
            merged,
            **{f"{zone}_share": getattr(merged, f"{zone}_share") * scale for zone in _THREE},
        )
    return merged.normalize_shares()


def _blend_minutes(minutes, epm: EpmPrior | None, box: BoxPrior | None, epm_w: float, box_w: float):
    if minutes.out:
        return minutes
    current = float(minutes.mean)
    parts: list[tuple[float, float]] = []
    if box is not None and box.minutes >= 1.0 and box_w > 0:
        parts.append((box_w, float(box.minutes)))
    if epm is not None and epm.mpg >= 1.0 and epm_w > 0:
        # Season minutes are a weaker pull than tonight's rotation.
        part = epm_w * (0.5 if box is not None and box.minutes >= 1.0 else 1.0)
        parts.append((part, float(epm.mpg)))
    weight = sum(item[0] for item in parts)
    if weight <= 0:
        return minutes
    if weight > 0.60:
        scale = 0.60 / weight
        parts = [(item[0] * scale, item[1]) for item in parts]
        weight = 0.60
    mean = (1.0 - weight) * current + sum(item[0] * item[1] for item in parts)
    lo = float(minutes.min_minutes)
    hi = float(minutes.max_minutes) if float(minutes.max_minutes) > 0 else mean
    mean = min(hi, max(lo, mean))
    return replace(minutes, mean=float(mean))


def _nudge_team_rating(
    rates: RateVector,
    *,
    team: tuple[float, float] | None,
    opponent: tuple[float, float] | None,
    team_strength: TeamStrength | None,
    opponent_strength: TeamStrength | None,
    league: TeamStrength | None,
    weight: float,
) -> RateVector:
    if league is None or league.ortg <= 0 or league.drtg <= 0 or weight <= 0:
        return rates
    factor = 1.0
    if team is not None and team_strength is not None and team_strength.ortg > 0:
        dunks_ortg = league.ortg + team[0]
        factor *= (dunks_ortg / team_strength.ortg) ** weight
    if opponent is not None and opponent_strength is not None and opponent_strength.drtg > 0:
        # Dunks defensive rating is points above average (positive = stingier).
        dunks_drtg = league.drtg - opponent[1]
        factor *= (dunks_drtg / opponent_strength.drtg) ** weight
    if abs(factor - 1.0) < 1e-9:
        return rates
    updates = {
        f"{zone}_fg_pct": min(0.85, max(0.15, getattr(rates, f"{zone}_fg_pct") * factor))
        for zone in ZONES
    }
    updates["ft_pct"] = min(0.95, max(0.45, rates.ft_pct * (1.0 + (factor - 1.0) * 0.35)))
    return replace(rates, **updates)


def _nudge_defender(
    player_id: int,
    depm: float,
    weight: float,
    fg_factor: dict[int, float] | None,
    fg3_factor: dict[int, float] | None,
) -> None:
    """Good defensive EPM slightly suppresses opponent shooting when he defends."""
    if fg_factor is None and fg3_factor is None:
        return
    shift = 1.0 - weight * 0.01 * float(depm)
    shift = min(1.08, max(0.92, shift))
    if fg_factor is not None:
        fg_factor[player_id] = min(1.15, max(0.85, float(fg_factor.get(player_id, 1.0)) * shift))
    if fg3_factor is not None:
        fg3_factor[player_id] = min(1.15, max(0.85, float(fg3_factor.get(player_id, 1.0)) * shift))


def _mix(current: float, target: float, weight: float, lo: float, hi: float) -> float:
    mixed = (1.0 - weight) * float(current) + weight * float(target)
    return min(hi, max(lo, mixed))


def _renorm_usage(players: dict, config: dict) -> None:
    from projections.build import _normalize_usage_for_minutes

    if not players:
        return
    minutes_by_id = {pid: player.minutes for pid, player in players.items()}
    out_ids = {pid for pid, player in players.items() if player.minutes.out}
    play_threshold = float((config.get("minutes") or {}).get("play_threshold", 1.0))
    updated = _normalize_usage_for_minutes(
        {pid: player.rates for pid, player in players.items()},
        minutes_by_id=minutes_by_id,
        out_ids=out_ids,
        play_threshold=play_threshold,
    )
    for pid, rates in updated.items():
        players[pid] = replace(players[pid], rates=rates)


def _epm_map(data_dir: Path, as_of: date) -> dict[int, EpmPrior]:
    key = ("epm", str(data_dir), as_of.isoformat())
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    path = _latest_file(data_dir, "epm_", as_of)
    mapping: dict[int, EpmPrior] = {}
    if path is not None:
        for row in pq.read_table(path).to_pylist():
            mapping[int(row["nba_id"])] = EpmPrior(
                team=str(row["team"]),
                mpg=float(row["p_mpg"]),
                usg=float(row["p_usg"]),
                oepm=float(row["oepm"]),
                depm=float(row["depm"]),
                pts_100=float(row["p_pts_100"]),
                fg2a_100=float(row["p_fg2a_100"]),
                fg2_pct=float(row["p_fg2pct"]),
                fg3a_100=float(row["p_fg3a_100"]),
                fg3_pct=float(row["p_fg3pct"]),
                fta_100=float(row["p_fta_100"]),
                ft_pct=float(row["p_ftpct"]),
                orb_100=float(row["p_orb_100"]),
                drb_100=float(row["p_drb_100"]),
                ast_100=float(row["p_ast_100"]),
                tov_100=float(row["p_tov_100"]),
                stl_100=float(row["p_stl_100"]),
                blk_100=float(row["p_blk_100"]),
            )
    _CACHE[key] = mapping
    return mapping


def _box_map(data_dir: Path, as_of: date) -> dict[int, BoxPrior]:
    key = ("box", str(data_dir), as_of.isoformat())
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    path = data_dir / f"box_{as_of.isoformat()}.parquet"
    mapping: dict[int, BoxPrior] = {}
    if path.is_file():
        for row in pq.read_table(path).to_pylist():
            mapping[int(row["player_id"])] = BoxPrior(
                team=str(row["team_abbr"]),
                minutes=float(row["minutes"]),
                pts=float(row["pts"]),
                reb=float(row["reb"]),
                ast=float(row["ast"]),
                stl=float(row["stl"]),
                blk=float(row["blk"]),
                tov=float(row["tov"]),
                oreb=float(row["oreb"]),
                dreb=float(row["dreb"]),
                fg3a=float(row["fg3a"]),
            )
    _CACHE[key] = mapping
    return mapping


def _team_map(data_dir: Path, as_of: date) -> dict[str, tuple[float, float]]:
    key = ("team", str(data_dir), as_of.isoformat())
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    path = _latest_file(data_dir, "team_ratings_", as_of)
    mapping: dict[str, tuple[float, float]] = {}
    if path is not None:
        for row in pq.read_table(path).to_pylist():
            mapping[str(row["team_abbr"])] = (float(row["ortg"]), float(row["drtg"]))
    _CACHE[key] = mapping
    return mapping


def _latest_file(data_dir: Path, prefix: str, as_of: date) -> Path | None:
    best: tuple[date, Path] | None = None
    for path in data_dir.glob(f"{prefix}*.parquet"):
        match = _FILE_DATE.search(path.name)
        if match is None:
            continue
        stamped = date.fromisoformat(match.group(1))
        if stamped <= as_of and (best is None or stamped > best[0]):
            best = (stamped, path)
    return None if best is None else best[1]
