"""In-memory confident-stat-line picks from raw sim arrays.

Never persists raw runs — only the resulting pick summaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from ingest.injuries import InjuryEntry
from projections.build import GameProjection, PlayerProjection
from sim.engine import GameSimResult

_STAT_ARRAY = {
    "pts": "pts",
    "reb": "reb",
    "ast": "ast",
    "stl": "stl",
    "blk": "blk",
}
_MIN_MEDIAN = {
    "pts": 10.0,
    "reb": 5.0,
    "ast": 4.0,
    "stl": 2.0,
    "blk": 2.0,
}


@dataclass(frozen=True)
class ConfidentPick:
    player_id: int
    player_name: str
    team_abbr: str
    opponent_abbr: str
    game_id: str
    stat: str
    median: float
    lo: float
    hi: float
    confidence: float  # 0–1
    range_label: str
    proj_minutes: float = 0.0
    play_prob: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "team_abbr": self.team_abbr,
            "opponent_abbr": self.opponent_abbr,
            "game_id": self.game_id,
            "stat": self.stat,
            "median": self.median,
            "lo": self.lo,
            "hi": self.hi,
            "confidence": self.confidence,
            "range_label": self.range_label,
            "proj_minutes": self.proj_minutes,
            "play_prob": self.play_prob,
        }


def scaled_window(stat: str, median: float) -> float:
    """Half-width around the median; stars get wider absolute windows."""
    m = abs(float(median))
    if stat == "pts":
        return max(3.0, 0.15 * m)
    if stat in {"reb", "ast"}:
        return max(2.0, 0.20 * m)
    # stl / blk
    return 1.0


def excluded_player_ids(
    injuries: Sequence[InjuryEntry],
    game_date,
) -> set[int]:
    """Players who were Q / minutes-capped / role-changed tonight."""
    excluded: set[int] = set()
    for entry in injuries:
        if entry.game_date != game_date or entry.player_id is None:
            continue
        pid = int(entry.player_id)
        status = entry.status.lower()
        if status == "questionable":
            excluded.add(pid)
        if entry.minutes_cap is not None:
            excluded.add(pid)
        reason = (entry.reason or "").lower()
        if entry.source == "override" and (
            "assume" in reason
            or "q " in reason
            or reason.startswith("q ")
            or "questionable" in reason
            or "probable" in reason
            or "upgraded" in reason
            or "late scratch" in reason
            or "minutes" in reason
            or "starter" in reason
            or "bench" in reason
            or "role" in reason
        ):
            excluded.add(pid)
    return excluded


def _is_core_rotation(player: PlayerProjection, med_min: float) -> bool:
    """Starters or core rotation with median minutes 26+."""
    if med_min < 26.0:
        return False
    if player.started:
        return True
    # Core rotation: top-ish depth and real minutes projection.
    return int(player.depth_rank) <= 7 and float(player.minutes.mean) >= 26.0


def confident_picks_for_game(
    projection: GameProjection,
    result: GameSimResult,
    *,
    excluded_ids: set[int],
    max_per_player: int = 2,
) -> list[ConfidentPick]:
    """Score every eligible player/stat; return sorted picks for one game."""
    opp = {"H": projection.away_abbr, "A": projection.home_abbr}
    by_id = {p.player_id: p for p in projection.players}
    candidates: list[ConfidentPick] = []

    for index, player_id in enumerate(result.player_ids):
        pid = int(player_id)
        if pid in excluded_ids:
            continue
        proj = by_id.get(pid)
        if proj is None:
            continue
        play_prob = float(getattr(proj.minutes, "play_prob", 1.0) or 0.0)
        if play_prob < 0.95:
            continue
        status = (proj.status or "available").lower()
        if status in {"questionable", "out", "doubtful"}:
            continue
        med_min = float(np.median(result.minutes[index]))
        if not _is_core_rotation(proj, med_min):
            continue
        team = result.team_abbrs[index]
        opponent = opp[result.home_away[index]]
        name = result.player_names[index]

        player_picks: list[ConfidentPick] = []
        for stat, attr in _STAT_ARRAY.items():
            draws = getattr(result, attr)[index]
            median = float(np.median(draws))
            if median < _MIN_MEDIAN[stat]:
                continue
            window = scaled_window(stat, median)
            lo = median - window
            hi = median + window
            conf = float(np.mean((draws >= lo) & (draws <= hi)))
            unit = {
                "pts": "points",
                "reb": "rebounds",
                "ast": "assists",
                "stl": "steals",
                "blk": "blocks",
            }[stat]
            lo_i = int(round(lo))
            hi_i = int(round(hi))
            med_i = int(round(median))
            range_label = f"{lo_i}-{hi_i} {unit}"
            player_picks.append(
                ConfidentPick(
                    player_id=pid,
                    player_name=name,
                    team_abbr=team,
                    opponent_abbr=opponent,
                    game_id=projection.game_id,
                    stat=stat.upper(),
                    median=float(med_i),
                    lo=float(lo_i),
                    hi=float(hi_i),
                    confidence=conf,
                    range_label=range_label,
                    proj_minutes=float(med_min),
                    play_prob=play_prob,
                )
            )
        player_picks.sort(key=lambda p: p.confidence, reverse=True)
        candidates.extend(player_picks[:max_per_player])

    candidates.sort(key=lambda p: p.confidence, reverse=True)
    return candidates


_DD_STATS = ("pts", "reb", "ast", "stl", "blk")


def double_double_from_draws(
    draws: dict[str, np.ndarray],
) -> tuple[float, str, float]:
    """P(two of PTS/REB/AST/STL/BLK are 10+) and the pair with the highest joint rate.

    ``draws`` values are one player's per-sim stat arrays. Nothing is stored.
    """
    flags = {stat: np.asarray(draws[stat], dtype=float) >= 10.0 for stat in _DD_STATS}
    stacked = np.vstack([flags[stat] for stat in _DD_STATS])
    p_dd = float(np.mean(stacked.sum(axis=0) >= 2))
    best_label = ""
    best_p = -1.0
    for i, left in enumerate(_DD_STATS):
        for right in _DD_STATS[i + 1 :]:
            joint = float(np.mean(flags[left] & flags[right]))
            if joint > best_p:
                best_p = joint
                best_label = f"{left.upper()}+{right.upper()}"
    return p_dd, best_label, max(best_p, 0.0)


def double_double_candidates(
    projection: GameProjection,
    result: GameSimResult,
    *,
    min_minutes: float = 26.0,
) -> list[ConfidentPick]:
    """Players with median minutes >= 26, excluding QUESTIONABLE / OUT / Doubtful.

    Ranked by P(double-double). One row per player. Raw runs are not retained.
    """
    opp = {"H": projection.away_abbr, "A": projection.home_abbr}
    by_id = {p.player_id: p for p in projection.players}
    candidates: list[ConfidentPick] = []
    for index, player_id in enumerate(result.player_ids):
        pid = int(player_id)
        proj = by_id.get(pid)
        if proj is None:
            continue
        status = (proj.status or "available").lower()
        if status in {"questionable", "out", "doubtful"}:
            continue
        med_min = float(np.median(result.minutes[index]))
        if med_min < min_minutes:
            continue
        draws = {stat: getattr(result, stat)[index] for stat in _DD_STATS}
        p_dd, pair, _joint = double_double_from_draws(draws)
        if p_dd <= 0.0 or not pair:
            continue
        team = result.team_abbrs[index]
        candidates.append(
            ConfidentPick(
                player_id=pid,
                player_name=result.player_names[index],
                team_abbr=team,
                opponent_abbr=opp[result.home_away[index]],
                game_id=projection.game_id,
                stat=f"DD_{pair.replace('+', '_')}",
                median=float(np.median(draws["pts"])),
                lo=10.0,
                hi=10.0,
                confidence=p_dd,
                range_label=pair,
                proj_minutes=med_min,
                play_prob=float(getattr(proj.minutes, "play_prob", 1.0) or 0.0),
            )
        )
    candidates.sort(key=lambda pick: (pick.confidence, pick.proj_minutes), reverse=True)
    return candidates


def select_slate_picks(
    all_picks: Sequence[ConfidentPick],
    *,
    n_picks: int = 8,
    max_per_game: int = 3,
    max_per_player: int = 2,
) -> list[ConfidentPick]:
    """Highest confidence first — exactly ``n_picks`` when enough candidates exist.

    On short slates (e.g. 2 games), raise the per-game cap just enough to allow
    ``n_picks`` while still preferring diversification.
    """
    n_games = len({p.game_id for p in all_picks}) or 1
    game_cap = max(max_per_game, (n_picks + n_games - 1) // n_games)
    selected: list[ConfidentPick] = []
    per_game: dict[str, int] = {}
    per_player: dict[int, int] = {}
    for pick in sorted(all_picks, key=lambda p: p.confidence, reverse=True):
        if len(selected) >= n_picks:
            break
        if per_game.get(pick.game_id, 0) >= game_cap:
            continue
        if per_player.get(pick.player_id, 0) >= max_per_player:
            continue
        if any(s.player_id == pick.player_id and s.stat == pick.stat for s in selected):
            continue
        selected.append(pick)
        per_game[pick.game_id] = per_game.get(pick.game_id, 0) + 1
        per_player[pick.player_id] = per_player.get(pick.player_id, 0) + 1
    return selected
