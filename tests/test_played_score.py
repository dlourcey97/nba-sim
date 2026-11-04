"""Honest backtest scoring counts every player who played."""

import numpy as np

from backtest.bootstrap import paired_player_bootstrap
from backtest.metrics import crps_from_quantiles, crps_from_samples
from backtest.sim_job import _play_calibration, iter_played


class _Player:
    def __init__(self, player_id: int) -> None:
        self.player_id = player_id


def test_unprojected_players_who_played_are_scored_at_zero():
    players = [_Player(1), _Player(2)]
    logs = {
        1: {"minutes": 32.0, "pts": 20},
        2: {"minutes": 0.0, "pts": 0},
        3: {"minutes": 18.0, "pts": 9},
    }
    rows = list(iter_played(players, logs))
    assert [pid for pid, _player, _actual in rows] == [1, 3]
    assert rows[0][1] is players[0]
    assert rows[1][1] is None
    assert rows[1][2]["pts"] == 9


def test_unprojected_point_mass_crps_is_the_absolute_error():
    score = crps_from_samples(np.array([0.0]), 18.0)
    assert score == 18.0
    published = crps_from_quantiles((0.10, 0.25, 0.50, 0.75, 0.90), (0, 0, 0, 0, 0), 18.0)
    assert published == 18.0


class _Minutes:
    def __init__(self, play_prob: float, out: bool = False) -> None:
        self.play_prob = play_prob
        self.out = out


class _Projected:
    def __init__(self, player_id: int, play_prob: float) -> None:
        self.player_id = player_id
        self.minutes = _Minutes(play_prob)


class _Projection:
    def __init__(self, players) -> None:
        self.players = players


def test_play_calibration_bins_sits_and_unprojected_players():
    projection = _Projection([_Projected(1, 0.96), _Projected(2, 0.10)])
    logs = {
        1: {"minutes": 30.0},
        2: {"minutes": 0.0},
        3: {"minutes": 12.0},
    }
    brier, n, bins = _play_calibration(projection, logs)
    assert n == 3
    assert abs(brier - ((0.96 - 1.0) ** 2 + (0.10 - 0.0) ** 2 + 1.0)) < 1e-9
    assert bins[9]["count"] == 1 and bins[9]["played"] == 1
    assert bins[1]["count"] == 1 and bins[1]["played"] == 0
    assert bins[0]["count"] == 1 and bins[0]["played"] == 1


def test_player_bootstrap_weights_games_by_how_many_played():
    left = [
        {"game_id": "a", "crps_min_sum": 10.0, "crps_pts_sum": 0.0, "played_n": 1,
         "play_brier_sum": 0.0, "play_n": 1, "cover_min_hits": 1, "cover_pts_hits": 1},
        {"game_id": "b", "crps_min_sum": 30.0, "crps_pts_sum": 0.0, "played_n": 3,
         "play_brier_sum": 0.0, "play_n": 3, "cover_min_hits": 0, "cover_pts_hits": 0},
    ]
    right = [
        {"game_id": "a", "crps_min_sum": 8.0, "crps_pts_sum": 0.0, "played_n": 1,
         "play_brier_sum": 0.0, "play_n": 1, "cover_min_hits": 1, "cover_pts_hits": 1},
        {"game_id": "b", "crps_min_sum": 24.0, "crps_pts_sum": 0.0, "played_n": 3,
         "play_brier_sum": 0.0, "play_n": 3, "cover_min_hits": 0, "cover_pts_hits": 0},
    ]
    boot = paired_player_bootstrap(left, right, n_boot=200, seed=1)
    # (8+24)/(1+3) - (10+30)/(1+3) = 8 - 10
    assert abs(boot["crps_min"]["diff"] - (-2.0)) < 1e-9
