"""Build a ResumeState from a live box score and play-by-play.

The box score is the current line. Play-by-play supplies who has the ball,
who is on the floor when the box does not say, and the state at a past horn
(halftime, end of the third) without using anything after that horn.
"""

from __future__ import annotations

from sim.resume import PlayerLive, ResumeState, TeamLive, clock_to_seconds
from sim.possession_log import PERIOD_SECONDS

_SHOTS = {"2pt", "3pt"}
_TIMEOUTS_FULL = 7


def state_now(box: dict, actions: list[dict]) -> ResumeState:
    """Current state. Counting stats come from the box; the ball from the feed."""
    walked = _walk(box, actions, stop_period_end=None)
    _overlay_box(walked, box)
    return walked


def state_at_period_end(box: dict, actions: list[dict], period: int) -> ResumeState:
    """State at the horn of ``period`` (2 = halftime, 3 = end of the third).

    Only actions through that horn are applied. The next period starts with a
    clean foul count. Timeouts already called stay spent.
    """
    state = _walk(box, actions, stop_period_end=int(period))
    state.period = int(period)
    state.clock_seconds = 0.0
    state.home.fouls_this_period = 0
    state.away.fouls_this_period = 0
    state.home.in_bonus = False
    state.away.in_bonus = False
    return state


def _walk(box: dict, actions: list[dict], stop_period_end: int | None) -> ResumeState:
    game = box["game"]
    home_raw = game["homeTeam"]
    away_raw = game["awayTeam"]
    home = TeamLive(team_id=int(home_raw["teamId"]), abbr=str(home_raw.get("teamTricode") or ""))
    away = TeamLive(team_id=int(away_raw["teamId"]), abbr=str(away_raw.get("teamTricode") or ""))
    players: dict[int, PlayerLive] = {}
    on_court: dict[int, list[int]] = {home.team_id: [], away.team_id: []}
    entered: dict[int, float] = {}
    for team_id, raw_team in ((home.team_id, home_raw), (away.team_id, away_raw)):
        for raw in raw_team.get("players") or []:
            player_id = int(raw["personId"])
            name = (
                f"{raw.get('firstName', '')} {raw.get('familyName', '')}".strip()
                or str(raw.get("name") or player_id)
            )
            players[player_id] = PlayerLive(player_id=player_id, name=name, team_id=team_id)
            if str(raw.get("starter") or "") in {"1", "True", "true"}:
                on_court[team_id].append(player_id)
                entered[player_id] = 0.0
    for team_id, lineup in on_court.items():
        del lineup[5:]
        for player_id in lineup:
            players[player_id].on_court = True
    home.on_court = list(on_court[home.team_id])
    away.on_court = list(on_court[away.team_id])
    possession: int | None = None
    period_fouls = {home.team_id: 0, away.team_id: 0}
    timeouts_used = {home.team_id: 0, away.team_id: 0}
    last_period = 1
    last_clock = PERIOD_SECONDS

    for action in actions:
        period = int(action.get("period") or last_period)
        if str(action.get("periodType") or "REGULAR").upper() not in {"REGULAR", ""}:
            break
        if period > 4:
            break
        clock = clock_to_seconds(action.get("clock"))
        if action.get("actionType") == "period" and action.get("subType") == "end":
            _close_minutes(players, entered, on_court, period, 0.0)
            _read_score(action, home, away)
            if stop_period_end is not None and period >= stop_period_end:
                last_period = period
                last_clock = 0.0
                possession = _possession(action, possession)
                break
            period_fouls[home.team_id] = 0
            period_fouls[away.team_id] = 0
            last_period = period
            last_clock = 0.0
            continue
        if action.get("actionType") == "period" and action.get("subType") == "start":
            period_fouls[home.team_id] = 0
            period_fouls[away.team_id] = 0
            last_period = period
            last_clock = clock
            continue
        _apply_action(action, players, on_court, entered, period_fouls, timeouts_used, period, clock)
        _read_score(action, home, away)
        possession = _possession(action, possession)
        last_period = period
        last_clock = clock

    _close_minutes(players, entered, on_court, last_period, last_clock)
    home.on_court = [player_id for player_id in on_court[home.team_id] if players[player_id].on_court]
    away.on_court = [player_id for player_id in on_court[away.team_id] if players[player_id].on_court]
    home.fouls_this_period = int(period_fouls[home.team_id])
    away.fouls_this_period = int(period_fouls[away.team_id])
    home.timeouts_remaining = max(0, _TIMEOUTS_FULL - timeouts_used[home.team_id])
    away.timeouts_remaining = max(0, _TIMEOUTS_FULL - timeouts_used[away.team_id])
    home.in_bonus = _in_bonus(home.fouls_this_period, last_clock)
    away.in_bonus = _in_bonus(away.fouls_this_period, last_clock)
    for line in players.values():
        line.on_court = line.player_id in home.on_court or line.player_id in away.on_court
    return ResumeState(
        period=last_period,
        clock_seconds=last_clock,
        home=home,
        away=away,
        players=players,
        possession_team_id=possession,
    )


def _overlay_box(state: ResumeState, box: dict) -> None:
    """Trust the live box for the score, the clock, and the counting line."""
    game = box["game"]
    home_raw = game["homeTeam"]
    away_raw = game["awayTeam"]
    state.home.score = int(home_raw.get("score") or 0)
    state.away.score = int(away_raw.get("score") or 0)
    state.period = int(game.get("period") or state.period or 1)
    state.clock_seconds = clock_to_seconds(game.get("gameClock"))
    if game.get("homeTeam", {}).get("timeoutsRemaining") is not None:
        state.home.timeouts_remaining = int(home_raw.get("timeoutsRemaining") or 0)
    if away_raw.get("timeoutsRemaining") is not None:
        state.away.timeouts_remaining = int(away_raw.get("timeoutsRemaining") or 0)
    state.home.in_bonus = bool(home_raw.get("inBonus"))
    state.away.in_bonus = bool(away_raw.get("inBonus"))
    state.home.on_court = []
    state.away.on_court = []
    for side, raw_team in ((state.home, home_raw), (state.away, away_raw)):
        for raw in raw_team.get("players") or []:
            player_id = int(raw["personId"])
            line = state.players.get(player_id)
            if line is None:
                name = f"{raw.get('firstName', '')} {raw.get('familyName', '')}".strip()
                line = PlayerLive(player_id=player_id, name=name, team_id=side.team_id)
                state.players[player_id] = line
            stats = raw.get("statistics") or {}
            line.minutes = _minutes(stats.get("minutes"))
            line.pts = _num(stats.get("points"))
            line.reb = _num(stats.get("reboundsTotal"))
            line.ast = _num(stats.get("assists"))
            line.fouls = int(_num(stats.get("foulsPersonal")))
            line.fga = _num(stats.get("fieldGoalsAttempted"))
            line.fgm = _num(stats.get("fieldGoalsMade"))
            line.fta = _num(stats.get("freeThrowsAttempted"))
            line.ftm = _num(stats.get("freeThrowsMade"))
            line.tov = _num(stats.get("turnovers"))
            line.on_court = str(raw.get("oncourt") or "") in {"1", "True", "true"}
            if line.on_court:
                side.on_court.append(player_id)


def _apply_action(
    action: dict,
    players: dict[int, PlayerLive],
    on_court: dict[int, list[int]],
    entered: dict[int, float],
    period_fouls: dict[int, int],
    timeouts_used: dict[int, int],
    period: int,
    clock: float,
) -> None:
    kind = str(action.get("actionType") or "")
    team_id = action.get("teamId")
    team_id = int(team_id) if team_id not in (None, "", 0) else None
    player_id = action.get("personId")
    player_id = int(player_id) if player_id not in (None, "", 0) else None
    if player_id is not None and player_id not in players and team_id is not None:
        players[player_id] = PlayerLive(
            player_id=player_id,
            name=str(action.get("playerName") or player_id),
            team_id=team_id,
        )
    elapsed = _elapsed(period, clock)
    if kind == "substitution" and player_id is not None and team_id is not None:
        lineup = on_court.setdefault(team_id, [])
        if action.get("subType") == "out":
            _bank_minutes(players, entered, player_id, elapsed)
            if player_id in lineup:
                lineup.remove(player_id)
            if player_id in players:
                players[player_id].on_court = False
        elif action.get("subType") == "in":
            if player_id not in lineup:
                lineup.append(player_id)
            entered[player_id] = elapsed
            if player_id in players:
                players[player_id].on_court = True
        return
    if kind == "timeout" and team_id is not None:
        timeouts_used[team_id] = timeouts_used.get(team_id, 0) + 1
        return
    if kind == "foul" and player_id is not None and player_id in players:
        if action.get("subType") != "technical":
            players[player_id].fouls += 1
            if team_id is not None:
                period_fouls[team_id] = period_fouls.get(team_id, 0) + 1
        return
    line = players.get(player_id) if player_id is not None else None
    if line is None:
        return
    if kind in _SHOTS:
        line.fga += 1
        if action.get("shotResult") == "Made":
            line.fgm += 1
            line.pts += 3 if kind == "3pt" else 2
            assist = action.get("assistPersonId")
            if assist not in (None, "", 0):
                assist_id = int(assist)
                if assist_id in players:
                    players[assist_id].ast += 1
    elif kind == "freethrow":
        line.fta += 1
        if action.get("shotResult") == "Made":
            line.ftm += 1
            line.pts += 1
    elif kind == "rebound" and action.get("subType") in {"offensive", "defensive"}:
        line.reb += 1
    elif kind == "turnover":
        line.tov += 1


def _close_minutes(players, entered, on_court, period: int, clock: float) -> None:
    elapsed = _elapsed(period, clock)
    for lineup in on_court.values():
        for player_id in list(lineup):
            _bank_minutes(players, entered, player_id, elapsed)
            entered[player_id] = elapsed


def _bank_minutes(players, entered, player_id: int, elapsed: float) -> None:
    start = entered.get(player_id)
    if start is None or player_id not in players:
        return
    players[player_id].minutes += max(0.0, elapsed - start) / 60.0
    entered[player_id] = elapsed


def _elapsed(period: int, clock: float) -> float:
    period = min(max(int(period), 1), 4)
    clock = min(max(float(clock), 0.0), PERIOD_SECONDS)
    return (period - 1) * PERIOD_SECONDS + (PERIOD_SECONDS - clock)


def _read_score(action: dict, home: TeamLive, away: TeamLive) -> None:
    if action.get("scoreHome") in (None, ""):
        return
    try:
        home.score = int(action["scoreHome"])
        away.score = int(action["scoreAway"])
    except (TypeError, ValueError):
        return


def _possession(action: dict, previous: int | None) -> int | None:
    value = action.get("possession")
    if value in (None, "", 0):
        return previous
    try:
        return int(value)
    except (TypeError, ValueError):
        return previous


def _in_bonus(fouls: int, clock: float) -> bool:
    if fouls >= 5:
        return True
    return clock <= 120.0 and fouls >= 2


def _minutes(value) -> float:
    if value is None or value == "":
        return 0.0
    text = str(value)
    if text.startswith("PT"):
        return clock_to_seconds(text) / 60.0
    try:
        if ":" in text:
            mins, secs = text.split(":", 1)
            return float(mins) + float(secs) / 60.0
        return float(text)
    except ValueError:
        return 0.0


def _num(value) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
