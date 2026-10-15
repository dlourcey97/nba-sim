"""Reduce simulation arrays to percentile summaries in memory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Sequence

import numpy as np

from nba_sim.schema import PLAYER_STATS
from projections.build import GameProjection
from sim.engine import GameSimResult

_PERCENTILES = (10, 25, 50, 75, 90)


@dataclass
class StatSummary:
    mean: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float

    def as_dict(self) -> dict[str, float]:
        return {
            "mean": self.mean,
            "p10": self.p10,
            "p25": self.p25,
            "p50": self.p50,
            "p75": self.p75,
            "p90": self.p90,
        }


@dataclass
class PlayerSummary:
    player_id: int
    player_name: str
    team_abbr: str
    opponent_abbr: str
    home_away: str
    stats: dict[str, StatSummary]
    thresholds: dict[str, dict[str, float]]


@dataclass
class GameSummary:
    season: str
    game_id: str
    game_date: date
    home_abbr: str
    away_abbr: str
    runs: int
    seed: int
    simulated_at: datetime
    home_win_prob: float
    overtime_prob: float
    home_pts: StatSummary
    away_pts: StatSummary
    margin: StatSummary
    total: StatSummary
    players: list[PlayerSummary]


def summarize_game(
    projection: GameProjection,
    result: GameSimResult,
    *,
    thresholds: Sequence[tuple[str, float]] | None = None,
) -> GameSummary:
    """Build distribution summaries. Does not persist anything."""
    threshold_list = list(thresholds or [])
    margin = result.home_pts - result.away_pts
    total = result.home_pts + result.away_pts
    players: list[PlayerSummary] = []
    opp = {
        "H": projection.away_abbr,
        "A": projection.home_abbr,
    }
    for index, player_id in enumerate(result.player_ids):
        arrays = {
            "pts": result.pts[index],
            "reb": result.reb[index],
            "ast": result.ast[index],
            "fg3m": result.fg3m[index],
            "stl": result.stl[index],
            "blk": result.blk[index],
            "tov": result.tov[index],
            "min": result.minutes[index],
        }
        arrays["pra"] = arrays["pts"] + arrays["reb"] + arrays["ast"]
        arrays["pr"] = arrays["pts"] + arrays["reb"]
        arrays["pa"] = arrays["pts"] + arrays["ast"]
        arrays["ra"] = arrays["reb"] + arrays["ast"]
        stats = {name: _summary(arrays[name]) for name in PLAYER_STATS}
        probs: dict[str, dict[str, float]] = {}
        for stat_name, cutoff in threshold_list:
            if stat_name not in arrays:
                continue
            probs.setdefault(stat_name, {})[str(cutoff)] = float(
                np.mean(arrays[stat_name] >= cutoff)
            )
        players.append(
            PlayerSummary(
                player_id=int(player_id),
                player_name=result.player_names[index],
                team_abbr=result.team_abbrs[index],
                opponent_abbr=opp[result.home_away[index]],
                home_away=result.home_away[index],
                stats=stats,
                thresholds=probs,
            )
        )
    return GameSummary(
        season=projection.season,
        game_id=projection.game_id,
        game_date=projection.game_date,
        home_abbr=projection.home_abbr,
        away_abbr=projection.away_abbr,
        runs=result.runs,
        seed=result.seed,
        simulated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        home_win_prob=float(np.mean(result.home_pts > result.away_pts)),
        overtime_prob=float(np.mean(result.overtime)),
        home_pts=_summary(result.home_pts),
        away_pts=_summary(result.away_pts),
        margin=_summary(margin),
        total=_summary(total),
        players=players,
    )


def _summary(values: np.ndarray) -> StatSummary:
    pct = np.percentile(values, _PERCENTILES)
    return StatSummary(
        mean=float(np.mean(values)),
        p10=float(pct[0]),
        p25=float(pct[1]),
        p50=float(pct[2]),
        p75=float(pct[3]),
        p90=float(pct[4]),
    )


def summary_to_json_dict(summary: GameSummary) -> dict[str, Any]:
    return {
        "season": summary.season,
        "game_id": summary.game_id,
        "game_date": summary.game_date.isoformat(),
        "home_abbr": summary.home_abbr,
        "away_abbr": summary.away_abbr,
        "runs": summary.runs,
        "seed": summary.seed,
        "simulated_at": summary.simulated_at.isoformat() + "Z",
        "home_win_prob": summary.home_win_prob,
        "overtime_prob": summary.overtime_prob,
        "home_pts": summary.home_pts.as_dict(),
        "away_pts": summary.away_pts.as_dict(),
        "margin": summary.margin.as_dict(),
        "total": summary.total.as_dict(),
        "players": [
            {
                "player_id": player.player_id,
                "player_name": player.player_name,
                "team_abbr": player.team_abbr,
                "opponent_abbr": player.opponent_abbr,
                "home_away": player.home_away,
                "stats": {name: stat.as_dict() for name, stat in player.stats.items()},
                "thresholds": player.thresholds,
            }
            for player in summary.players
        ],
    }
