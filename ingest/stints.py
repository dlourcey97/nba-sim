"""Extract compact on-court lineup stints from PlayByPlayV3 actions.

A stint is a stretch with a fixed 5-man lineup for one team. We track period,
clock, score margin (home − away), and elapsed possession endings so rotation
models can condition on game state without storing raw PBP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ingest.pbp import (
    _action_team,
    _is_starter,
    _match_player,
    _player_id,
)


@dataclass(frozen=True)
class LineupStint:
    team_id: int
    period: int
    start_clock_sec: float
    end_clock_sec: float
    duration_sec: float
    margin_start: int  # home − away at stint open
    margin_end: int
    possessions: int
    players: tuple[int, int, int, int, int]


_CLOCK_RE = re.compile(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?")


def clock_to_seconds(clock: object) -> float:
    """Parse ISO-ish NBA clock (PT11M27.00S) to seconds remaining in the period."""
    text = str(clock or "").strip()
    if not text:
        return 0.0
    match = _CLOCK_RE.match(text)
    if match is None:
        return 0.0
    minutes = float(match.group(1) or 0)
    seconds = float(match.group(2) or 0)
    return minutes * 60.0 + seconds


def margin_bucket(margin: int, *, close: int = 6, blowout: int = 15) -> str:
    abs_m = abs(int(margin))
    if abs_m < close:
        return "close"
    if abs_m < blowout:
        return "moderate"
    return "blowout"


def stints_from_actions(
    actions: list[dict],
    players: list[dict],
    *,
    home_team_id: int,
) -> list[LineupStint]:
    """Walk substitutions and score updates; emit one stint per lineup stretch."""
    tracker = _StintTracker(players, home_team_id=home_team_id)
    for action in actions:
        tracker.observe(action)
    tracker.close_all()
    return tracker.stints


def stint_rows(
    *,
    season: str,
    game_id: str,
    game_date,
    home_team_id: int,
    away_team_id: int,
    stints: list[LineupStint],
) -> list[dict]:
    """Flatten stints into schema rows (one row per team-stint)."""
    rows: list[dict] = []
    for stint in stints:
        if len(stint.players) != 5:
            continue
        mid_margin = (stint.margin_start + stint.margin_end) // 2
        # Home margin change over the stint; flip sign for the away team.
        home_pm = int(stint.margin_end - stint.margin_start)
        if stint.team_id == home_team_id:
            team_margin = mid_margin
            plus_minus = home_pm
        else:
            team_margin = -mid_margin
            plus_minus = -home_pm
        rows.append(
            {
                "season": season,
                "game_id": game_id,
                "game_date": game_date,
                "team_id": stint.team_id,
                "opponent_team_id": away_team_id if stint.team_id == home_team_id else home_team_id,
                "home_away": "H" if stint.team_id == home_team_id else "A",
                "period": stint.period,
                "duration_sec": round(stint.duration_sec, 2),
                "possessions": stint.possessions,
                "margin_bucket": margin_bucket(team_margin),
                "team_margin": int(team_margin),
                "plus_minus": int(plus_minus),
                "p1": stint.players[0],
                "p2": stint.players[1],
                "p3": stint.players[2],
                "p4": stint.players[3],
                "p5": stint.players[4],
            }
        )
    return rows


class _StintTracker:
    def __init__(self, players: list[dict], *, home_team_id: int) -> None:
        self.home_team_id = int(home_team_id)
        self.roster: dict[int, list[dict]] = {}
        self.lineups: dict[int, list[int]] = {}
        for player in players:
            team_id = int(player["team_id"])
            self.roster.setdefault(team_id, []).append(player)
            if _is_starter(player):
                bucket = self.lineups.setdefault(team_id, [])
                pid = int(player["player_id"])
                if pid not in bucket and len(bucket) < 5:
                    bucket.append(pid)
        self.score_home = 0
        self.score_away = 0
        self.period = 1
        self.clock_sec = 720.0
        self.possessions = 0
        self.open: dict[int, _OpenStint] = {}
        self.stints: list[LineupStint] = []
        for team_id, lineup in self.lineups.items():
            if len(lineup) == 5:
                self.open[team_id] = self._new_open(team_id, tuple(sorted(lineup)))

    def observe(self, action: dict) -> None:
        period = int(action.get("period") or self.period)
        clock = clock_to_seconds(action.get("clock"))
        if clock > 0 or str(action.get("clock") or "").startswith("PT"):
            self.clock_sec = clock
        if period != self.period:
            self.close_all()
            self.period = period
            # Reset clock for new period (OT = 5 min).
            self.clock_sec = 300.0 if period > 4 else 720.0
            for team_id, lineup in self.lineups.items():
                if len(lineup) == 5:
                    self.open[team_id] = self._new_open(team_id, tuple(sorted(lineup)))

        kind = str(action.get("actionType") or "").strip().lower()
        self._update_score(action)
        if kind == "substitution":
            self._substitute(action)
            return
        # Rough possession counter: made shots, turnovers, and last FT of a trip.
        if kind in {"made shot", "turnover"}:
            self.possessions += 1
            for open_stint in self.open.values():
                open_stint.possessions += 1
        elif kind == "free throw":
            subtype = str(action.get("subType") or "")
            match = re.search(r"(\d+)\s+of\s+(\d+)", subtype)
            if match is None or match.group(1) == match.group(2):
                if _is_made_ft(action):
                    self.possessions += 1
                    for open_stint in self.open.values():
                        open_stint.possessions += 1

    def close_all(self) -> None:
        for team_id in list(self.open):
            self._close(team_id)

    def _substitute(self, action: dict) -> None:
        team_id = _action_team(action)
        if team_id is None:
            return
        match = re.match(r"SUB:\s+(.+?)\s+FOR\s+(.+)$", str(action.get("description") or ""))
        if match is None:
            return
        lineup = self.lineups.setdefault(team_id, [])
        outgoing = _player_id(action.get("personId"))
        if outgoing in lineup:
            lineup.remove(outgoing)
        incoming = _match_player(match.group(1), self.roster.get(team_id, []), exclude=set(lineup))
        if incoming is not None and incoming not in lineup and len(lineup) < 5:
            lineup.append(incoming)
        key = tuple(sorted(lineup)) if len(lineup) == 5 else None
        current = self.open.get(team_id)
        if current is not None and (key is None or key != current.players):
            self._close(team_id)
        if key is not None and team_id not in self.open:
            self.open[team_id] = self._new_open(team_id, key)

    def _close(self, team_id: int) -> None:
        open_stint = self.open.pop(team_id, None)
        if open_stint is None:
            return
        end_clock = self.clock_sec
        # Same period: clock counts down; duration is start_clock - end_clock.
        if open_stint.period == self.period:
            duration = max(0.0, open_stint.start_clock_sec - end_clock)
        else:
            duration = max(0.0, open_stint.start_clock_sec)
        if duration < 1.0 and open_stint.possessions == 0:
            return
        self.stints.append(
            LineupStint(
                team_id=team_id,
                period=open_stint.period,
                start_clock_sec=open_stint.start_clock_sec,
                end_clock_sec=end_clock,
                duration_sec=duration,
                margin_start=open_stint.margin_start,
                margin_end=self._margin(),
                possessions=open_stint.possessions,
                players=open_stint.players,  # type: ignore[arg-type]
            )
        )

    def _new_open(self, team_id: int, players: tuple[int, ...]) -> _OpenStint:
        return _OpenStint(
            period=self.period,
            start_clock_sec=self.clock_sec,
            margin_start=self._margin(),
            possessions=0,
            players=players,
        )

    def _margin(self) -> int:
        return int(self.score_home - self.score_away)

    def _update_score(self, action: dict) -> None:
        sh = action.get("scoreHome")
        sa = action.get("scoreAway")
        if sh not in (None, "") and sa not in (None, ""):
            try:
                self.score_home = int(sh)
                self.score_away = int(sa)
            except (TypeError, ValueError):
                pass


@dataclass
class _OpenStint:
    period: int
    start_clock_sec: float
    margin_start: int
    possessions: int
    players: tuple[int, ...]


def _is_made_ft(action: dict) -> bool:
    result = str(action.get("shotResult") or "").strip().lower()
    if result == "made":
        return True
    if result == "missed":
        return False
    return not str(action.get("description") or "").upper().startswith("MISS")
