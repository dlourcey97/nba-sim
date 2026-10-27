"""P(double-double) from in-memory sim draws. No persisted runs."""

import numpy as np

from outputs.confidence import double_double_from_draws


def test_pair_with_highest_joint_rate_drives_the_label():
    n = 100
    pts = np.array([12] * 80 + [4] * 20, dtype=float)
    reb = np.array([11] * 60 + [3] * 40, dtype=float)
    ast = np.array([11] * 10 + [2] * 90, dtype=float)
    stl = np.zeros(n)
    blk = np.zeros(n)
    p_dd, pair, joint = double_double_from_draws(
        {"pts": pts, "reb": reb, "ast": ast, "stl": stl, "blk": blk}
    )
    # 60 sims have PTS+REB; 10 have PTS+AST. No other pair clears 10.
    assert pair == "PTS+REB"
    assert joint == 0.60
    assert p_dd == 0.60


def test_one_category_is_not_a_double_double():
    n = 50
    p_dd, pair, joint = double_double_from_draws(
        {
            "pts": np.full(n, 20.0),
            "reb": np.full(n, 4.0),
            "ast": np.full(n, 4.0),
            "stl": np.full(n, 1.0),
            "blk": np.full(n, 1.0),
        }
    )
    assert p_dd == 0.0
    assert joint == 0.0
    assert pair
