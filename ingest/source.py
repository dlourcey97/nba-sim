"""Download schedule, box scores, and possessions.

Raw responses stay in memory. Historical seasons use stats.nba.com first:
LeagueGameLog for the schedule, and BoxScoreTraditional for each final game.
If that host does not answer, the season file on data.nba.com supplies the
schedule and the live box score supplies player lines. The current season
uses the cdn.nba.com schedule when that file matches the requested season.

Historical possessions come from stats.nba.com PlayByPlayV3. The live feed
is the source for the current season and the fallback when PlayByPlayV3
does not answer. A body that is not JSON is logged once and not retried.
"""

from __future__ import annotations

import json
import time

import requests
from nba_api.stats.library.http import STATS_HEADERS

from ingest.pbp import possessions_to_views, views_from_playbyplay_v3

from ingest.parse import (
    ScheduleGame,
    games_from_cdn_schedule,
    games_from_data_nba_schedule,
    games_from_team_log,
)

_CDN_SCHEDULE = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
_SEASON_TYPES = ("Regular Season", "Playoffs", "PlayIn")


class SourceUnavailable(Exception):
    """A feed did not have this game. Another feed may."""


class NonJsonResponse(Exception):
    """HTML, an empty body, or an error page. Callers must not retry it."""


class PossessionsMissing(Exception):
    """Play-by-play was unusable. The box score can still be stored."""


class NbaSource:
    def __init__(
        self,
        *,
        delay_seconds: float,
        max_retries: int,
        backoff_seconds: float,
        timeout_seconds: float,
        log,
        current_season: str | None = None,
    ) -> None:
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.timeout_seconds = timeout_seconds
        self.log = log
        self.current_season = current_season
        self._last_request = 0.0
        self._schedule_cache: dict[tuple[str, str], list[ScheduleGame]] = {}
        self._data_nba_seasons: set[str] = set()
        self._api_players: dict[tuple[str, str], dict[str, list[dict]]] = {}
        self._stats_nba_ok: bool | None = None

    def stats_nba_ok(self) -> bool:
        """False only after a stats.nba.com call has already failed this run."""
        return self._stats_nba_ok is not False

    def clear_schedule_cache(self) -> None:
        self._schedule_cache.clear()
        self._data_nba_seasons.clear()

    def schedule(self, season: str, season_type: str) -> list[ScheduleGame]:
        key = (season, season_type)
        if key not in self._schedule_cache:
            self._load_schedule(season, season_type)
        return list(self._schedule_cache.get(key, []))

    def api_player_rows(self, season: str, season_type: str, game_id: str) -> list[dict] | None:
        """Player log rows from nba_api, or None when that host is unavailable."""
        if not self.stats_nba_ok():
            return None
        key = (season, season_type)
        if key not in self._api_players:
            self._api_players[key] = self._league_game_log(season, season_type)
        return self._api_players[key].get(game_id)

    def stats_boxscore(self, game_id: str) -> tuple[list[dict], dict[int, int]]:
        """Player lines from stats.nba.com. Raises SourceUnavailable when that host cannot serve the game."""
        if self._stats_nba_ok is False:
            raise SourceUnavailable(f"stats.nba.com skipped for {game_id}")
        rows = self._stats_rows(
            "boxscoretraditionalv2",
            _boxscore_params(game_id),
            "PlayerStats",
            label=f"BoxScoreTraditional {game_id}",
        )
        if not rows:
            raise SourceUnavailable(f"BoxScoreTraditional {game_id} had no players")
        return _players_from_traditional(rows)

    def common_team_roster(self, team_id: int, season: str) -> list[dict]:
        """Current CommonTeamRoster snapshot for one team.

        Historical seasons are not reliable: the endpoint returns the current
        roster for the requested season label, not a dated archive. Prefer
        game-log stints for as-of history; use this for the live season so
        signed players appear before their first box score.
        """
        if self._stats_nba_ok is False:
            raise SourceUnavailable(f"stats.nba.com skipped for CommonTeamRoster {team_id}")
        rows = self._stats_rows(
            "commonteamroster",
            _common_team_roster_params(team_id, season),
            "CommonTeamRoster",
            label=f"CommonTeamRoster {team_id} {season}",
        )
        players = []
        for row in rows:
            player_id = row.get("PLAYER_ID")
            if player_id is None:
                continue
            jersey = row.get("NUM")
            players.append(
                {
                    "team_id": int(row.get("TeamID") or team_id),
                    "player_id": int(player_id),
                    "player_name": row.get("PLAYER") or f"player:{player_id}",
                    "position": row.get("POSITION"),
                    "jersey": None if jersey is None or jersey == "" else str(jersey),
                    "roster_status": None,
                }
            )
        return players

    def live_boxscore(self, game_id: str) -> tuple[list[dict], dict[int, int]]:
        payload = self._request_json(
            f"https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/NBA/liveData/boxscore/boxscore_{game_id}.json",
            label=f"boxscore {game_id}",
        )
        return _players_and_points(payload)

    def possession_views(self, game_id: str, players: list[dict], *, historical: bool):
        """Possession views for one game.

        Historical seasons read PlayByPlayV3 first. The current season reads
        the live feed first. The other feed is a single fallback attempt.
        """
        order = ("playbyplayv3", "live") if historical else ("live", "playbyplayv3")
        problems: list[str] = []
        for kind in order:
            try:
                views = self._possession_views_from(kind, game_id, players)
            except NonJsonResponse as exc:
                problems.append(str(exc))
                continue
            except SourceUnavailable as exc:
                problems.append(str(exc))
                continue
            except Exception as exc:
                if _is_non_json(exc):
                    problems.append(f"{kind} {game_id} returned a non-JSON response")
                else:
                    problems.append(f"{kind} {game_id} failed: {exc}")
                continue
            if views:
                return views
            problems.append(f"{kind} {game_id} had no possessions")
        self.log(f"{game_id} possessions missing: {'; '.join(problems)}")
        raise PossessionsMissing(game_id)

    def _possession_views_from(self, kind: str, game_id: str, players: list[dict]):
        if kind == "playbyplayv3":
            return views_from_playbyplay_v3(self._playbyplay_v3(game_id), players)
        return possessions_to_views(self._pbpstats_possessions(game_id, "live"))

    def _load_schedule(self, season: str, season_type: str) -> None:
        if season == self.current_season:
            try:
                self._remember_schedule(season, self._cdn_schedule(season))
                return
            except SourceUnavailable as exc:
                self.log(f"CDN schedule unavailable for {season}: {exc}. Using stats.nba.com.")
        if self._stats_nba_ok is not False:
            try:
                records = self._team_schedule_rows(season, season_type)
            except Exception as exc:
                self._stats_nba_ok = False
                self.log(f"stats.nba.com schedule failed ({exc}). Using data.nba.com for {season}.")
            else:
                self._schedule_cache[(season, season_type)] = games_from_team_log(records)
                return
        if season not in self._data_nba_seasons:
            self._remember_schedule(season, self._data_nba_schedule(season))
            self._data_nba_seasons.add(season)
        if (season, season_type) not in self._schedule_cache:
            self._schedule_cache[(season, season_type)] = []

    def _data_nba_schedule(self, season: str) -> list[ScheduleGame]:
        year = season.split("-", 1)[0]
        url = (
            "https://data.nba.com/data/10s/v2015/json/mobile_teams/nba/"
            f"{year}/league/00_full_schedule.json"
        )
        payload = self._request_json(url, label=f"data.nba.com schedule {season}", headers=_BROWSER_HEADERS)
        try:
            return games_from_data_nba_schedule(payload, season)
        except ValueError as exc:
            raise SourceUnavailable(str(exc)) from exc

    def _remember_schedule(self, season: str, games: list[ScheduleGame]) -> None:
        for season_type in _SEASON_TYPES:
            self._schedule_cache[(season, season_type)] = [
                game for game in games if game.season_type == season_type
            ]

    def _cdn_schedule(self, season: str) -> list[ScheduleGame]:
        payload = self._request_json(_CDN_SCHEDULE, label=f"cdn schedule {season}", headers=_BROWSER_HEADERS)
        try:
            return games_from_cdn_schedule(payload, season)
        except ValueError as exc:
            raise SourceUnavailable(str(exc)) from exc

    def _team_schedule_rows(self, season: str, season_type: str) -> list[dict]:
        """Team rows for one season type. LeagueGameFinder runs if LeagueGameLog fails."""
        try:
            return self._stats_rows(
                "leaguegamelog",
                _league_game_log_params(season, season_type, player_or_team="T"),
                "LeagueGameLog",
                label=f"LeagueGameLog {season} {season_type}",
            )
        except requests.Timeout:
            raise
        except Exception as exc:
            self.log(f"LeagueGameLog failed for {season} {season_type}: {exc}. Trying LeagueGameFinder.")
            return self._stats_rows(
                "leaguegamefinder",
                _league_game_finder_params(season, season_type),
                "LeagueGameFinderResults",
                label=f"LeagueGameFinder {season} {season_type}",
            )

    def _league_game_log(self, season: str, season_type: str) -> dict[str, list[dict]]:
        try:
            records = self._stats_rows(
                "leaguegamelog",
                _league_game_log_params(season, season_type, player_or_team="P"),
                "LeagueGameLog",
                label=f"LeagueGameLog players {season} {season_type}",
            )
        except Exception:
            self._stats_nba_ok = False
            raise
        grouped: dict[str, list[dict]] = {}
        for record in records:
            grouped.setdefault(str(record["GAME_ID"]), []).append(record)
        return grouped

    def _playbyplay_v3(self, game_id: str) -> list[dict]:
        def _load() -> list[dict]:
            self._pause()
            response = requests.get(
                "https://stats.nba.com/stats/playbyplayv3",
                params=_playbyplay_params(game_id),
                headers=dict(STATS_HEADERS),
                timeout=self.timeout_seconds,
            )
            if response.status_code in {403, 404}:
                raise SourceUnavailable(f"PlayByPlayV3 {game_id} returned {response.status_code}")
            response.raise_for_status()
            payload = _load_json(response, f"PlayByPlayV3 {game_id}")
            actions = (payload.get("game") or {}).get("actions") if isinstance(payload.get("game"), dict) else None
            if not isinstance(actions, list) or not actions:
                raise SourceUnavailable(f"PlayByPlayV3 {game_id} had no actions")
            return actions

        return self._retry(f"PlayByPlayV3 {game_id}", _load)

    def _pbpstats_possessions(self, game_id: str, provider: str):
        from pbpstats.client import Client

        self._pause()
        client = Client({"Possessions": {"source": "web", "data_provider": provider}})
        try:
            return list(client.Game(game_id).possessions.items)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in {403, 404}:
                raise SourceUnavailable(str(exc)) from exc
            raise
        except json.JSONDecodeError as exc:
            raise NonJsonResponse(f"live feed {game_id} returned a non-JSON response") from exc

    def _request_json(self, url: str, *, label: str, headers: dict[str, str] | None = None) -> dict:
        def _load():
            self._pause()
            response = requests.get(
                url,
                timeout=self.timeout_seconds,
                headers=headers or {"User-Agent": "nba-sim"},
            )
            if response.status_code in {403, 404}:
                raise SourceUnavailable(f"{label} returned {response.status_code}")
            response.raise_for_status()
            return _load_json(response, label)

        return self._retry(label, _load)

    def _stats_rows(self, endpoint: str, params: list[tuple[str, str]], result_name: str, *, label: str) -> list[dict]:
        """GET a stats.nba.com endpoint. Query order is preserved (LeagueID first)."""

        def _load() -> list[dict]:
            self._pause()
            response = requests.get(
                f"https://stats.nba.com/stats/{endpoint}",
                params=params,
                headers=dict(STATS_HEADERS),
                timeout=self.timeout_seconds,
            )
            if response.status_code in {403, 404}:
                raise SourceUnavailable(f"{label} returned {response.status_code}")
            response.raise_for_status()
            payload = _load_json(response, label)
            return _result_rows(payload, result_name)

        rows = self._retry(label, _load)
        self._stats_nba_ok = True
        self.log(f"stats.nba.com {label} returned {len(rows)} rows.")
        return rows

    def _pause(self) -> None:
        if self.delay_seconds <= 0:
            return
        elapsed = time.monotonic() - self._last_request
        if self._last_request and elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)
        self._last_request = time.monotonic()

    def _retry(self, label: str, fn):
        delay = self.backoff_seconds
        last: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return fn()
            except (SourceUnavailable, NonJsonResponse):
                raise
            except requests.Timeout:
                self.log(f"{label} timed out after {self.timeout_seconds:g}s with no response.")
                raise
            except Exception as exc:
                if _is_non_json(exc):
                    raise NonJsonResponse(f"{label} returned a non-JSON response") from exc
                last = exc
                self.log(f"{label} attempt {attempt} failed: {exc}")
                if attempt == self.max_retries:
                    break
                time.sleep(delay)
                delay *= 2
        assert last is not None
        raise last


_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "sec-ch-ua": '"Google Chrome";v="120", "Chromium";v="120", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


def _league_game_log_params(season: str, season_type: str, *, player_or_team: str) -> list[tuple[str, str]]:
    # LeagueID stays first. Alphabetical order has been answered with an HTML block page.
    return [
        ("LeagueID", "00"),
        ("Season", season),
        ("SeasonType", season_type),
        ("PlayerOrTeam", player_or_team),
        ("DateFrom", ""),
        ("DateTo", ""),
        ("Counter", "0"),
        ("Direction", "ASC"),
        ("Sorter", "DATE"),
    ]


def _playbyplay_params(game_id: str) -> list[tuple[str, str]]:
    return [("GameID", game_id), ("StartPeriod", "0"), ("EndPeriod", "0")]


def _load_json(response: requests.Response, label: str) -> dict:
    """Parse a body that must be a JSON object. HTML, empty, and error pages raise."""
    stripped = response.text.lstrip("\ufeff \t\r\n")
    if not stripped or stripped[0] not in "{[":
        raise NonJsonResponse(f"{label} returned a non-JSON response")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise NonJsonResponse(f"{label} returned a non-JSON response") from exc
    if not isinstance(payload, dict):
        raise NonJsonResponse(f"{label} returned a non-JSON response")
    message = payload.get("Message")
    if message and "game" not in payload and "resultSets" not in payload and "resultSet" not in payload:
        raise NonJsonResponse(f"{label} returned an error page")
    return payload


def _is_non_json(exc: BaseException) -> bool:
    if isinstance(exc, json.JSONDecodeError):
        return True
    text = str(exc)
    return "Expecting value" in text or "JSONDecodeError" in text


def _boxscore_params(game_id: str) -> list[tuple[str, str]]:
    return [
        ("GameID", game_id),
        ("StartPeriod", "0"),
        ("EndPeriod", "0"),
        ("StartRange", "0"),
        ("EndRange", "0"),
        ("RangeType", "0"),
    ]


def _common_team_roster_params(team_id: int, season: str) -> list[tuple[str, str]]:
    return [
        ("LeagueID", "00"),
        ("Season", season),
        ("TeamID", str(team_id)),
    ]


def _league_game_finder_params(season: str, season_type: str) -> list[tuple[str, str]]:
    return [
        ("LeagueID", "00"),
        ("Season", season),
        ("SeasonType", season_type),
        ("PlayerOrTeam", "T"),
        ("DateFrom", ""),
        ("DateTo", ""),
    ]


def _result_rows(payload: dict, result_name: str) -> list[dict]:
    sets = payload.get("resultSets")
    if sets is None and isinstance(payload.get("resultSet"), dict):
        sets = [payload["resultSet"]]
    if not isinstance(sets, list):
        raise requests.RequestException("stats.nba.com response has no resultSets")
    for item in sets:
        if item.get("name") != result_name:
            continue
        headers = item.get("headers") or []
        return [dict(zip(headers, row)) for row in item.get("rowSet") or []]
    raise requests.RequestException(f"stats.nba.com response has no {result_name}")


def _players_from_traditional(rows: list[dict]) -> tuple[list[dict], dict[int, int]]:
    players: list[dict] = []
    points: dict[int, int] = {}
    for record in rows:
        team_id = int(record["TEAM_ID"])
        points[team_id] = points.get(team_id, 0) + int(record.get("PTS") or 0)
        start = str(record.get("START_POSITION") or "").strip()
        minutes = record.get("MIN")
        players.append(
            {
                "player_id": int(record["PLAYER_ID"]),
                "name": record.get("PLAYER_NAME"),
                "team_id": team_id,
                "team_abbreviation": record.get("TEAM_ABBREVIATION"),
                "played": "0" if minutes in (None, "", "0", "0:00") else "1",
                "starter": "1" if start else "0",
                "position": start or None,
                "minutes": minutes,
                "points": record.get("PTS"),
                "reboundsTotal": record.get("REB"),
                "assists": record.get("AST"),
                "threePointersMade": record.get("FG3M"),
                "steals": record.get("STL"),
                "blocks": record.get("BLK"),
                "turnovers": record.get("TO"),
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
    _limit_starters(players)
    return players, points


def _limit_starters(players: list[dict]) -> None:
    """Older box scores put a position on every player. Only the first five count as starters."""
    by_team: dict[int, list[int]] = {}
    for index, player in enumerate(players):
        by_team.setdefault(int(player["team_id"]), []).append(index)
    for indexes in by_team.values():
        flagged = [index for index in indexes if players[index]["starter"] == "1"]
        if len(flagged) <= 5:
            continue
        keep = set(flagged[:5])
        for index in flagged:
            if index not in keep:
                players[index]["starter"] = "0"


def _players_and_points(payload: dict) -> tuple[list[dict], dict[int, int]]:
    game = payload["game"]
    players: list[dict] = []
    points: dict[int, int] = {}
    for team in game["homeTeam"], game["awayTeam"]:
        team_id = int(team["teamId"])
        points[team_id] = int(team["score"])
        abbreviation = team.get("teamTricode")
        for person in team.get("players", []):
            stats = person.get("statistics") or {}
            players.append(
                {
                    "player_id": int(person["personId"]),
                    "name": f"{person.get('firstName', '')} {person.get('familyName', '')}".strip(),
                    "team_id": team_id,
                    "team_abbreviation": abbreviation,
                    "played": person.get("played"),
                    "starter": person.get("starter"),
                    "position": person.get("position"),
                    "minutes": stats.get("minutes"),
                    "points": stats.get("points"),
                    "reboundsTotal": stats.get("reboundsTotal"),
                    "assists": stats.get("assists"),
                    "threePointersMade": stats.get("threePointersMade"),
                    "steals": stats.get("steals"),
                    "blocks": stats.get("blocks"),
                    "turnovers": stats.get("turnovers"),
                    "fieldGoalsMade": stats.get("fieldGoalsMade"),
                    "fieldGoalsAttempted": stats.get("fieldGoalsAttempted"),
                    "threePointersAttempted": stats.get("threePointersAttempted"),
                    "freeThrowsMade": stats.get("freeThrowsMade"),
                    "freeThrowsAttempted": stats.get("freeThrowsAttempted"),
                    "reboundsOffensive": stats.get("reboundsOffensive"),
                    "reboundsDefensive": stats.get("reboundsDefensive"),
                    "plusMinusPoints": stats.get("plusMinusPoints"),
                }
            )
    return players, points

