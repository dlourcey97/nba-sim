"""Download schedule, box scores, and possessions.

Raw responses stay in memory. pbpstats is not given a directory, so it does
not write response files. nba_api is tried first for season logs. When
stats.nba.com does not answer, live box scores from the NBA media feed are used.
"""

from __future__ import annotations

import time
from datetime import date

import requests

from ingest.parse import ScheduleGame, parse_game_date

_STATS_PROBE = (
    "https://stats.nba.com/stats/scoreboardv2"
    "?GameDate=10/22/2024&LeagueID=00&DayOffset=0"
)
_STATS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
}


class SourceUnavailable(Exception):
    """A feed did not have this game. Another feed may."""


class NbaSource:
    def __init__(
        self,
        *,
        delay_seconds: float,
        max_retries: int,
        backoff_seconds: float,
        timeout_seconds: float,
        log,
    ) -> None:
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.timeout_seconds = timeout_seconds
        self.log = log
        self._last_request = 0.0
        self._schedule_cache: dict[str, list[ScheduleGame]] = {}
        self._api_players: dict[tuple[str, str], dict[str, list[dict]]] = {}
        self._stats_nba_ok: bool | None = None

    def stats_nba_ok(self) -> bool:
        if self._stats_nba_ok is None:
            self._stats_nba_ok = self._probe_stats_nba()
            state = "reachable" if self._stats_nba_ok else "not reachable; using live NBA feeds"
            self.log(f"stats.nba.com is {state}.")
        return self._stats_nba_ok

    def clear_schedule_cache(self) -> None:
        self._schedule_cache.clear()

    def schedule(self, season: str, season_type: str) -> list[ScheduleGame]:
        if season not in self._schedule_cache:
            self._schedule_cache[season] = self._load_schedule(season)
        return [game for game in self._schedule_cache[season] if game.season_type == season_type]

    def api_player_rows(self, season: str, season_type: str, game_id: str) -> list[dict] | None:
        """Player log rows from nba_api, or None when that host is unavailable."""
        if not self.stats_nba_ok():
            return None
        key = (season, season_type)
        if key not in self._api_players:
            self._api_players[key] = self._league_game_log(season, season_type)
        return self._api_players[key].get(game_id)

    def live_boxscore(self, game_id: str) -> tuple[list[dict], dict[int, int]]:
        payload = self._request_json(
            f"https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/NBA/liveData/boxscore/boxscore_{game_id}.json",
            label=f"boxscore {game_id}",
        )
        return _players_and_points(payload)

    def possessions(self, game_id: str):
        """pbpstats possession objects. Live feed first, then stats.nba.com."""
        try:
            return self._pbpstats_possessions(game_id, "live")
        except SourceUnavailable:
            pass
        except Exception as exc:
            self.log(f"live possessions failed for {game_id}: {exc}")
        if not self.stats_nba_ok():
            raise SourceUnavailable(f"no possession feed for {game_id}")
        return self._retry(f"possessions {game_id}", lambda: self._pbpstats_possessions(game_id, "stats_nba"))

    def _load_schedule(self, season: str) -> list[ScheduleGame]:
        from pbpstats.data_loader.data_nba.schedule.loader import DataNbaScheduleLoader

        def _load() -> list[ScheduleGame]:
            cache: dict[str, object] = {}
            web = _ScheduleWeb()
            caching = _CachingSchedule(web, cache, self._pause)
            games: list[ScheduleGame] = []
            for season_type in ("Regular Season", "Playoffs", "PlayIn"):
                loaded = DataNbaScheduleLoader("nba", season, season_type, caching)
                for item in loaded.items:
                    status = "final" if item.is_final else "scheduled"
                    games.append(
                        ScheduleGame(
                            game_id=str(item.game_id),
                            game_date=parse_game_date(item.date),
                            status=status,
                            home_team_id=int(item.home_team_id),
                            away_team_id=int(item.away_team_id),
                            home_abbr=str(item.home_team_abbreviation),
                            away_abbr=str(item.away_team_abbreviation),
                            home_pts=_score(item.home_score, final=item.is_final),
                            away_pts=_score(item.away_score, final=item.is_final),
                            season_type=season_type,
                        )
                    )
            return games

        return self._retry(f"schedule {season}", _load)

    def _league_game_log(self, season: str, season_type: str) -> dict[str, list[dict]]:
        from nba_api.stats.endpoints import LeagueGameLog

        def _load():
            self._pause()
            endpoint = LeagueGameLog(
                season=season,
                player_or_team_abbreviation="P",
                season_type_all_star=season_type,
                timeout=int(self.timeout_seconds),
            )
            frame = endpoint.get_data_frames()[0]
            return frame.to_dict(orient="records")

        records = self._retry(f"nba_api game log {season} {season_type}", _load)
        grouped: dict[str, list[dict]] = {}
        for record in records:
            grouped.setdefault(str(record["GAME_ID"]), []).append(record)
        return grouped

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

    def _request_json(self, url: str, *, label: str) -> dict:
        def _load():
            self._pause()
            response = requests.get(url, timeout=self.timeout_seconds, headers={"User-Agent": "nba-sim"})
            if response.status_code in {403, 404}:
                raise SourceUnavailable(f"{label} returned {response.status_code}")
            response.raise_for_status()
            return response.json()

        return self._retry(label, _load)

    def _probe_stats_nba(self) -> bool:
        try:
            response = requests.get(_STATS_PROBE, headers=_STATS_HEADERS, timeout=12)
            return response.status_code == 200 and response.content[:1] in {b"{", b"["}
        except requests.RequestException:
            return False

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
            except SourceUnavailable:
                raise
            except Exception as exc:
                last = exc
                self.log(f"{label} attempt {attempt} failed: {exc}")
                if attempt == self.max_retries:
                    break
                time.sleep(delay)
                delay *= 2
        assert last is not None
        raise last


class _ScheduleWeb:
    """data.nba.com schedule fetch that sends a browser user agent and saves nothing."""

    def __init__(self) -> None:
        self.file_directory = None

    def load_data(self, league: str, season: str):
        from pbpstats.data_loader.data_nba.schedule.web import DataNbaScheduleWebLoader

        inner = DataNbaScheduleWebLoader(None)
        inner.league_string = league
        inner.season_year = season.split("-")[0]
        league_url_part = "nba" if league == "gleague" else league
        league_part = "dleague" if league == "gleague" else league
        inner.url = (
            f"https://data.{league_url_part}.com/data/10s/v2015/json/mobile_teams/"
            f"{league_part}/{inner.season_year}/league/{inner.league_id}_full_schedule.json"
        )
        response = requests.get(inner.url, headers=_STATS_HEADERS, timeout=30)
        if response.status_code in {403, 404}:
            raise SourceUnavailable(f"schedule {season} returned {response.status_code}")
        response.raise_for_status()
        inner.source_data = response.json()
        return inner.source_data


class _CachingSchedule:
    def __init__(self, inner, cache: dict[str, object], pause) -> None:
        self.inner = inner
        self.cache = cache
        self.pause = pause
        self.file_directory = None

    def load_data(self, league: str, season: str):
        if season not in self.cache:
            self.pause()
            self.cache[season] = self.inner.load_data(league, season)
        return self.cache[season]


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


def _score(value: object, *, final: bool) -> int | None:
    if not final or value is None or value == "":
        return None
    return int(value)
