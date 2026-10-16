"""Build as-of-date team roster timelines from game logs (and optional API)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from nba_sim.settings import Settings
from nba_sim.storage import read_rows, store_rows


def team_rosters_from_logs(
    season: str,
    log_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Derive player stints from box-score appearances.

    Consecutive games for the same team form one stint. ``from_date`` is the
    first game date on that team; ``to_date`` is the first game date on a
    different team (exclusive end), or null for an open stint.
    """
    by_player: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in log_rows:
        by_player[int(row["player_id"])].append(row)
    rows: list[dict[str, object]] = []
    for player_id, appearances in by_player.items():
        ordered = sorted(
            appearances,
            key=lambda item: (item["game_date"], str(item["game_id"])),
        )
        stint_team: int | None = None
        stint_abbr = ""
        stint_name = ""
        stint_position: str | None = None
        stint_from: date | None = None
        for appearance in ordered:
            team_id = int(appearance["team_id"])
            game_date = appearance["game_date"]
            if not isinstance(game_date, date):
                game_date = date.fromisoformat(str(game_date))
            name = str(appearance.get("player_name") or f"player:{player_id}")
            abbr = str(appearance.get("team_abbr") or "")
            position = appearance.get("position")
            position_s = None if position is None else str(position)
            if stint_team is None:
                stint_team = team_id
                stint_abbr = abbr
                stint_name = name
                stint_position = position_s
                stint_from = game_date
                continue
            if team_id != stint_team:
                rows.append(
                    _stint_row(
                        season=season,
                        team_id=stint_team,
                        team_abbr=stint_abbr,
                        player_id=player_id,
                        player_name=stint_name,
                        position=stint_position,
                        from_date=stint_from,
                        to_date=game_date,
                        source="game_log",
                    )
                )
                stint_team = team_id
                stint_abbr = abbr
                stint_name = name
                stint_position = position_s
                stint_from = game_date
            else:
                stint_name = name
                stint_abbr = abbr or stint_abbr
                if position_s:
                    stint_position = position_s
        if stint_team is not None and stint_from is not None:
            rows.append(
                _stint_row(
                    season=season,
                    team_id=stint_team,
                    team_abbr=stint_abbr,
                    player_id=player_id,
                    player_name=stint_name,
                    position=stint_position,
                    from_date=stint_from,
                    to_date=None,
                    source="game_log",
                )
            )
    rows.sort(key=lambda item: (int(item["team_id"]), int(item["player_id"]), item["from_date"]))
    return rows


def merge_common_roster(
    stints: list[dict[str, object]],
    api_players: list[dict[str, object]],
    *,
    season: str,
    as_of: date,
) -> list[dict[str, object]]:
    """Merge a current CommonTeamRoster snapshot into log-derived stints.

    Only for the live/current season. Players who already have an open game-log
    stint on the API team keep that stint. A player whose open stint is on a
    different team is closed at ``as_of`` and opened on the API team (trade /
    signing before first box score). New players get an open common_roster stint.
    """
    if not api_players:
        return list(stints)
    # from_date must be < slate as_of so same-day projections see the player.
    api_from = as_of - timedelta(days=1)
    working = [dict(row) for row in stints]
    open_by_player: dict[int, dict[str, object]] = {}
    for row in working:
        if row["to_date"] is None:
            open_by_player[int(row["player_id"])] = row

    by_team: dict[int, list[dict[str, object]]] = defaultdict(list)
    for player in api_players:
        by_team[int(player["team_id"])].append(player)

    for team_id, players in by_team.items():
        for player in players:
            player_id = int(player["player_id"])
            name = str(player.get("player_name") or f"player:{player_id}")
            abbr = str(player.get("team_abbr") or "")
            position = player.get("position")
            position_s = None if position is None else str(position)
            jersey = player.get("jersey")
            jersey_s = None if jersey is None else str(jersey)
            open_stint = open_by_player.get(player_id)
            if open_stint is not None and int(open_stint["team_id"]) == team_id:
                if position_s and not open_stint.get("position"):
                    open_stint["position"] = position_s
                if jersey_s and not open_stint.get("jersey"):
                    open_stint["jersey"] = jersey_s
                continue
            if open_stint is not None and int(open_stint["team_id"]) != team_id:
                prior_from = open_stint["from_date"]
                if not isinstance(prior_from, date):
                    prior_from = date.fromisoformat(str(prior_from))
                if prior_from < as_of:
                    open_stint["to_date"] = as_of
                else:
                    # Same-day conflict: drop the log open stint in favor of API.
                    working.remove(open_stint)
                open_by_player.pop(player_id, None)
            new_row = _stint_row(
                season=season,
                team_id=team_id,
                team_abbr=abbr,
                player_id=player_id,
                player_name=name,
                position=position_s,
                from_date=api_from,
                to_date=None,
                source="common_roster",
                jersey=jersey_s,
                roster_status=None if player.get("roster_status") is None else str(player["roster_status"]),
            )
            working.append(new_row)
            open_by_player[player_id] = new_row
    working.sort(key=lambda item: (int(item["team_id"]), int(item["player_id"]), item["from_date"]))
    return working


def active_roster_player_ids(
    roster_rows: list[dict[str, object]],
    *,
    team_id: int,
    as_of: date,
) -> list[int]:
    """Players on ``team_id`` as of ``as_of`` (no future leakage)."""
    active: list[int] = []
    for row in roster_rows:
        if int(row["team_id"]) != team_id:
            continue
        from_date = row["from_date"]
        if not isinstance(from_date, date):
            from_date = date.fromisoformat(str(from_date))
        if not from_date < as_of:
            continue
        to_date = row.get("to_date")
        if to_date is not None:
            if not isinstance(to_date, date):
                to_date = date.fromisoformat(str(to_date))
            if not as_of < to_date:
                continue
        active.append(int(row["player_id"]))
    return active


def rebuild_team_rosters(
    settings: Settings,
    season: str,
    *,
    source: Any | None = None,
    refresh_common: bool | None = None,
    as_of: date | None = None,
    log=print,
) -> int:
    """Rewrite ``team_rosters`` for one season from stored logs (+ optional API).

    Historical seasons need no network. Pass ``refresh_common=True`` (or leave
    default for the current season) to merge CommonTeamRoster for players who
    have not appeared in a box score yet.
    """
    logs = read_rows(settings, "player_game_logs", season)
    stints = team_rosters_from_logs(season, logs)
    use_common = (
        refresh_common
        if refresh_common is not None
        else season == settings.current_season
    )
    if use_common and source is not None:
        team_ids = sorted(
            {
                int(row["team_id"])
                for row in logs
            }
            | {
                int(row["home_team_id"])
                for row in read_rows(settings, "schedule", season)
            }
            | {
                int(row["away_team_id"])
                for row in read_rows(settings, "schedule", season)
            }
        )
        if not team_ids:
            team_ids = list(_NBA_TEAM_IDS)
        api_players: list[dict[str, object]] = []
        abbr_by_team = _team_abbr_map(logs, settings, season)
        for team_id in team_ids:
            try:
                fetched = source.common_team_roster(team_id, season)
            except Exception as exc:
                log(f"CommonTeamRoster failed for {team_id} {season}: {exc}")
                continue
            for player in fetched:
                player = dict(player)
                player.setdefault("team_abbr", abbr_by_team.get(team_id, ""))
                api_players.append(player)
        merge_date = as_of or datetime.now(timezone.utc).date()
        stints = merge_common_roster(
            stints,
            api_players,
            season=season,
            as_of=merge_date,
        )
        log(f"Merged CommonTeamRoster into team_rosters for {season} ({len(api_players)} players).")
    store_rows(settings, "team_rosters", season, stints, allow_historical=True)
    log(f"Rewrote team_rosters for {season}: {len(stints)} stints.")
    return len(stints)


def prior_season_label(season: str) -> str | None:
    try:
        start = int(season.split("-", 1)[0])
    except (TypeError, ValueError):
        return None
    return f"{start - 1}-{str(start)[-2:]}"


def _stint_row(
    *,
    season: str,
    team_id: int,
    team_abbr: str,
    player_id: int,
    player_name: str,
    position: str | None,
    from_date: date | None,
    to_date: date | None,
    source: str,
    jersey: str | None = None,
    roster_status: str | None = None,
) -> dict[str, object]:
    if from_date is None:
        raise ValueError("from_date is required")
    return {
        "season": season,
        "team_id": team_id,
        "team_abbr": team_abbr,
        "player_id": player_id,
        "player_name": player_name,
        "position": position,
        "from_date": from_date,
        "to_date": to_date,
        "jersey": jersey,
        "roster_status": roster_status,
        "source": source,
    }


def _team_abbr_map(
    logs: list[dict[str, object]],
    settings: Settings,
    season: str,
) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for row in logs:
        mapping[int(row["team_id"])] = str(row["team_abbr"])
    for row in read_rows(settings, "schedule", season):
        mapping[int(row["home_team_id"])] = str(row["home_abbr"])
        mapping[int(row["away_team_id"])] = str(row["away_abbr"])
    return mapping


# Standard NBA franchise ids (stats.nba.com). Used when schedule/logs are empty.
_NBA_TEAM_IDS = tuple(range(1610612737, 1610612767))
