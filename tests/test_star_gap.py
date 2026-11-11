"""The graded star gap blocks on out-of-sample points, not season averages."""

from backtest.star_gap import aggregate_star_gap


def test_gap_uses_actual_points_of_high_usage_players():
    rows = []
    for pid in range(30):
        for _game in range(3):
            rows.append(
                {
                    "player_id": pid,
                    "usage": 0.30,
                    "pred_pts": 18.0,
                    "pred_p50": 17.0,
                    "actual_pts": 24.0,
                }
            )
    for pid in range(30, 40):
        for _game in range(4):
            rows.append(
                {
                    "player_id": pid,
                    "usage": 0.08,
                    "pred_pts": 4.0,
                    "pred_p50": 3.0,
                    "actual_pts": 4.0,
                }
            )
    pred, _med, actual, gap, players, player_games, passed = aggregate_star_gap(rows)
    assert players == 30
    assert player_games == 90
    assert pred == 18.0
    assert actual == 24.0
    assert abs(gap - (-25.0)) < 1e-9
    assert passed is False


def test_gap_inside_five_percent_passes():
    rows = [
        {
            "player_id": pid,
            "usage": 0.28,
            "pred_pts": 20.0,
            "pred_p50": 19.0,
            "actual_pts": 20.5,
        }
        for pid in range(20)
        for _game in range(3)
    ]
    _pred, _med, _actual, gap, _players, _games, passed = aggregate_star_gap(rows)
    assert abs(gap) < 5.0
    assert passed is True
