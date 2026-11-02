"""Split "projected under 0.5, played 8+" by what the pre-tip roster could see.

Causes, first match wins:

- a: not on the active roster and not in the projection
- b: on the active roster but left out of the projection
- c: in the projection, conditional mean at least 0.5, play probability under
  0.35, and he sat at least half of the last team window
- d: in the projection and he missed the previous team game
- e: everything else still in that miss bucket
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from ingest.rosters import active_roster_player_ids


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


class CauseIndex:
    """Team schedule, built once per season."""

    def __init__(self, schedule: list, bundles: list, season: str) -> None:
        del bundles, season
        self.team_games: dict[int, list[tuple[date, object]]] = defaultdict(list)
        for row in schedule:
            when = _as_date(row["game_date"])
            self.team_games[int(row["home_team_id"])].append((when, row["game_id"]))
            self.team_games[int(row["away_team_id"])].append((when, row["game_id"]))
        for games in self.team_games.values():
            games.sort()


def count_causes(
    projection,
    game_logs: dict,
    logs_by_game: dict,
    roster_rows: list,
    index: CauseIndex,
) -> tuple[int, int, int, int, int]:
    """Return cause counts a, b, c, d, e for one game."""
    counts = {"a": 0, "b": 0, "c": 0, "d": 0, "e": 0}
    when = _as_date(projection.game_date)
    by_id = {int(player.player_id): player for player in projection.players}
    active_by_team: dict[int, set[int]] = {}
    for team_id in (int(projection.home_team_id), int(projection.away_team_id)):
        active_by_team[team_id] = set(
            active_roster_player_ids(roster_rows, team_id=team_id, as_of=when)
        )
    for pid, log in game_logs.items():
        actual = float(log.get("minutes") or 0.0)
        player = by_id.get(int(pid))
        if player is None or player.minutes.out or float(player.minutes.play_prob) <= 0.0:
            expected = 0.0
            cond = 0.0
            play_prob = 0.0
        else:
            cond = float(player.minutes.mean)
            play_prob = float(player.minutes.play_prob)
            expected = cond * play_prob
        if not (expected < 0.5 and actual >= 8.0):
            continue
        team_id = int(log["team_id"])
        prev_games = [game for game in index.team_games[team_id] if game[0] < when]
        miss_streak = 0
        for _team_when, team_game in reversed(prev_games):
            prev_log = logs_by_game.get(team_game, {}).get(int(pid))
            played = prev_log is not None and float(prev_log.get("minutes") or 0.0) > 0.0
            if played:
                break
            miss_streak += 1
        missed_prev = miss_streak >= 1 and len(prev_games) > 0
        window = prev_games[-10:]
        if window:
            played_n = 0
            for _team_when, team_game in window:
                prev_log = logs_by_game.get(team_game, {}).get(int(pid))
                if prev_log is not None and float(prev_log.get("minutes") or 0.0) > 0.0:
                    played_n += 1
            appear = played_n / len(window)
        else:
            appear = 1.0
        on_roster = int(pid) in active_by_team.get(team_id, set())
        if player is None and not on_roster:
            cause = "a"
        elif player is None and on_roster:
            cause = "b"
        elif cond >= 0.5 and play_prob < 0.35 and appear <= 0.5:
            cause = "c"
        elif missed_prev:
            cause = "d"
        else:
            cause = "e"
        counts[cause] += 1
    return counts["a"], counts["b"], counts["c"], counts["d"], counts["e"]
