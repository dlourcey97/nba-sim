"""Live re-sim stays off the pregame path unless a ResumeState is passed."""

from __future__ import annotations

from datetime import date

import numpy as np

from projections.build import GameProjection, PlayerProjection
from projections.minutes import MinutesProjection
from projections.rates import RateVector
from sim.engine import simulate_game
from sim.live_state import state_at_period_end
from sim.resume import ResumeState, clock_to_seconds, foul_minute_factor


def test_clock_and_foul_factor():
    assert clock_to_seconds("PT11M49.00S") == 11 * 60 + 49
    assert clock_to_seconds("PT00M00.00S") == 0
    assert foul_minute_factor(6, 3, 400) == 0.0
    assert foul_minute_factor(4, 2, 400) == 0.50
    assert foul_minute_factor(4, 3, 720) == 1.0
    assert foul_minute_factor(5, 3, 720) == 0.15


def test_halftime_snapshot_ignores_the_second_half():
    box = _box()
    actions = [
        {"actionType": "period", "subType": "start", "period": 1, "periodType": "REGULAR", "clock": "PT12M00.00S"},
        _shot(101, 10, made=True, period=1, clock="PT10M00.00S", home=2, away=0),
        {"actionType": "period", "subType": "end", "period": 1, "periodType": "REGULAR", "clock": "PT00M00.00S", "scoreHome": "2", "scoreAway": "0"},
        {"actionType": "period", "subType": "start", "period": 2, "periodType": "REGULAR", "clock": "PT12M00.00S"},
        _shot(201, 20, made=True, period=2, clock="PT08M00.00S", home=2, away=2),
        {"actionType": "period", "subType": "end", "period": 2, "periodType": "REGULAR", "clock": "PT00M00.00S", "scoreHome": "2", "scoreAway": "2"},
        {"actionType": "period", "subType": "start", "period": 3, "periodType": "REGULAR", "clock": "PT12M00.00S"},
        _shot(101, 10, made=True, period=3, clock="PT09M00.00S", home=5, away=2, points=3, kind="3pt"),
    ]
    state = state_at_period_end(box, actions, 2)
    assert state.home.score == 2
    assert state.away.score == 2
    assert state.period == 2
    assert state.clock_seconds == 0
    assert state.elapsed_fraction == 0.5
    assert state.period_index == 2
    assert state.players[101].pts == 2
    assert state.players[101].fga == 1
    assert state.home.fouls_this_period == 0


def test_pregame_seed_is_stable_and_resume_keeps_the_lead():
    projection = _projection()
    first = simulate_game(projection, runs=30, seed=7, config={})
    second = simulate_game(projection, runs=30, seed=7, config={})
    assert np.array_equal(first.home_pts, second.home_pts)
    resume = ResumeState(
        period=2,
        clock_seconds=0.0,
        home=_team(10, 40),
        away=_team(20, 30),
        players={},
    )
    resumed = simulate_game(projection, runs=30, seed=7, config={}, resume=resume)
    assert np.all(resumed.home_pts >= 40)
    assert np.all(resumed.away_pts >= 30)
    assert float(np.mean(resumed.home_pts - 40)) < float(np.mean(first.home_pts))


def _shot(player_id, team_id, *, made, period, clock, home, away, points=2, kind="2pt"):
    return {
        "actionType": kind,
        "subType": "Jump Shot",
        "shotResult": "Made" if made else "Missed",
        "period": period,
        "periodType": "REGULAR",
        "clock": clock,
        "personId": player_id,
        "teamId": team_id,
        "scoreHome": str(home),
        "scoreAway": str(away),
        "possession": team_id,
        "pointsTotal": points if made else 0,
    }


def _box():
    def players(team_id, ids):
        rows = []
        for index, player_id in enumerate(ids):
            rows.append(
                {
                    "personId": player_id,
                    "firstName": "P",
                    "familyName": str(player_id),
                    "starter": "1" if index < 5 else "0",
                    "statistics": {},
                }
            )
        return rows

    return {
        "game": {
            "homeTeam": {"teamId": 10, "teamTricode": "HOM", "players": players(10, [101, 102, 103, 104, 105])},
            "awayTeam": {"teamId": 20, "teamTricode": "AWY", "players": players(20, [201, 202, 203, 204, 205])},
        }
    }


def _team(team_id, score):
    from sim.resume import TeamLive

    return TeamLive(team_id=team_id, abbr="X", score=score)


def _projection() -> GameProjection:
    players = []
    for team_id, abbr, side, ids in (
        (10, "HOM", "H", range(101, 107)),
        (20, "AWY", "A", range(201, 207)),
    ):
        for depth, player_id in enumerate(ids):
            players.append(
                PlayerProjection(
                    player_id=player_id,
                    player_name=f"P{player_id}",
                    team_id=team_id,
                    team_abbr=abbr,
                    opponent_team_id=20 if team_id == 10 else 10,
                    opponent_abbr="AWY" if team_id == 10 else "HOM",
                    home_away=side,
                    position="C" if depth == 4 else "SF",
                    started=depth < 5,
                    rates=RateVector(),
                    minutes=MinutesProjection(
                        mean=28.0 if depth < 5 else 8.0,
                        sd=1.0,
                        min_minutes=0.0,
                        max_minutes=40.0,
                        out=False,
                    ),
                    expected_team_possessions=100.0,
                    rest_days=1,
                    status="available",
                    depth_rank=depth + 1,
                )
            )
    return GameProjection(
        season="2025-26",
        game_id="0022500001",
        game_date=date(2025, 10, 22),
        home_team_id=10,
        away_team_id=20,
        home_abbr="HOM",
        away_abbr="AWY",
        home_possessions=100.0,
        away_possessions=100.0,
        players=players,
    )
