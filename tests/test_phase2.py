"""Phase 2: compact rows and a resumable backfill that does not need the network."""

from __future__ import annotations

from datetime import date

import pytest

from backfill import main
from ingest.parse import (
    CourtEvent,
    PossessionView,
    ScheduleGame,
    games_from_cdn_schedule,
    games_from_data_nba_schedule,
    games_from_team_log,
    parse_game_date,
    parse_minutes,
    parse_seasons,
    player_rows_from_box,
    rates_from_possessions,
    shot_zone,
)
from ingest.pbp import possessions_to_views
from ingest.pipeline import run_backfill
from ingest.source import SourceUnavailable
from nba_sim.storage import read_rows
from pbpstats.resources.enhanced_pbp.field_goal import FieldGoal


def _game(**overrides) -> ScheduleGame:
    values = dict(
        game_id="0022400001",
        game_date=date(2024, 10, 22),
        status="final",
        home_team_id=1610612738,
        away_team_id=1610612752,
        home_abbr="BOS",
        away_abbr="NYK",
        home_pts=110,
        away_pts=100,
        season_type="Regular Season",
    )
    values.update(overrides)
    return ScheduleGame(**values)


def _players() -> list[dict]:
    return [
        {
            "player_id": 10,
            "name": "Home Star",
            "team_id": 1610612738,
            "team_abbreviation": "BOS",
            "played": "1",
            "starter": "1",
            "position": "SF",
            "minutes": "PT30M00.00S",
            "points": 20,
            "reboundsTotal": 5,
            "assists": 4,
            "threePointersMade": 1,
            "steals": 1,
            "blocks": 0,
            "turnovers": 2,
            "fieldGoalsMade": 8,
            "fieldGoalsAttempted": 15,
            "threePointersAttempted": 4,
            "freeThrowsMade": 3,
            "freeThrowsAttempted": 4,
            "reboundsOffensive": 1,
            "reboundsDefensive": 4,
            "plusMinusPoints": 8,
        },
        {
            "player_id": 11,
            "name": "Home Mate",
            "team_id": 1610612738,
            "team_abbreviation": "BOS",
            "played": "1",
            "starter": "0",
            "position": "PG",
            "minutes": 20,
            "points": 8,
            "reboundsTotal": 2,
            "assists": 6,
            "threePointersMade": 0,
            "steals": 0,
            "blocks": 0,
            "turnovers": 1,
            "fieldGoalsMade": 3,
            "fieldGoalsAttempted": 6,
            "threePointersAttempted": 1,
            "freeThrowsMade": 2,
            "freeThrowsAttempted": 2,
            "reboundsOffensive": 0,
            "reboundsDefensive": 2,
            "plusMinusPoints": 4,
        },
        {
            "player_id": 20,
            "name": "Away Wing",
            "team_id": 1610612752,
            "team_abbreviation": "NYK",
            "played": "1",
            "starter": "1",
            "position": "SG",
            "minutes": "28:30",
            "points": 18,
            "reboundsTotal": 3,
            "assists": 2,
            "threePointersMade": 2,
            "steals": 1,
            "blocks": 1,
            "turnovers": 1,
            "fieldGoalsMade": 7,
            "fieldGoalsAttempted": 14,
            "threePointersAttempted": 6,
            "freeThrowsMade": 2,
            "freeThrowsAttempted": 2,
            "reboundsOffensive": 0,
            "reboundsDefensive": 3,
            "plusMinusPoints": -8,
        },
        {
            "player_id": 99,
            "name": "Did Not Play",
            "team_id": 1610612738,
            "team_abbreviation": "BOS",
            "played": "0",
            "starter": "0",
            "position": "",
            "minutes": "PT00M00.00S",
            "points": 0,
            "reboundsTotal": 0,
            "assists": 0,
            "threePointersMade": 0,
            "steals": 0,
            "blocks": 0,
            "turnovers": 0,
            "fieldGoalsMade": 0,
            "fieldGoalsAttempted": 0,
            "threePointersAttempted": 0,
            "freeThrowsMade": 0,
            "freeThrowsAttempted": 0,
            "reboundsOffensive": 0,
            "reboundsDefensive": 0,
            "plusMinusPoints": 0,
        },
    ]


def _views() -> list[PossessionView]:
    lineup = {1610612738: (10, 11), 1610612752: (20,)}
    made = CourtEvent(
        kind="field_goal",
        team_id=1610612738,
        player_id=10,
        lineup=lineup,
        made=True,
        shot_zone="restricted_area",
    )
    missed = CourtEvent(
        kind="field_goal",
        team_id=1610612752,
        player_id=20,
        lineup=lineup,
        made=False,
        shot_zone="above_break_3",
    )
    free_throw = CourtEvent(
        kind="free_throw",
        team_id=1610612738,
        player_id=10,
        lineup=lineup,
        made=True,
    )
    return [
        PossessionView(1610612738, 1, [made], counts=True),
        PossessionView(1610612752, 5, [missed, free_throw], counts=True),
    ]


class FakeSource:
    def __init__(self, games: list[ScheduleGame], *, fail_pbp: set[str] | None = None, api_only: set[str] | None = None):
        self.games = games
        self.fail_pbp = fail_pbp or set()
        self.api_only = api_only or set()
        self.box_calls: list[str] = []
        self.pbp_calls: list[str] = []
        self.api_calls: list[str] = []

    def schedule(self, season: str, season_type: str) -> list[ScheduleGame]:
        return [game for game in self.games if game.season_type == season_type]

    def live_boxscore(self, game_id: str):
        self.box_calls.append(game_id)
        if game_id in self.api_only:
            raise SourceUnavailable(game_id)
        game = next(game for game in self.games if game.game_id == game_id)
        return _players(), {game.home_team_id: game.home_pts or 0, game.away_team_id: game.away_pts or 0}

    def api_player_rows(self, season: str, season_type: str, game_id: str):
        self.api_calls.append(game_id)
        if game_id not in self.api_only:
            return None
        return [
            {
                "GAME_ID": game_id,
                "PLAYER_ID": 10,
                "PLAYER_NAME": "Api Player",
                "TEAM_ID": 1610612738,
                "TEAM_ABBREVIATION": "BOS",
                "MIN": 30,
                "PTS": 12,
                "REB": 3,
                "AST": 4,
                "FG3M": 1,
                "STL": 0,
                "BLK": 0,
                "TOV": 1,
                "FGM": 5,
                "FGA": 10,
                "FG3A": 3,
                "FTM": 1,
                "FTA": 2,
                "OREB": 0,
                "DREB": 3,
                "PLUS_MINUS": 5,
            }
        ]

    def possessions(self, game_id: str):
        self.pbp_calls.append(game_id)
        if game_id in self.fail_pbp:
            raise SourceUnavailable(game_id)
        return _views()

    def clear_schedule_cache(self) -> None:
        return None


@pytest.fixture
def identity_views(monkeypatch):
    monkeypatch.setattr("ingest.pipeline.possessions_to_views", lambda items: items)


def test_schedule_rows_from_stats_and_cdn():
    games = games_from_team_log(
        [
            {
                "GAME_ID": "0022400061",
                "GAME_DATE": "2024-10-22",
                "MATCHUP": "BOS vs. NYK",
                "TEAM_ID": 1610612738,
                "TEAM_ABBREVIATION": "BOS",
                "PTS": 132,
            },
            {
                "GAME_ID": 22400061,
                "GAME_DATE": "2024-10-22",
                "MATCHUP": "NYK @ BOS",
                "TEAM_ID": 1610612752,
                "TEAM_ABBREVIATION": "NYK",
                "PTS": 109,
            },
            {
                "GAME_ID": "0012400001",
                "GAME_DATE": "2024-10-04",
                "MATCHUP": "BOS vs. NYK",
                "TEAM_ID": 1610612738,
                "TEAM_ABBREVIATION": "BOS",
                "PTS": 90,
            },
        ]
    )
    assert len(games) == 1
    assert games[0].game_id == "0022400061"
    assert games[0].home_abbr == "BOS"
    assert games[0].away_pts == 109
    assert games[0].season_type == "Regular Season"
    assert games[0].is_final
    cdn = games_from_cdn_schedule(
        {
            "leagueSchedule": {
                "seasonYear": "2025-26",
                "gameDates": [
                    {
                        "gameDate": "10/22/2025 00:00:00",
                        "games": [
                            {
                                "gameId": "0022500001",
                                "gameStatus": 1,
                                "gameStatusText": "7:30 pm ET",
                                "homeTeam": {"teamId": 1610612738, "teamTricode": "BOS", "score": 0},
                                "awayTeam": {"teamId": 1610612752, "teamTricode": "NYK", "score": 0},
                            }
                        ],
                    }
                ],
            }
        },
        "2025-26",
    )
    assert cdn[0].status == "scheduled"
    assert cdn[0].home_pts is None
    assert cdn[0].game_date == parse_game_date("2025-10-22")
    with pytest.raises(ValueError):
        games_from_cdn_schedule({"leagueSchedule": {"seasonYear": "2026-27", "gameDates": []}}, "2025-26")
    assert "DataNbaScheduleLoader" not in open("ingest/source.py", encoding="utf-8").read()
    mobile = games_from_data_nba_schedule(
        {
            "lscd": [
                {
                    "mscd": {
                        "g": [
                            {
                                "gid": "0022400061",
                                "gdte": "2024-10-22",
                                "stt": "Final",
                                "h": {"tid": 1610612738, "ta": "BOS", "s": "132"},
                                "v": {"tid": 1610612752, "ta": "NYK", "s": "109"},
                            }
                        ]
                    }
                }
            ]
        },
        "2024-25",
    )
    assert mobile[0].home_abbr == "BOS"
    assert mobile[0].away_pts == 109
    assert mobile[0].is_final


def test_parse_seasons_and_minutes():
    assert parse_seasons("2024-25") == ["2024-25"]
    labels = parse_seasons("2015-2025")
    assert labels[0] == "2015-16"
    assert labels[-1] == "2025-26"
    assert len(labels) == 11
    with pytest.raises(ValueError):
        parse_seasons("2025-2015")
    assert parse_minutes("PT34M10.00S") == pytest.approx(34 + 10 / 60)
    assert parse_minutes("28:30") == pytest.approx(28.5)
    assert shot_zone("Corner3", -20, False) == "left_corner_3"
    assert shot_zone("Corner3", 20, False) == "right_corner_3"
    assert shot_zone("AtRim", 0, False) == "restricted_area"


def test_box_rows_skip_dnp_and_rates_count_chances():
    game = _game()
    rows = player_rows_from_box("2024-25", game, _players(), {1610612738: 110, 1610612752: 100})
    assert [row["player_id"] for row in rows] == [10, 11, 20]
    star = rows[0]
    assert star["started"] is True
    assert star["position"] == "SF"
    assert star["home_away"] == "H"
    assert star["win"] is True
    assert star["minutes"] == pytest.approx(30)

    rate_rows, pace, overtime = rates_from_possessions("2024-25", game, _players(), _views())
    by_player = {row["player_id"]: row for row in rate_rows}
    assert 99 not in by_player
    assert by_player[10]["usage"] == pytest.approx(1.0)
    assert by_player[11]["usage"] == pytest.approx(0.0)
    assert by_player[11]["ast_chances"] == pytest.approx(1.0)
    assert by_player[20]["oreb_chances"] == pytest.approx(1.0)
    assert by_player[10]["dreb_chances"] == pytest.approx(1.0)
    assert by_player[10]["fta"] == pytest.approx(1.0)
    assert by_player[10]["ftm"] == pytest.approx(1.0)
    assert by_player[10]["restricted_area_fgm"] == pytest.approx(1.0)
    assert pace[1610612738] == pytest.approx(1.0)
    assert overtime == 1


def test_possessions_to_views_maps_a_field_goal():
    class Shot(FieldGoal):
        is_made = True
        shot_value = 2
        shot_type = "AtRim"
        locX = -8
        player1_id = 10
        team_id = 1610612738
        is_possession_ending_event = True
        count_as_possession = True

        @property
        def current_players(self):
            return {1610612738: [10, 0], 1610612752: [20]}

    class Possession:
        offense_team_id = 1610612738
        period = 2
        events = [Shot()]

    views = possessions_to_views([Possession()])
    assert len(views) == 1
    assert views[0].counts is True
    event = views[0].events[0]
    assert event.kind == "field_goal"
    assert event.shot_zone == "restricted_area"
    assert event.player_id == 10
    assert 0 not in event.lineup[1610612738]


def test_backfill_stores_one_game_then_skips(settings, identity_views, capsys):
    source = FakeSource([_game(), _game(game_id="0022400099", status="scheduled", home_pts=None, away_pts=None)])
    first = run_backfill(
        settings,
        ["2024-25"],
        season_types=["Regular Season"],
        start_date=date(2024, 10, 22),
        end_date=date(2024, 10, 22),
        max_games=1,
        source=source,
    )
    assert first.stored_games == 1
    assert first.failed_games == []
    logs = read_rows(settings, "player_game_logs", "2024-25")
    assert {row["player_id"] for row in logs} == {10, 11, 20}
    teams = read_rows(settings, "team_game_results", "2024-25")
    assert {row["team_abbr"] for row in teams} == {"BOS", "NYK"}
    assert all(row["pace"] == 1 for row in teams)
    rates = read_rows(settings, "player_game_rates", "2024-25")
    assert len(rates) == 3
    schedule = read_rows(settings, "schedule", "2024-25")
    assert {row["status"] for row in schedule} == {"final", "scheduled"}
    aggregates = read_rows(settings, "player_season_aggregates", "2024-25")
    assert any(row["player_id"] == 10 and row["games"] == 1 for row in aggregates)
    assert not (settings.data_dir / "player_game_logs" / "season=2024-25" / "_COMPLETE").exists()
    assert list(settings.data_dir.rglob("*.json")) == []

    second = run_backfill(
        settings,
        ["2024-25"],
        season_types=["Regular Season"],
        start_date=date(2024, 10, 22),
        end_date=date(2024, 10, 22),
        source=source,
    )
    assert second.stored_games == 0
    assert second.skipped_games == 1
    assert source.box_calls == ["0022400001"]
    captured = capsys.readouterr()
    assert "bytes" in captured.out.lower() or "used" in captured.out.lower() or "DATA_DIR" in captured.out


def test_failed_possession_is_recorded_and_not_frozen(settings, identity_views):
    source = FakeSource([_game()], fail_pbp={"0022400001"})
    result = run_backfill(
        settings,
        ["2024-25"],
        season_types=["Regular Season"],
        source=source,
    )
    assert result.failed_games == ["0022400001"]
    assert read_rows(settings, "player_game_logs", "2024-25") == []
    assert not (settings.data_dir / "player_game_logs" / "season=2024-25" / "_COMPLETE").exists()


def test_full_older_season_freezes_fact_tables(settings, identity_views):
    source = FakeSource([_game()])
    result = run_backfill(
        settings,
        ["2024-25"],
        season_types=["Regular Season"],
        source=source,
    )
    assert result.failed_games == []
    for table in ("player_game_logs", "team_game_results", "schedule"):
        assert (settings.data_dir / table / "season=2024-25" / "_COMPLETE").is_file()
    assert not (settings.data_dir / "player_game_rates" / "season=2024-25" / "_COMPLETE").exists()
    source.schedule_calls = 0
    original = source.schedule

    def counting(season: str, season_type: str):
        source.schedule_calls += 1
        return original(season, season_type)

    source.schedule = counting
    again = run_backfill(
        settings,
        ["2024-25"],
        season_types=["Regular Season", "Playoffs", "PlayIn"],
        source=source,
    )
    assert again.stored_games == 0
    assert source.schedule_calls == 0
    assert source.box_calls == ["0022400001"]


def test_api_box_fallback(settings, identity_views):
    source = FakeSource([_game()], api_only={"0022400001"})
    result = run_backfill(
        settings,
        ["2024-25"],
        season_types=["Regular Season"],
        max_games=1,
        source=source,
    )
    assert result.stored_games == 1
    logs = read_rows(settings, "player_game_logs", "2024-25")
    assert logs[0]["player_name"] == "Api Player"
    assert logs[0]["started"] is False
    assert source.api_calls == ["0022400001"]


def test_cli_rejects_a_full_and_a_single_season_together():
    with pytest.raises(SystemExit):
        main(["--seasons", "2015-2025", "--season", "2024-25"])


def test_cli_log_file_must_stay_outside_the_repo(monkeypatch):
    monkeypatch.setattr(
        "backfill.run_backfill",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ran")),
    )
    with pytest.raises(SystemExit):
        main(["--season", "2024-25", "--log-file", "backfill.log"])
    assert main(["--season", "2024-25", "--log-file", "/workspace/backfill.log"]) == 1
