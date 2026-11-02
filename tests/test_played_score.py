"""Honest backtest scoring counts every player who played."""

from backtest.sim_job import iter_played


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
