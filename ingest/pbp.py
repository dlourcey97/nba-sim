"""Convert play-by-play into the plain events used by parse.py.

pbpstats possession objects and stats.nba.com PlayByPlayV3 actions both become
PossessionView rows. Shot zones use the same cutoffs as pbpstats: at the rim
inside 4 feet, short midrange inside 14 feet, and a corner three when the
shot is a three and the y coordinate is at or below 8.7 feet.
"""

from __future__ import annotations

import re
import unicodedata

from ingest.parse import CourtEvent, PossessionView, shot_zone

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def possessions_to_views(possessions) -> list[PossessionView]:
    from pbpstats.resources.enhanced_pbp import FieldGoal, FreeThrow, Rebound, Turnover

    views = []
    for possession in possessions:
        events = []
        counts = False
        saw_ending = False
        for event in possession.events:
            if getattr(event, "is_possession_ending_event", False):
                saw_ending = True
                counts = bool(getattr(event, "count_as_possession", False))
            kind = "other"
            made = False
            zone = None
            oreb = False
            if isinstance(event, FieldGoal):
                kind = "field_goal"
                made = bool(event.is_made)
                zone = shot_zone(
                    getattr(event, "shot_type", None),
                    getattr(event, "locX", None),
                    bool(getattr(event, "is_corner_3", False)),
                )
            elif isinstance(event, FreeThrow):
                kind = "free_throw"
                made = bool(getattr(event, "is_made", False))
            elif isinstance(event, Turnover):
                kind = "turnover"
            elif isinstance(event, Rebound):
                kind = "rebound"
                oreb = bool(getattr(event, "oreb", False))
            assist_id = None
            if kind == "field_goal" and made:
                assist_id = _player_id(getattr(event, "player2_id", None))
            events.append(
                CourtEvent(
                    kind=kind,
                    team_id=_int_or_none(getattr(event, "team_id", None)),
                    player_id=_player_id(getattr(event, "player1_id", None)),
                    lineup=_lineup(event),
                    made=made,
                    shot_zone=zone,
                    assist_player_id=assist_id,
                )
            )
        if not saw_ending:
            counts = True
        views.append(
            PossessionView(
                offense_team_id=int(possession.offense_team_id),
                period=int(possession.period),
                events=events,
                counts=counts,
            )
        )
    return views


def _lineup(event) -> dict[int, tuple[int, ...]]:
    try:
        raw = event.current_players
    except Exception:
        return {}
    lineup = {}
    for team_id, players in raw.items():
        ids = []
        for player_id in players:
            parsed = _player_id(player_id)
            if parsed is not None:
                ids.append(parsed)
        lineup[int(team_id)] = tuple(ids)
    return lineup


def _player_id(value) -> int | None:
    if value is None or value == "" or str(value) == "0":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value) -> int | None:
    if value is None or value == "" or value == 0:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def views_from_playbyplay_v3(actions: list[dict], players: list[dict]) -> list[PossessionView]:
    """Turn PlayByPlayV3 actions into possession views.

    Starters come from the box score. Substitutions keep the on-court lineup
    current so rate rows can see who shared the floor.
    """
    state = _PlayState(players)
    for index, action in enumerate(actions):
        state.observe(action, actions, index)
    state.close(counts=True)
    return state.views


class _PlayState:
    def __init__(self, players: list[dict]) -> None:
        self.roster: dict[int, list[dict]] = {}
        self.teams: list[int] = []
        self.lineups: dict[int, list[int]] = {}
        for player in players:
            team_id = int(player["team_id"])
            if team_id not in self.roster:
                self.teams.append(team_id)
                self.roster[team_id] = []
            self.roster[team_id].append(player)
            if _is_starter(player):
                bucket = self.lineups.setdefault(team_id, [])
                player_id = int(player["player_id"])
                if player_id not in bucket and len(bucket) < 5:
                    bucket.append(player_id)
        self.views: list[PossessionView] = []
        self.events: list[CourtEvent] = []
        self.offense: int | None = None
        self.period = 1
        self.awaiting_rebound = False
        self.last_shot_team: int | None = None

    def observe(self, action: dict, actions: list[dict], index: int) -> None:
        period = int(action.get("period") or self.period)
        if period != self.period:
            self.close(counts=True)
            self.period = period
            self.offense = None
            self.awaiting_rebound = False
        kind = str(action.get("actionType") or "").strip().lower()
        if kind == "substitution":
            self._substitute(action)
            return
        if kind == "jump ball":
            self._jump_ball(action)
            return
        if kind == "period" and str(action.get("subType") or "").lower() == "end":
            self.close(counts=self._buffer_counts())
            self.offense = None
            self.awaiting_rebound = False
            return
        if kind in {"made shot", "missed shot", "2pt", "3pt"}:
            self._shot(action, actions, index)
            return
        if kind == "rebound":
            self._rebound(action)
            return
        if kind == "turnover":
            self._turnover(action)
            return
        if kind == "free throw":
            self._free_throw(action)

    def close(self, *, counts: bool) -> None:
        if not self.events or self.offense is None:
            self.events = []
            return
        self.views.append(
            PossessionView(
                offense_team_id=self.offense,
                period=self.period,
                events=self.events,
                counts=counts and self._buffer_counts(),
            )
        )
        self.events = []

    def _buffer_counts(self) -> bool:
        return any(event.kind in {"field_goal", "free_throw", "turnover"} for event in self.events)

    def _shot(self, action: dict, actions: list[dict], index: int) -> None:
        team_id = _action_team(action)
        player_id = _player_id(action.get("personId"))
        if team_id is None:
            return
        self._ensure_offense(team_id)
        made = _is_made(action)
        assist_id = None
        if made:
            assist_id = _player_id(action.get("assistPersonId"))
            if assist_id is None:
                assist_id = self._assist_from_description(
                    str(action.get("description") or ""),
                    team_id=team_id,
                    shooter_id=player_id,
                )
        self.events.append(
            CourtEvent(
                kind="field_goal",
                team_id=team_id,
                player_id=player_id,
                lineup=self._snapshot(),
                made=made,
                shot_zone=_zone_for_action(action),
                assist_player_id=assist_id,
            )
        )
        self.last_shot_team = team_id
        if not made:
            self.awaiting_rebound = True
            return
        self.awaiting_rebound = False
        if player_id is not None and _and_one(actions, index, player_id):
            return
        self.close(counts=True)
        self.offense = self._other(team_id)

    def _rebound(self, action: dict) -> None:
        if not self.awaiting_rebound:
            return
        team_id = _rebound_team(action)
        self.awaiting_rebound = False
        if team_id is not None and team_id == self.last_shot_team:
            return
        self.close(counts=True)
        if team_id is not None:
            self.offense = team_id

    def _turnover(self, action: dict) -> None:
        team_id = _action_team(action)
        if team_id is None:
            return
        self._ensure_offense(team_id)
        self.awaiting_rebound = False
        self.events.append(
            CourtEvent(
                kind="turnover",
                team_id=team_id,
                player_id=_player_id(action.get("personId")),
                lineup=self._snapshot(),
            )
        )
        self.close(counts=True)
        self.offense = self._other(team_id)

    def _free_throw(self, action: dict) -> None:
        description = str(action.get("description") or "")
        subtype = str(action.get("subType") or "")
        team_id = _action_team(action)
        player_id = _player_id(action.get("personId"))
        if team_id is None or player_id is None:
            return
        technical = "technical" in subtype.lower() or "technical" in description.lower()
        if technical:
            if self.offense is not None:
                self.events.append(self._free_throw_event(action, team_id, player_id))
            return
        self._ensure_offense(team_id)
        self.events.append(self._free_throw_event(action, team_id, player_id))
        if not _last_free_throw(subtype):
            return
        if _is_made(action):
            self.awaiting_rebound = False
            self.close(counts=True)
            self.offense = self._other(team_id)
            return
        self.awaiting_rebound = True
        self.last_shot_team = team_id

    def _free_throw_event(self, action: dict, team_id: int, player_id: int) -> CourtEvent:
        return CourtEvent(
            kind="free_throw",
            team_id=team_id,
            player_id=player_id,
            lineup=self._snapshot(),
            made=_is_made(action),
        )

    def _assist_from_description(
        self,
        description: str,
        *,
        team_id: int,
        shooter_id: int | None,
    ) -> int | None:
        """Resolve ``(Last 1 AST)`` in a Made Shot description to a player id.

        PlayByPlayV3 often omits ``assistPersonId``; the passer is only named in
        the description. Prefer on-court teammates, then the full team roster.
        """
        match = re.search(r"\(([^()]+?)\s+\d+\s+AST\)", description, flags=re.IGNORECASE)
        if match is None:
            return None
        token = match.group(1).strip()
        if not token:
            return None
        exclude = {int(shooter_id)} if shooter_id is not None else set()
        on_court = self.lineups.get(team_id) or []
        court_players = [
            player
            for player in self.roster.get(team_id, [])
            if int(player["player_id"]) in set(on_court)
        ]
        hit = _match_player(token, court_players, exclude=exclude)
        if hit is not None:
            return hit
        return _match_player(token, self.roster.get(team_id, []), exclude=exclude)

    def _jump_ball(self, action: dict) -> None:
        winner = _tipped_to(str(action.get("description") or ""), self.roster)
        if winner is None:
            return
        team_id, _player = winner
        if self.awaiting_rebound and self.last_shot_team is not None and team_id != self.last_shot_team:
            self.awaiting_rebound = False
            self.close(counts=True)
        else:
            self.awaiting_rebound = False
        self.offense = team_id

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

    def _ensure_offense(self, team_id: int) -> None:
        if self.offense is None:
            self.offense = team_id

    def _other(self, team_id: int) -> int | None:
        for candidate in self.teams:
            if candidate != team_id:
                return candidate
        return None

    def _snapshot(self) -> dict[int, tuple[int, ...]]:
        return {team_id: tuple(player_ids) for team_id, player_ids in self.lineups.items() if player_ids}


def _zone_for_action(action: dict) -> str | None:
    x = _float_or_none(action.get("xLegacy"))
    y = _float_or_none(action.get("yLegacy"))
    value = int(action.get("shotValue") or 0)
    description = str(action.get("description") or "")
    if value == 3 or "3PT" in description.upper():
        coordinates_missing = (x in (None, 0)) and (y in (None, 0))
        corner = y is not None and y <= 87 and not coordinates_missing
        return shot_zone("Corner3" if corner else "Arc3", x, corner)
    distance = _float_or_none(action.get("shotDistance"))
    if (distance is None or distance == 0) and x not in (None, 0) and y is not None:
        distance = round((x * x + y * y) ** 0.5 / 10, 1)
    if distance is None:
        distance = 0.0
    if distance < 4:
        shot_type = "AtRim"
    elif distance < 14:
        shot_type = "ShortMidRange"
    else:
        shot_type = "LongMidRange"
    return shot_zone(shot_type, x, False)


def _and_one(actions: list[dict], index: int, shooter_id: int) -> bool:
    for action in actions[index + 1 : index + 8]:
        kind = str(action.get("actionType") or "").strip().lower()
        if kind == "free throw" and _player_id(action.get("personId")) == shooter_id:
            return True
        if kind in {"made shot", "missed shot", "turnover", "rebound", "period", "2pt", "3pt"}:
            return False
    return False


def _last_free_throw(subtype: str) -> bool:
    match = re.search(r"(\d+)\s+of\s+(\d+)", subtype)
    if match is None:
        return True
    return match.group(1) == match.group(2)


def _is_made(action: dict) -> bool:
    result = str(action.get("shotResult") or "").strip().lower()
    if result == "made":
        return True
    if result == "missed":
        return False
    return not str(action.get("description") or "").upper().startswith("MISS")


def _is_starter(player: dict) -> bool:
    return player.get("starter") in {True, 1, "1", "true", "True"}


def _action_team(action: dict) -> int | None:
    return _int_or_none(action.get("teamId"))


def _rebound_team(action: dict) -> int | None:
    team_id = _int_or_none(action.get("teamId"))
    if team_id is not None:
        return team_id
    return _int_or_none(action.get("personId"))


def _tipped_to(description: str, roster: dict[int, list[dict]]) -> tuple[int, int] | None:
    match = re.search(r"Tip to (.+)$", description)
    if match is None:
        return None
    hits: list[tuple[int, int]] = []
    for team_id, players in roster.items():
        for player in players:
            if _name_is(match.group(1), str(player.get("name") or "")):
                hits.append((team_id, int(player["player_id"])))
    if len(hits) == 1:
        return hits[0]
    return None


def _match_player(token: str, players: list[dict], *, exclude: set[int]) -> int | None:
    hits = [int(player["player_id"]) for player in players if _name_is(token, str(player.get("name") or ""))]
    available = [player_id for player_id in hits if player_id not in exclude]
    if len(available) == 1:
        return available[0]
    if len(hits) == 1:
        return hits[0]
    return None


def _name_is(token: str, full_name: str) -> bool:
    """True when a play-by-play name refers to a roster name.

    The feed uses last names, drops accents, and sometimes shortens a first
    name (Marc Morris for Marcus Morris Sr.).
    """
    token_parts = _name_parts(token)
    name_parts = _name_parts(full_name)
    if not token_parts or not name_parts:
        return False
    if len(token_parts) <= len(name_parts) and name_parts[-len(token_parts) :] == token_parts:
        return True
    if token_parts[-1] == name_parts[-1] and len(token_parts) > 1 and len(name_parts) > 1:
        return name_parts[0].startswith(token_parts[0]) or token_parts[0].startswith(name_parts[0])
    return False


def _name_parts(value: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", value)
    folded = "".join(char for char in folded if not unicodedata.combining(char)).lower()
    return [part for part in re.split(r"[^a-z0-9]+", folded) if part and part not in _SUFFIXES]


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
