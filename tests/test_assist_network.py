"""Assist-edge extraction and network-weighted passer selection."""

from __future__ import annotations

from datetime import date

import numpy as np

from ingest.assists import assist_edges_from_actions, assist_edges_from_possessions
from ingest.parse import CourtEvent, PossessionView
from sim.engine import _assist_matrix, _credit_assists


def test_assist_edges_from_possessions():
    events = [
        CourtEvent(
            kind="field_goal",
            team_id=1,
            player_id=10,
            made=True,
            assist_player_id=20,
        ),
        CourtEvent(
            kind="field_goal",
            team_id=1,
            player_id=10,
            made=True,
            assist_player_id=20,
        ),
        CourtEvent(
            kind="field_goal",
            team_id=1,
            player_id=11,
            made=True,
            assist_player_id=None,
        ),
    ]
    views = [PossessionView(offense_team_id=1, period=1, events=events)]
    rows = assist_edges_from_possessions(
        season="2025-26",
        game_id="g1",
        game_date=date(2025, 11, 1),
        possessions=views,
    )
    assert len(rows) == 1
    assert rows[0]["passer_id"] == 20
    assert rows[0]["shooter_id"] == 10
    assert rows[0]["assists"] == 2


def test_assist_edges_from_actions_assist_person_id():
    actions = [
        {
            "assistPersonId": 20,
            "personId": 10,
            "teamId": 1,
            "shotResult": "Made",
            "actionType": "Made Shot",
        },
        {
            "personId": 11,
            "teamId": 1,
            "shotResult": "Made",
            "actionType": "Made Shot",
        },
    ]
    rows = assist_edges_from_actions(
        season="2025-26",
        game_id="g1",
        game_date=date(2025, 11, 1),
        actions=actions,
        home_team_id=1,
        away_team_id=2,
    )
    assert len(rows) == 1
    assert rows[0]["assists"] == 1


def test_assist_matrix_and_credit_prefers_network():
    class _P:
        def __init__(self, pid):
            self.player_id = pid

    players = [_P(100), _P(200), _P(300)]
    network = {100: {200: 50.0, 300: 1.0}}
    mat = _assist_matrix(players, network)
    assert mat[1, 0] == 50.0  # passer 200 → shooter 100
    assert mat[2, 0] == 1.0

    packed = {
        "ast_rate": np.array([0.1, 0.1, 0.5]),
        "assist_p_scale": 1.0,
        "assist_matrix": mat,
    }
    # One run, lineup [0,1,2], shooter slot 0 (player 100).
    off_lineups = np.array([[0, 1, 2]], dtype=np.int32)
    user_slot = np.array([0], dtype=np.int32)
    is_make = np.array([True])
    ast = np.zeros((3, 1), dtype=float)
    rng = np.random.default_rng(0)
    # Force many assisted makes: high scale via ast_rate sum.
    packed["ast_rate"] = np.array([0.1, 0.4, 0.4])
    counts = np.zeros(3, dtype=int)
    for seed in range(200):
        ast[:] = 0
        _credit_assists(
            np.random.default_rng(seed),
            is_make=is_make,
            off_lineups=off_lineups,
            user_slot=user_slot,
            packed=packed,
            ast=ast,
        )
        if ast[1, 0] > 0:
            counts[1] += 1
        if ast[2, 0] > 0:
            counts[2] += 1
    # Network strongly prefers passer index 1 (200) over 2 (300).
    assert counts[1] > counts[2]
