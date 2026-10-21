"""Turn schedule, box score, and possession events into schema rows.

This module does not download anything and does not touch DATA_DIR.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from nba_sim.schema import POSITIONS_5, ZONES

_MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
_ZONE_BY_SHOT = {
    "AtRim": "restricted_area",
    "ShortMidRange": "paint_non_ra",
    "LongMidRange": "midrange",
    "Arc3": "above_break_3",
    "UnknownDistance2pt": "midrange",
}


@dataclass(frozen=True)
class ScheduleGame:
    game_id: str
    game_date: date
    status: str
    home_team_id: int
    away_team_id: int
    home_abbr: str
    away_abbr: str
    home_pts: int | None
    away_pts: int | None
    season_type: str

    @property
    def is_final(self) -> bool:
        return self.status == "final"


@dataclass
class CourtEvent:
    kind: str
    team_id: int | None
    player_id: int | None
    lineup: dict[int, tuple[int, ...]] = field(default_factory=dict)
    made: bool = False
    shot_zone: str | None = None
    # Passer on assisted makes (from assistPersonId / player2_id). Never raw PBP.
    assist_player_id: int | None = None


@dataclass
class PossessionView:
    offense_team_id: int
    period: int
    events: list[CourtEvent]
    counts: bool = True


def parse_seasons(value: str) -> list[str]:
    """Accept 2024-25 or a start-year span such as 2015-2025."""
    text = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return [text]
    match = re.fullmatch(r"(\d{4})-(\d{4})", text)
    if match is None:
        raise ValueError(
            f"Could not read seasons {value!r}. Use 2024-25 or 2015-2025."
        )
    start, end = int(match.group(1)), int(match.group(2))
    if end < start:
        raise ValueError(f"Season span {value!r} ends before it starts.")
    return [f"{year}-{str(year + 1)[-2:]}" for year in range(start, end + 1)]


def parse_game_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if "T" in text:
        text = text.split("T", 1)[0]
    elif " " in text and "," not in text:
        text = text.split(" ", 1)[0]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text.title() if "," in text else text, fmt).date()
        except ValueError:
            continue
    month_match = re.fullmatch(r"([A-Za-z]{3}) (\d{1,2}), (\d{4})", text)
    if month_match and month_match.group(1).upper() in _MONTHS:
        return date(
            int(month_match.group(3)),
            _MONTHS[month_match.group(1).upper()],
            int(month_match.group(2)),
        )
    raise ValueError(f"Could not read game date {value!r}.")


def parse_minutes(value: object) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if text.startswith("PT"):
        body = text.removeprefix("PT").removesuffix("S").replace("M", ":")
        minutes, _, seconds = body.partition(":")
        return float(minutes or 0) + float(seconds or 0) / 60.0
    if ":" in text:
        minutes, seconds = text.split(":", 1)
        return float(minutes) + float(seconds) / 60.0
    return float(text)


def shot_zone(shot_type: str | None, loc_x: float | None, is_corner_3: bool) -> str | None:
    if is_corner_3 or shot_type == "Corner3":
        if loc_x is None:
            return "left_corner_3"
        return "left_corner_3" if float(loc_x) < 0 else "right_corner_3"
    if shot_type is None:
        return None
    return _ZONE_BY_SHOT.get(shot_type)


def games_from_team_log(records: list[dict[str, object]]) -> list[ScheduleGame]:
    """Build one schedule row per game from a team LeagueGameLog or LeagueGameFinder."""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        grouped[_game_id(record.get("GAME_ID"))].append(record)
    games: list[ScheduleGame] = []
    for game_id, rows in sorted(grouped.items()):
        season_type = season_type_from_game_id(game_id)
        if season_type is None:
            continue
        home, away = _home_away_from_team_log(rows)
        if home is None or away is None:
            continue
        home_pts = _optional_int(home.get("PTS"))
        away_pts = _optional_int(away.get("PTS"))
        final = home_pts is not None and away_pts is not None
        games.append(
            ScheduleGame(
                game_id=game_id,
                game_date=parse_game_date(home.get("GAME_DATE")),
                status="final" if final else "scheduled",
                home_team_id=int(home["TEAM_ID"]),
                away_team_id=int(away["TEAM_ID"]),
                home_abbr=str(home.get("TEAM_ABBREVIATION") or ""),
                away_abbr=str(away.get("TEAM_ABBREVIATION") or ""),
                home_pts=home_pts if final else None,
                away_pts=away_pts if final else None,
                season_type=season_type,
            )
        )
    return games


def _home_away_from_team_log(
    rows: list[dict[str, object]],
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    """Pair home/away team log rows. Neutral-site preseason sometimes labels both `@`."""
    home = next((row for row in rows if _matchup_is_home(row.get("MATCHUP"))), None)
    away = next((row for row in rows if _matchup_is_away(row.get("MATCHUP"))), None)
    if home is not None and away is not None and home is not away:
        return home, away
    if len(rows) != 2:
        return None, None
    homes = [row for row in rows if _matchup_is_home(row.get("MATCHUP"))]
    aways = [row for row in rows if _matchup_is_away(row.get("MATCHUP"))]
    if len(homes) == 1:
        home = homes[0]
        away = next(row for row in rows if row is not home)
        return home, away
    if len(aways) == 1:
        away = aways[0]
        home = next(row for row in rows if row is not away)
        return home, away
    # Both same polarity (common in overseas preseason). Stable fallback by team_id.
    ordered = sorted(rows, key=lambda row: int(row["TEAM_ID"]))
    return ordered[0], ordered[1]


def games_from_cdn_schedule(payload: dict[str, object], season: str) -> list[ScheduleGame]:
    """Build schedule rows from cdn.nba.com scheduleLeagueV2.json."""
    league = payload.get("leagueSchedule")
    if not isinstance(league, dict):
        raise ValueError("CDN schedule has no leagueSchedule object.")
    published = str(league.get("seasonYear") or "")
    if published and published != season:
        raise ValueError(f"CDN schedule is for {published}, not {season}.")
    games: list[ScheduleGame] = []
    dates = league.get("gameDates") or []
    if not isinstance(dates, list):
        raise ValueError("CDN schedule gameDates is not a list.")
    for bucket in dates:
        if not isinstance(bucket, dict):
            continue
        for item in bucket.get("games") or []:
            if not isinstance(item, dict):
                continue
            game_id = _game_id(item.get("gameId"))
            season_type = season_type_from_game_id(game_id)
            if season_type is None:
                continue
            home = item.get("homeTeam") if isinstance(item.get("homeTeam"), dict) else {}
            away = item.get("awayTeam") if isinstance(item.get("awayTeam"), dict) else {}
            status_code = int(item.get("gameStatus") or 0)
            final = status_code == 3 or str(item.get("gameStatusText") or "").lower() == "final"
            when = bucket.get("gameDate") or item.get("gameDateTimeUTC") or item.get("gameDateUTC")
            games.append(
                ScheduleGame(
                    game_id=game_id,
                    game_date=parse_game_date(when),
                    status="final" if final else "scheduled",
                    home_team_id=int(home["teamId"]),
                    away_team_id=int(away["teamId"]),
                    home_abbr=str(home.get("teamTricode") or ""),
                    away_abbr=str(away.get("teamTricode") or ""),
                    home_pts=_optional_int(home.get("score")) if final else None,
                    away_pts=_optional_int(away.get("score")) if final else None,
                    season_type=season_type,
                )
            )
    return games


def games_from_data_nba_schedule(payload: dict[str, object], season: str) -> list[ScheduleGame]:
    """Build schedule rows from the data.nba.com full-season file."""
    months = payload.get("lscd")
    if not isinstance(months, list):
        raise ValueError("data.nba.com schedule has no lscd list.")
    games: list[ScheduleGame] = []
    for month in months:
        if not isinstance(month, dict):
            continue
        block = month.get("mscd") if isinstance(month.get("mscd"), dict) else {}
        for item in block.get("g") or []:
            if not isinstance(item, dict):
                continue
            game_id = _game_id(item.get("gid"))
            season_type = season_type_from_game_id(game_id)
            if season_type is None:
                continue
            home = item.get("h") if isinstance(item.get("h"), dict) else {}
            away = item.get("v") if isinstance(item.get("v"), dict) else {}
            final = str(item.get("stt") or "").lower() == "final"
            games.append(
                ScheduleGame(
                    game_id=game_id,
                    game_date=parse_game_date(item.get("gdte")),
                    status="final" if final else "scheduled",
                    home_team_id=int(home["tid"]),
                    away_team_id=int(away["tid"]),
                    home_abbr=str(home.get("ta") or ""),
                    away_abbr=str(away.get("ta") or ""),
                    home_pts=_optional_int(home.get("s")) if final else None,
                    away_pts=_optional_int(away.get("s")) if final else None,
                    season_type=season_type,
                )
            )
    if not games:
        raise ValueError(f"data.nba.com schedule for {season} had no regular-season, playoff, or play-in games.")
    return games


def season_type_from_game_id(game_id: str) -> str | None:
    if len(game_id) < 3 or not game_id.startswith("00"):
        return None
    return {
        "1": "Preseason",
        "2": "Regular Season",
        "4": "Playoffs",
        "5": "PlayIn",
    }.get(game_id[2])


def schedule_row(season: str, game: ScheduleGame) -> dict[str, object]:
    return {
        "season": season,
        "game_id": game.game_id,
        "game_date": game.game_date,
        "home_team_id": game.home_team_id,
        "away_team_id": game.away_team_id,
        "home_abbr": game.home_abbr,
        "away_abbr": game.away_abbr,
        "status": game.status,
        "home_pts": game.home_pts,
        "away_pts": game.away_pts,
    }


def player_rows_from_box(
    season: str,
    game: ScheduleGame,
    players: list[dict[str, object]],
    team_points: dict[int, int],
) -> list[dict[str, object]]:
    rows = []
    for player in players:
        if str(player.get("played", "1")) == "0":
            continue
        minutes = parse_minutes(player.get("minutes"))
        if minutes <= 0 and str(player.get("played", "1")) != "1":
            continue
        if minutes <= 0 and player.get("played") is None:
            continue
        player_id = int(player["player_id"])
        team_id = int(player["team_id"])
        opponent_id = game.away_team_id if team_id == game.home_team_id else game.home_team_id
        opponent_abbr = game.away_abbr if team_id == game.home_team_id else game.home_abbr
        points_for = team_points.get(team_id)
        points_against = team_points.get(opponent_id)
        rows.append(
            {
                "season": season,
                "game_id": game.game_id,
                "game_date": game.game_date,
                "player_id": player_id,
                "player_name": str(player.get("name") or player.get("player_name") or player_id),
                "team_id": team_id,
                "team_abbr": str(player.get("team_abbreviation") or player.get("team_abbr") or ""),
                "opponent_team_id": opponent_id,
                "opponent_abbr": opponent_abbr,
                "home_away": "H" if team_id == game.home_team_id else "A",
                "win": bool(points_for is not None and points_against is not None and points_for > points_against),
                "started": str(player.get("starter", "0")) in {"1", "True", "true"} or player.get("starter") is True,
                "position": _text_or_none(player.get("position")),
                "minutes": minutes,
                "pts": _int(player.get("points", player.get("pts"))),
                "reb": _int(player.get("reboundsTotal", player.get("reb"))),
                "ast": _int(player.get("assists", player.get("ast"))),
                "fg3m": _int(player.get("threePointersMade", player.get("fg3m"))),
                "stl": _int(player.get("steals", player.get("stl"))),
                "blk": _int(player.get("blocks", player.get("blk"))),
                "tov": _int(player.get("turnovers", player.get("tov"))),
                "fgm": _int(player.get("fieldGoalsMade", player.get("fgm"))),
                "fga": _int(player.get("fieldGoalsAttempted", player.get("fga"))),
                "fg3a": _int(player.get("threePointersAttempted", player.get("fg3a"))),
                "ftm": _int(player.get("freeThrowsMade", player.get("ftm"))),
                "fta": _int(player.get("freeThrowsAttempted", player.get("fta"))),
                "oreb": _int(player.get("reboundsOffensive", player.get("oreb"))),
                "dreb": _int(player.get("reboundsDefensive", player.get("dreb"))),
                "plus_minus": _optional_int(player.get("plusMinusPoints", player.get("plus_minus"))),
            }
        )
    return rows


def player_rows_from_api(
    season: str,
    game: ScheduleGame,
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Map nba_api LeagueGameLog player rows for one game."""
    adapted = []
    for record in records:
        if str(record.get("GAME_ID")) != game.game_id:
            continue
        adapted.append(
            {
                "player_id": record["PLAYER_ID"],
                "name": record.get("PLAYER_NAME"),
                "team_id": record["TEAM_ID"],
                "team_abbreviation": record.get("TEAM_ABBREVIATION"),
                "played": "1",
                "starter": "0",
                "position": None,
                "minutes": record.get("MIN"),
                "points": record.get("PTS"),
                "reboundsTotal": record.get("REB"),
                "assists": record.get("AST"),
                "threePointersMade": record.get("FG3M"),
                "steals": record.get("STL"),
                "blocks": record.get("BLK"),
                "turnovers": record.get("TOV"),
                "fieldGoalsMade": record.get("FGM"),
                "fieldGoalsAttempted": record.get("FGA"),
                "threePointersAttempted": record.get("FG3A"),
                "freeThrowsMade": record.get("FTM"),
                "freeThrowsAttempted": record.get("FTA"),
                "reboundsOffensive": record.get("OREB"),
                "reboundsDefensive": record.get("DREB"),
                "plusMinusPoints": record.get("PLUS_MINUS"),
            }
        )
    team_points = {
        game.home_team_id: game.home_pts or 0,
        game.away_team_id: game.away_pts or 0,
    }
    return player_rows_from_box(season, game, adapted, team_points)


def team_rows(
    season: str,
    game: ScheduleGame,
    team_points: dict[int, int],
    pace_by_team: dict[int, float],
    overtime_periods: int,
) -> list[dict[str, object]]:
    rows = []
    sides = (
        (game.home_team_id, game.home_abbr, "H", game.away_team_id, game.away_abbr),
        (game.away_team_id, game.away_abbr, "A", game.home_team_id, game.home_abbr),
    )
    for team_id, abbr, home_away, opponent_id, opponent_abbr in sides:
        points = team_points.get(team_id, game.home_pts if home_away == "H" else game.away_pts)
        opponent_points = team_points.get(opponent_id, game.away_pts if home_away == "H" else game.home_pts)
        if points is None or opponent_points is None:
            continue
        pace = pace_by_team.get(team_id)
        rows.append(
            {
                "season": season,
                "game_id": game.game_id,
                "game_date": game.game_date,
                "team_id": team_id,
                "team_abbr": abbr,
                "opponent_team_id": opponent_id,
                "opponent_abbr": opponent_abbr,
                "home_away": home_away,
                "win": points > opponent_points,
                "pts": int(points),
                "opp_pts": int(opponent_points),
                "pace": None if pace is None else float(pace),
                "overtime_periods": overtime_periods,
            }
        )
    return rows


def rates_from_possessions(
    season: str,
    game: ScheduleGame,
    players: list[dict[str, object]],
    possessions: list[PossessionView],
) -> tuple[list[dict[str, object]], dict[int, float], int]:
    """Return rate rows, offensive possession counts by team, and overtime periods."""
    catalog = {int(player["player_id"]): player for player in players}
    offense_poss: dict[int, float] = defaultdict(float)
    defense_poss: dict[int, float] = defaultdict(float)
    used: dict[int, float] = defaultdict(float)
    oreb_chances: dict[int, float] = defaultdict(float)
    dreb_chances: dict[int, float] = defaultdict(float)
    ast_chances: dict[int, float] = defaultdict(float)
    zone_fga: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    zone_fgm: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    fta: dict[int, float] = defaultdict(float)
    ftm: dict[int, float] = defaultdict(float)
    team_offense: dict[int, float] = defaultdict(float)
    player_team: dict[int, int] = {int(player["player_id"]): int(player["team_id"]) for player in players}
    max_period = 0

    for possession in possessions:
        max_period = max(max_period, possession.period)
        if not possession.counts:
            continue
        lineup = _possession_lineup(possession)
        offense_id = possession.offense_team_id
        offense_players = lineup.get(offense_id, ())
        if not offense_players:
            continue
        defense_id = next((team_id for team_id in lineup if team_id != offense_id), None)
        team_offense[offense_id] += 1
        for player_id in offense_players:
            offense_poss[player_id] += 1
            player_team.setdefault(player_id, offense_id)
        if defense_id is not None:
            for player_id in lineup.get(defense_id, ()):
                defense_poss[player_id] += 1
                player_team.setdefault(player_id, defense_id)
        user = _possession_user(possession, offense_id)
        if user is not None:
            used[user] += 1
        for event in possession.events:
            if event.kind == "free_throw" and event.player_id:
                fta[event.player_id] += 1
                if event.made:
                    ftm[event.player_id] += 1
            if event.kind != "field_goal" or event.player_id is None or event.shot_zone is None:
                continue
            zone_fga[event.player_id][event.shot_zone] += 1
            if event.made:
                zone_fgm[event.player_id][event.shot_zone] += 1
                for teammate in event.lineup.get(event.team_id or -1, ()):
                    if teammate != event.player_id:
                        ast_chances[teammate] += 1
            elif event.lineup:
                shooting_team = event.team_id
                for player_id in event.lineup.get(shooting_team or -1, ()):
                    oreb_chances[player_id] += 1
                for team_id, on_court in event.lineup.items():
                    if team_id == shooting_team:
                        continue
                    for player_id in on_court:
                        dreb_chances[player_id] += 1

    rows = []
    player_ids = set(catalog) | set(offense_poss) | set(defense_poss)
    for player_id in sorted(player_ids):
        info = catalog.get(player_id, {})
        team_id = player_team.get(player_id)
        if team_id is None:
            continue
        offensive = offense_poss[player_id]
        defensive = defense_poss[player_id]
        minutes = parse_minutes(info.get("minutes")) if info else 0.0
        if offensive + defensive <= 0 and minutes <= 0:
            continue
        row: dict[str, object] = {
            "season": season,
            "game_id": game.game_id,
            "game_date": game.game_date,
            "player_id": player_id,
            "team_id": team_id,
            "minutes": minutes,
            "possessions": offensive + defensive,
            "usage": (used[player_id] / offensive) if offensive else 0.0,
            "oreb_chances": oreb_chances[player_id],
            "dreb_chances": dreb_chances[player_id],
            "ast_chances": ast_chances[player_id],
            "fta": fta[player_id],
            "ftm": ftm[player_id],
        }
        for zone in ZONES:
            row[f"{zone}_fga"] = zone_fga[player_id][zone]
            row[f"{zone}_fgm"] = zone_fgm[player_id][zone]
        rows.append(row)
    overtime = max(0, max_period - 4)
    return rows, dict(team_offense), overtime


def player_season_aggregates(
    log_rows: list[dict[str, object]],
    rate_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    logs: dict[tuple[int, int], list[dict[str, object]]] = defaultdict(list)
    for row in log_rows:
        logs[(int(row["player_id"]), int(row["team_id"]))].append(row)
    rates: dict[tuple[int, int], list[dict[str, object]]] = defaultdict(list)
    for row in rate_rows:
        rates[(int(row["player_id"]), int(row["team_id"]))].append(row)
    aggregates = []
    for key in sorted(set(logs) | set(rates)):
        player_logs = logs.get(key, [])
        player_rates = rates.get(key, [])
        if not player_logs and not player_rates:
            continue
        sample = player_logs[0] if player_logs else player_rates[0]
        possessions = sum(float(row["possessions"]) for row in player_rates)
        weighted_usage = sum(float(row["usage"]) * float(row["possessions"]) for row in player_rates)
        position = next((row.get("position") for row in player_logs if row.get("position")), None)
        name = next((str(row["player_name"]) for row in player_logs if row.get("player_name")), str(key[0]))
        row = {
            "season": sample["season"],
            "player_id": key[0],
            "team_id": key[1],
            "player_name": name,
            "position": position,
            "games": len(player_logs) or len({row["game_id"] for row in player_rates}),
            "minutes": sum(float(item["minutes"]) for item in player_logs) if player_logs else sum(float(item["minutes"]) for item in player_rates),
            "possessions": possessions,
            "usage": (weighted_usage / possessions) if possessions else 0.0,
            "oreb_chances": sum(float(item["oreb_chances"]) for item in player_rates),
            "dreb_chances": sum(float(item["dreb_chances"]) for item in player_rates),
            "ast_chances": sum(float(item["ast_chances"]) for item in player_rates),
            "pts": sum(_int(item.get("pts")) for item in player_logs),
            "reb": sum(_int(item.get("reb")) for item in player_logs),
            "ast": sum(_int(item.get("ast")) for item in player_logs),
            "fg3m": sum(_int(item.get("fg3m")) for item in player_logs),
            "stl": sum(_int(item.get("stl")) for item in player_logs),
            "blk": sum(_int(item.get("blk")) for item in player_logs),
            "tov": sum(_int(item.get("tov")) for item in player_logs),
            "fta": sum(float(item["fta"]) for item in player_rates),
            "ftm": sum(float(item["ftm"]) for item in player_rates),
        }
        for zone in ZONES:
            row[f"{zone}_fga"] = sum(float(item[f"{zone}_fga"]) for item in player_rates)
            row[f"{zone}_fgm"] = sum(float(item[f"{zone}_fgm"]) for item in player_rates)
        aggregates.append(row)
    return aggregates


def team_season_aggregates(team_rows_in: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in team_rows_in:
        grouped[int(row["team_id"])].append(row)
    aggregates = []
    for team_id in sorted(grouped):
        games = grouped[team_id]
        paces = [float(row["pace"]) for row in games if row.get("pace") is not None]
        opponent_paces = []
        for row in games:
            match = next(
                (
                    other
                    for other in team_rows_in
                    if other["game_id"] == row["game_id"] and int(other["team_id"]) != team_id
                ),
                None,
            )
            if match is not None and match.get("pace") is not None:
                opponent_paces.append(float(match["pace"]))
        aggregates.append(
            {
                "season": games[0]["season"],
                "team_id": team_id,
                "team_abbr": games[-1]["team_abbr"],
                "games": len(games),
                "pace": (sum(paces) / len(paces)) if paces else 0.0,
                "possessions_for": sum(paces),
                "possessions_against": sum(opponent_paces),
                "points_for": sum(_int(row["pts"]) for row in games),
                "points_against": sum(_int(row["opp_pts"]) for row in games),
            }
        )
    return aggregates


def team_zone_defense(
    season: str,
    log_rows: list[dict[str, object]],
    rate_rows: list[dict[str, object]],
    team_rows_in: list[dict[str, object]],
) -> list[dict[str, object]]:
    opponent = {
        (str(row["game_id"]), int(row["player_id"])): int(row["opponent_team_id"])
        for row in log_rows
    }
    allowed_fga: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    allowed_fgm: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    teams = {int(row["team_id"]) for row in team_rows_in}
    for row in rate_rows:
        defender = opponent.get((str(row["game_id"]), int(row["player_id"])))
        if defender is None:
            continue
        teams.add(defender)
        for zone in ZONES:
            allowed_fga[defender][zone] += float(row[f"{zone}_fga"])
            allowed_fgm[defender][zone] += float(row[f"{zone}_fgm"])
    defensive_possessions: dict[int, float] = defaultdict(float)
    for row in team_rows_in:
        if row.get("pace") is None:
            continue
        opponent_row = next(
            (
                other
                for other in team_rows_in
                if other["game_id"] == row["game_id"] and int(other["team_id"]) != int(row["team_id"])
            ),
            None,
        )
        if opponent_row is not None and opponent_row.get("pace") is not None:
            defensive_possessions[int(row["team_id"])] += float(opponent_row["pace"])
    rows = []
    for team_id in sorted(teams):
        for zone in ZONES:
            rows.append(
                {
                    "season": season,
                    "team_id": team_id,
                    "zone": zone,
                    "fga": allowed_fga[team_id][zone],
                    "fgm": allowed_fgm[team_id][zone],
                    "possessions": defensive_possessions[team_id],
                }
            )
    return rows


def team_position_defense(
    season: str,
    log_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Stats allowed to opposing PG/SG/SF/PF/C, derived from player game logs."""
    from projections.rates import five_position

    totals: dict[tuple[int, str], dict[str, float]] = defaultdict(
        lambda: {
            "player_games": 0.0,
            "minutes": 0.0,
            "pts": 0.0,
            "reb": 0.0,
            "ast": 0.0,
            "fg3m": 0.0,
            "stl": 0.0,
            "blk": 0.0,
            "tov": 0.0,
        }
    )
    teams: set[int] = set()
    for row in log_rows:
        defender = int(row["opponent_team_id"])
        teams.add(defender)
        position = five_position(
            None if row.get("position") is None else str(row.get("position")),
            reb=float(row.get("reb") or 0),
            ast=float(row.get("ast") or 0),
            minutes=float(row.get("minutes") or 0),
        )
        key = (defender, position)
        bucket = totals[key]
        bucket["player_games"] += 1.0
        bucket["minutes"] += float(row.get("minutes") or 0)
        bucket["pts"] += float(row.get("pts") or 0)
        bucket["reb"] += float(row.get("reb") or 0)
        bucket["ast"] += float(row.get("ast") or 0)
        bucket["fg3m"] += float(row.get("fg3m") or 0)
        bucket["stl"] += float(row.get("stl") or 0)
        bucket["blk"] += float(row.get("blk") or 0)
        bucket["tov"] += float(row.get("tov") or 0)
    rows = []
    for team_id in sorted(teams):
        for position in POSITIONS_5:
            bucket = totals[(team_id, position)]
            rows.append(
                {
                    "season": season,
                    "team_id": team_id,
                    "position": position,
                    "player_games": int(bucket["player_games"]),
                    "minutes": bucket["minutes"],
                    "pts": bucket["pts"],
                    "reb": bucket["reb"],
                    "ast": bucket["ast"],
                    "fg3m": bucket["fg3m"],
                    "stl": bucket["stl"],
                    "blk": bucket["blk"],
                    "tov": bucket["tov"],
                }
            )
    return rows


def _possession_lineup(possession: PossessionView) -> dict[int, tuple[int, ...]]:
    for event in reversed(possession.events):
        if possession.offense_team_id in event.lineup:
            return event.lineup
    for event in possession.events:
        if event.lineup:
            return event.lineup
    return {}


def _possession_user(possession: PossessionView, offense_team_id: int) -> int | None:
    chosen = None
    for event in possession.events:
        if event.team_id != offense_team_id or event.player_id is None:
            continue
        if event.kind in {"field_goal", "turnover", "free_throw"}:
            chosen = event.player_id
    return chosen


def _int(value: object) -> int:
    if value is None or value == "":
        return 0
    return int(round(float(value)))


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(round(float(value)))


def _game_id(value: object) -> str:
    text = str(value or "").strip()
    if text.isdigit():
        return text.zfill(10)
    return text


def _matchup_is_home(value: object) -> bool:
    text = str(value or "")
    return " vs." in text or " vs " in text


def _matchup_is_away(value: object) -> bool:
    return " @ " in str(value or "")


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
