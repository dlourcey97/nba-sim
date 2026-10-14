"""Convert pbpstats possessions into the plain events used by parse.py."""

from __future__ import annotations

from ingest.parse import CourtEvent, PossessionView, shot_zone


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
            events.append(
                CourtEvent(
                    kind=kind,
                    team_id=_int_or_none(getattr(event, "team_id", None)),
                    player_id=_player_id(getattr(event, "player1_id", None)),
                    lineup=_lineup(event),
                    made=made,
                    shot_zone=zone,
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
