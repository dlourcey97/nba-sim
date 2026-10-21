"""In-memory confident-stat-line picks from raw sim arrays.

Never persists raw runs — only the resulting pick summaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from ingest.injuries import InjuryEntry
from projections.build import GameProjection
from sim.engine import GameSimResult

# Inclusive windows around the median.
_WINDOWS = {
    "pts": 3,
    "reb": 2,
    "ast": 2,
    "stl": 1,
    "blk": 1,
}
_MIN_MEDIAN = {
    "pts": 4.0,
    "reb": 4.0,
    "ast": 4.0,
    "stl": 2.0,
    "blk": 2.0,
}
_STAT_ARRAY = {
    "pts": "pts",
    "reb": "reb",
    "ast": "ast",
    "stl": "stl",
    "blk": "blk",
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
        }


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
        # Overrides that resolved a Q/probable into available still count as
        # uncertain / changed-role for confidence exclusion when reason notes it.
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
        # Skip players projected out / near-zero minutes.
        med_min = float(np.median(result.minutes[index]))
        if med_min < 8.0:
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
            window = _WINDOWS[stat]
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
            # Integer-ish display for counting stats.
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
                )
            )
        player_picks.sort(key=lambda p: p.confidence, reverse=True)
        candidates.extend(player_picks[:max_per_player])

    candidates.sort(key=lambda p: p.confidence, reverse=True)
    return candidates


def select_slate_picks(
    all_picks: Sequence[ConfidentPick],
    *,
    min_picks: int = 6,
    max_picks: int = 10,
    max_per_game: int = 3,
    max_per_player: int = 2,
) -> list[ConfidentPick]:
    """Highest confidence first, with per-game / per-player caps."""
    selected: list[ConfidentPick] = []
    per_game: dict[str, int] = {}
    per_player: dict[int, int] = {}
    for pick in sorted(all_picks, key=lambda p: p.confidence, reverse=True):
        if len(selected) >= max_picks:
            break
        if per_game.get(pick.game_id, 0) >= max_per_game:
            continue
        if per_player.get(pick.player_id, 0) >= max_per_player:
            continue
        # Avoid duplicate player+stat
        if any(s.player_id == pick.player_id and s.stat == pick.stat for s in selected):
            continue
        selected.append(pick)
        per_game[pick.game_id] = per_game.get(pick.game_id, 0) + 1
        per_player[pick.player_id] = per_player.get(pick.player_id, 0) + 1
    if len(selected) < min_picks:
        # Keep what we have; caller notes shortfall.
        return selected
    return selected
