"""Leakage-safe referee crew effects on pace and free-throw rate.

Each official's foul, free-throw, pace, and points residuals are measured only
on games they worked before the slate date, then shrunk toward the league
average. The crew's combined residual scales expected possessions and ft_rate.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from ingest.referees import (
    _as_date,
    _read_rows,
    assignments_path,
    environment_path,
    officials_path,
)
from nba_sim.settings import Settings
from projections.rates import RateVector

@dataclass(frozen=True)
class CrewEffect:
    pace_factor: float
    ft_factor: float
    pace_delta: float
    ft_delta: float
    points_delta: float
    sample_games: int


@dataclass
class _GameStat:
    game_date: date
    game_id: str
    pace: float
    fta_per_100: float
    pf_per_100: float | None
    pts: float


class RefereeIndex:
    """Prior-game lookup. Games on the slate date are excluded."""

    def __init__(
        self,
        games: list[_GameStat],
        officials_by_game: dict[str, list[int]],
        official_game_pos: dict[int, list[int]],
        assignments: dict[tuple[date, str, str], list[int]],
    ) -> None:
        self.games = games
        self.officials_by_game = officials_by_game
        self.official_game_pos = official_game_pos
        self.assignments = assignments
        self._dates = [game.game_date for game in games]
        self._pace_prefix = _prefix([game.pace for game in games])
        self._fta_prefix = _prefix([game.fta_per_100 for game in games])
        self._pts_prefix = _prefix([game.pts for game in games])
        pf_values = [game.pf_per_100 if game.pf_per_100 is not None else 0.0 for game in games]
        pf_mask = [1.0 if game.pf_per_100 is not None else 0.0 for game in games]
        self._pf_prefix = _prefix(pf_values)
        self._pf_count_prefix = _prefix(pf_mask)

    def effect_for(
        self,
        *,
        game_id: str,
        game_date: date,
        home_abbr: str,
        away_abbr: str,
        prior_games: float,
        pace_weight: float,
        ft_weight: float,
        clip: float,
    ) -> CrewEffect:
        officials = self.officials_by_game.get(str(game_id))
        if not officials:
            officials = self.assignments.get((game_date, away_abbr, home_abbr))
        if not officials:
            return _identity()
        cut = bisect_left(self._dates, game_date)
        if cut < 20:
            return _identity()
        league_pace = self._pace_prefix[cut] / cut
        league_fta = self._fta_prefix[cut] / cut
        league_pts = self._pts_prefix[cut] / cut
        pf_n = self._pf_count_prefix[cut]
        league_pf = (self._pf_prefix[cut] / pf_n) if pf_n >= 20 else None
        if league_pace <= 0 or league_fta <= 0:
            return _identity()
        pace_deltas: list[float] = []
        ft_deltas: list[float] = []
        pts_deltas: list[float] = []
        samples: list[int] = []
        for official_id in officials:
            positions = [
                pos for pos in self.official_game_pos.get(int(official_id), []) if pos < cut
            ]
            samples.append(len(positions))
            if not positions:
                pace_deltas.append(0.0)
                ft_deltas.append(0.0)
                pts_deltas.append(0.0)
                continue
            weight = len(positions) / (len(positions) + prior_games)
            pace = sum(self.games[pos].pace for pos in positions) / len(positions)
            fta = sum(self.games[pos].fta_per_100 for pos in positions) / len(positions)
            pts = sum(self.games[pos].pts for pos in positions) / len(positions)
            pace_deltas.append(weight * (pace - league_pace))
            pts_deltas.append(weight * (pts - league_pts))
            pf_positions = [
                pos for pos in positions if self.games[pos].pf_per_100 is not None
            ]
            if league_pf is not None and pf_positions:
                pf = sum(self.games[pos].pf_per_100 or 0.0 for pos in pf_positions) / len(
                    pf_positions
                )
                pf_weight = len(pf_positions) / (len(pf_positions) + prior_games)
                fta_delta = weight * (fta - league_fta)
                pf_delta = pf_weight * (pf - league_pf)
                # Fouls and free throws are the same crew habit, on one scale.
                ft_deltas.append(0.5 * fta_delta + 0.5 * pf_delta * (league_fta / league_pf))
            else:
                ft_deltas.append(weight * (fta - league_fta))
        crew_pace = sum(pace_deltas) / len(pace_deltas)
        crew_ft = sum(ft_deltas) / len(ft_deltas)
        crew_pts = sum(pts_deltas) / len(pts_deltas)
        return CrewEffect(
            pace_factor=_clip(1.0 + pace_weight * crew_pace / league_pace, clip),
            ft_factor=_clip(1.0 + ft_weight * crew_ft / league_fta, clip),
            pace_delta=crew_pace,
            ft_delta=crew_ft,
            points_delta=crew_pts,
            sample_games=min(samples) if samples else 0,
        )


def load_referee_index(settings: Settings) -> RefereeIndex | None:
    environments = _read_rows(environment_path(settings))
    officials = _read_rows(officials_path(settings))
    if not environments or not officials:
        return None
    by_game: dict[str, dict[str, Any]] = {}
    for row in environments:
        if not row.get("regulation"):
            continue
        game_date = _as_date(row.get("game_date"))
        possessions = float(row.get("possessions") or 0.0)
        if game_date is None or possessions <= 0:
            continue
        pf = row.get("pf")
        by_game[str(row.get("game_id"))] = {
            "game_date": game_date,
            "pace": float(row.get("pace") or 0.0),
            "fta_per_100": 100.0 * float(row.get("fta") or 0.0) / possessions,
            "pf_per_100": (100.0 * float(pf) / possessions) if pf is not None else None,
            "pts": float(row.get("pts") or 0.0),
        }
    officials_by_game: dict[str, list[int]] = {}
    for row in officials:
        game_id = str(row.get("game_id") or "")
        if game_id not in by_game:
            continue
        try:
            official_id = int(row.get("official_id"))
        except (TypeError, ValueError):
            continue
        bucket = officials_by_game.setdefault(game_id, [])
        if official_id not in bucket:
            bucket.append(official_id)
    ordered = sorted(by_game.items(), key=lambda item: (item[1]["game_date"], item[0]))
    games: list[_GameStat] = []
    pos_by_game: dict[str, int] = {}
    for game_id, stats in ordered:
        pos_by_game[game_id] = len(games)
        games.append(
            _GameStat(
                game_date=stats["game_date"],
                game_id=game_id,
                pace=stats["pace"],
                fta_per_100=stats["fta_per_100"],
                pf_per_100=stats["pf_per_100"],
                pts=stats["pts"],
            )
        )
    official_game_pos: dict[int, list[int]] = {}
    for game_id, ids in officials_by_game.items():
        pos = pos_by_game.get(game_id)
        if pos is None:
            continue
        for official_id in ids:
            official_game_pos.setdefault(official_id, []).append(pos)
    jersey_to_id: dict[str, int] = {}
    for row in officials:
        jersey = str(row.get("jersey") or "").strip()
        try:
            official_id = int(row.get("official_id"))
        except (TypeError, ValueError):
            continue
        if jersey:
            jersey_to_id[jersey] = official_id
    assignments: dict[tuple[date, str, str], list[int]] = {}
    for row in _read_rows(assignments_path(settings)):
        game_date = _as_date(row.get("game_date"))
        if game_date is None:
            continue
        key = (game_date, str(row.get("away_abbr") or ""), str(row.get("home_abbr") or ""))
        jersey = str(row.get("jersey") or "").strip()
        official_id = jersey_to_id.get(jersey)
        if official_id is None:
            continue
        bucket = assignments.setdefault(key, [])
        if official_id not in bucket:
            bucket.append(official_id)
    if not games:
        return None
    return RefereeIndex(games, officials_by_game, official_game_pos, assignments)


def apply_referee_crew(
    settings: Settings,
    *,
    config: dict[str, Any],
    cache: Any,
    game_id: str,
    game_date: date,
    home_abbr: str,
    away_abbr: str,
    home_poss: float,
    away_poss: float,
    home_players: dict,
    away_players: dict,
) -> tuple[float, float]:
    """Scale possessions and ft_rate. No-op unless the flag is on and crews exist."""
    ctx = config.get("context") or {}
    if not bool(ctx.get("referees_enabled", False)):
        return home_poss, away_poss
    index = _cached_index(settings, cache)
    if index is None:
        return home_poss, away_poss
    effect = index.effect_for(
        game_id=game_id,
        game_date=game_date,
        home_abbr=home_abbr,
        away_abbr=away_abbr,
        prior_games=float(ctx.get("referees_prior_games", 25)),
        pace_weight=float(ctx.get("referees_pace_weight", 0.50)),
        ft_weight=float(ctx.get("referees_ft_weight", 0.50)),
        clip=float(ctx.get("referees_factor_clip", 0.015)),
    )
    if abs(effect.pace_factor - 1.0) > 1e-9:
        home_poss *= effect.pace_factor
        away_poss *= effect.pace_factor
        for group in (home_players, away_players):
            for pid, player in list(group.items()):
                group[pid] = replace(
                    player,
                    expected_team_possessions=player.expected_team_possessions
                    * effect.pace_factor,
                )
    if abs(effect.ft_factor - 1.0) > 1e-9:
        for group in (home_players, away_players):
            for pid, player in list(group.items()):
                rates: RateVector = player.rates
                group[pid] = replace(
                    player,
                    rates=replace(
                        rates,
                        ft_rate=min(0.45, max(0.02, rates.ft_rate * effect.ft_factor)),
                    ),
                )
    return home_poss, away_poss


def _cached_index(settings: Settings, cache: Any) -> RefereeIndex | None:
    if cache is None:
        return load_referee_index(settings)
    if not getattr(cache, "referee_index_ready", False):
        cache.referee_index = load_referee_index(settings)
        cache.referee_index_ready = True
    return cache.referee_index


def _identity() -> CrewEffect:
    return CrewEffect(1.0, 1.0, 0.0, 0.0, 0.0, 0)


def _clip(factor: float, clip: float) -> float:
    limit = abs(float(clip))
    return min(1.0 + limit, max(1.0 - limit, factor))


def _prefix(values: list[float]) -> list[float]:
    total = 0.0
    out = [0.0]
    for value in values:
        total += value
        out.append(total)
    return out
