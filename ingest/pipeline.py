"""Incremental backfill into the compact Parquet tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ingest.parse import (
    ScheduleGame,
    player_rows_from_box,
    player_season_aggregates,
    rates_from_possessions,
    schedule_row,
    team_rows,
    team_season_aggregates,
    team_zone_defense,
)
from ingest.pbp import possessions_to_views
from ingest.source import NbaSource, SourceUnavailable
from nba_sim.errors import SeasonFrozenError
from nba_sim.settings import Settings
from nba_sim.storage import (
    finish_run,
    mark_season_complete,
    read_rows,
    season_is_complete,
    store_rows,
    stored_game_ids,
)

_FREEZE_TABLES = ("player_game_logs", "team_game_results", "schedule")


@dataclass
class BackfillResult:
    stored_games: int = 0
    skipped_games: int = 0
    failed_games: list[str] = field(default_factory=list)
    seasons: list[str] = field(default_factory=list)


def run_backfill(
    settings: Settings,
    seasons: list[str],
    *,
    season_types: list[str],
    start_date: date | None = None,
    end_date: date | None = None,
    max_games: int | None = None,
    source: NbaSource | None = None,
    log=print,
) -> BackfillResult:
    http = settings.config["http"]
    active = source or NbaSource(
        delay_seconds=float(http["delay_seconds"]),
        max_retries=int(http["max_retries"]),
        backoff_seconds=float(http["backoff_seconds"]),
        timeout_seconds=float(http["timeout_seconds"]),
        log=log,
        current_season=settings.current_season,
    )
    result = BackfillResult(seasons=list(seasons))
    partial = start_date is not None or end_date is not None or max_games is not None
    for season in seasons:
        failed_before = len(result.failed_games)
        for season_type in season_types:
            _run_season_type(
                settings,
                active,
                season,
                season_type,
                start_date,
                end_date,
                max_games,
                result,
                log,
            )
        _rewrite_derived(settings, season, log)
        failed_here = len(result.failed_games) - failed_before
        if not partial and failed_here == 0 and _season_is_older(season, settings.current_season):
            for table in _FREEZE_TABLES:
                if stored_game_ids(settings, table, season) or table == "schedule":
                    if read_rows(settings, table, season):
                        mark_season_complete(settings, table, season)
                        log(f"Froze {table} {season}.")
        active.clear_schedule_cache()
    finish_run(settings)
    log(
        f"Backfill finished. Stored {result.stored_games} games, "
        f"skipped {result.skipped_games}, failed {len(result.failed_games)}."
    )
    if result.failed_games:
        log("Failed game ids: " + ", ".join(result.failed_games))
    return result


def _run_season_type(
    settings: Settings,
    source: NbaSource,
    season: str,
    season_type: str,
    start_date: date | None,
    end_date: date | None,
    max_games: int | None,
    result: BackfillResult,
    log,
) -> None:
    if all(season_is_complete(settings, table, season) for table in _FREEZE_TABLES):
        log(f"{season} {season_type}: frozen, skipping.")
        return
    try:
        games = source.schedule(season, season_type)
    except Exception as exc:
        log(f"{season} {season_type}: schedule failed: {exc}")
        result.failed_games.append(f"{season}:{season_type}")
        return
    selected = [
        game
        for game in games
        if (start_date is None or game.game_date >= start_date)
        and (end_date is None or game.game_date <= end_date)
    ]
    selected.sort(key=lambda game: (game.game_date, game.game_id))
    finals = [game for game in selected if game.is_final]
    if max_games is not None:
        finals = finals[:max_games]
        keep = {game.game_id for game in finals}
        selected = [game for game in selected if game.game_id in keep or not game.is_final]
    logged = stored_game_ids(settings, "player_game_logs", season)
    rated = stored_game_ids(settings, "player_game_rates", season)
    log(
        f"{season} {season_type}: {len(finals)} final games in range, "
        f"{sum(game.game_id in logged and game.game_id in rated for game in finals)} already stored."
    )
    rate_memory = read_rows(settings, "player_game_rates", season)
    for game in selected:
        if not game.is_final:
            _store_open(settings, "schedule", season, [schedule_row(season, game)], log)
            continue
        if game.game_id in logged and game.game_id in rated:
            _store_open(settings, "schedule", season, [schedule_row(season, game)], log)
            result.skipped_games += 1
            continue
        try:
            _store_game(settings, source, season, game, logged, rated, rate_memory, log)
        except SeasonFrozenError:
            result.skipped_games += 1
            continue
        except Exception as exc:
            log(f"Failed {game.game_id} {game.game_date}: {exc}")
            result.failed_games.append(game.game_id)
            continue
        result.stored_games += 1
        logged.add(game.game_id)
        rated.add(game.game_id)


def _store_game(
    settings: Settings,
    source: NbaSource,
    season: str,
    game: ScheduleGame,
    logged: set[str],
    rated: set[str],
    rate_memory: list[dict],
    log,
) -> None:
    need_logs = game.game_id not in logged
    need_rates = game.game_id not in rated
    players: list[dict] = []
    team_points: dict[int, int] = {}
    if need_logs:
        players, team_points = _load_box(source, season, game)
    pace: dict[int, float] = {}
    overtime = 0
    rate_rows: list[dict] = []
    if need_rates:
        views = possessions_to_views(source.possessions(game.game_id))
        if not players:
            players = _players_from_logs(settings, season, game.game_id)
            team_points = {
                game.home_team_id: game.home_pts or 0,
                game.away_team_id: game.away_pts or 0,
            }
        rate_rows, pace, overtime = rates_from_possessions(season, game, players, views)
    if need_logs and players:
        if not team_points:
            team_points = {
                game.home_team_id: game.home_pts or 0,
                game.away_team_id: game.away_pts or 0,
            }
        _store_open(
            settings,
            "player_game_logs",
            season,
            player_rows_from_box(season, game, players, team_points),
            log,
        )
        _store_open(
            settings,
            "team_game_results",
            season,
            team_rows(season, game, team_points, pace, overtime),
            log,
        )
    if need_rates:
        rate_memory[:] = [row for row in rate_memory if str(row["game_id"]) != game.game_id]
        rate_memory.extend(rate_rows)
        store_rows(settings, "player_game_rates", season, rate_memory)
    _store_open(settings, "schedule", season, [schedule_row(season, game)], log)
    log(f"Stored {game.game_id} {game.game_date} {game.away_abbr} at {game.home_abbr}.")


def _store_open(settings: Settings, table: str, season: str, rows: list[dict], log) -> None:
    try:
        store_rows(settings, table, season, rows, allow_historical=True)
    except SeasonFrozenError as exc:
        log(str(exc))


def _players_from_logs(settings: Settings, season: str, game_id: str) -> list[dict]:
    return [
        {
            "player_id": row["player_id"],
            "team_id": row["team_id"],
            "minutes": row["minutes"],
            "name": row["player_name"],
        }
        for row in read_rows(settings, "player_game_logs", season)
        if str(row["game_id"]) == game_id
    ]


def _load_box(source: NbaSource, season: str, game: ScheduleGame) -> tuple[list[dict], dict[int, int]]:
    """Historical seasons read stats.nba.com first. The live box score is the fallback."""
    if _historical(source, season):
        loaded = _stats_box(source, game)
        if loaded is not None:
            return loaded
        records = _api_records(source, season, game)
        if records:
            return _api_records_as_box(game, records)
    try:
        return source.live_boxscore(game.game_id)
    except SourceUnavailable:
        if _historical(source, season):
            raise SourceUnavailable(f"no box score for {game.game_id}") from None
        records = _api_records(source, season, game)
        if not records:
            raise SourceUnavailable(f"no box score for {game.game_id}") from None
        return _api_records_as_box(game, records)


def _historical(source: NbaSource, season: str) -> bool:
    current = getattr(source, "current_season", None)
    return current is not None and season != current


def _stats_box(source: NbaSource, game: ScheduleGame) -> tuple[list[dict], dict[int, int]] | None:
    method = getattr(source, "stats_boxscore", None)
    if method is None:
        return None
    try:
        return method(game.game_id)
    except SourceUnavailable:
        return None
    except Exception as exc:
        source_log = getattr(source, "log", None)
        if source_log is not None:
            source_log(f"stats.nba.com box score failed for {game.game_id}: {exc}")
        return None


def _api_records(source: NbaSource, season: str, game: ScheduleGame) -> list[dict] | None:
    try:
        return source.api_player_rows(season, game.season_type, game.game_id)
    except Exception as exc:
        source_log = getattr(source, "log", None)
        if source_log is not None:
            source_log(f"stats.nba.com player log failed for {game.game_id}: {exc}")
        return None


def _api_records_as_box(game: ScheduleGame, records: list[dict]) -> tuple[list[dict], dict[int, int]]:
    players = []
    for record in records:
        players.append(
            {
                "player_id": record["PLAYER_ID"],
                "name": record.get("PLAYER_NAME"),
                "team_id": int(record["TEAM_ID"]),
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
    points = {
        game.home_team_id: int(game.home_pts or 0),
        game.away_team_id: int(game.away_pts or 0),
    }
    return players, points


def _rewrite_derived(settings: Settings, season: str, log) -> None:
    logs = read_rows(settings, "player_game_logs", season)
    rates = read_rows(settings, "player_game_rates", season)
    teams = read_rows(settings, "team_game_results", season)
    if not logs and not rates and not teams:
        return
    store_rows(settings, "player_season_aggregates", season, player_season_aggregates(logs, rates))
    store_rows(settings, "team_season_aggregates", season, team_season_aggregates(teams))
    store_rows(settings, "team_zone_defense", season, team_zone_defense(season, logs, rates, teams))
    log(f"Rewrote derived tables for {season}.")


def _season_is_older(season: str, current: str) -> bool:
    return season < current
