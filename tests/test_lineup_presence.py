"""Rotation stints follow the minute draw, and box per-minute rates stay on the player."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from projections.rates import RateVector, add_game_to_accumulator, blend_vectors, empty_accumulator, vector_from_accumulator
from sim.engine import _lineups_state_grid


def _share(grid: np.ndarray, player: int, bucket: int) -> np.ndarray:
    """Fraction of substints that include ``player``. Shape (runs,)."""
    chosen = grid[:, :, bucket, :, :]
    runs = chosen.shape[0]
    on = np.zeros(runs, dtype=float)
    for period in range(chosen.shape[1]):
        for sub in range(chosen.shape[2]):
            on += np.any(chosen[:, period, sub, :] == player, axis=1)
    return on / float(chosen.shape[1] * chosen.shape[2])


def _quarters(grid: np.ndarray, player: int, bucket: int) -> np.ndarray:
    """Which quarters include ``player``. Shape (runs, 4)."""
    chosen = grid[:, :, bucket, :, :]
    runs = chosen.shape[0]
    on = np.zeros((runs, chosen.shape[1]), dtype=bool)
    for period in range(chosen.shape[1]):
        for sub in range(chosen.shape[2]):
            on[:, period] |= np.any(chosen[:, period, sub, :] == player, axis=1)
    return on


def test_starters_play_every_close_quarter_and_sit_blowouts():
    rng = np.random.default_rng(4)
    # Sums to 240, the regulation team total the sim normalizes to.
    minutes_line = np.array([36, 34, 32, 30, 26, 22, 20, 16, 14, 10], dtype=float)
    players = [SimpleNamespace(team_id=1, player_id=100 + i, depth_rank=i) for i in range(len(minutes_line))]
    runs = 200
    minutes = np.repeat(minutes_line[:, None], runs, axis=1)
    # Run 0 is foul trouble: the 36-minute starter is cut to 12.
    minutes[0, 0] = 12.0
    grid = _lineups_state_grid(
        rng,
        np.arange(len(minutes_line)),
        minutes,
        players,
        flat=True,
        lineup_presence=True,
        starter_floor=24.0,
        foul_ratio=0.72,
    )
    assert grid.ndim == 5
    close = grid[:, :, 0, :, :]
    ordered = np.sort(close, axis=-1)
    assert np.all(ordered[..., 1:] != ordered[..., :-1])

    healthy = _quarters(grid, 0, 0)[1:]
    assert healthy.all()
    foul_quarters = _quarters(grid, 0, 0)[0]
    assert not bool(foul_quarters[3])
    assert abs(float(_share(grid, 0, 0)[1:].mean()) - 36.0 / 48.0) < 0.05
    assert abs(float(_share(grid, 6, 0)[1:].mean()) - 20.0 / 48.0) < 0.05
    # Blowouts keep a short stint, not a share of every quarter.
    blow_share = float(_share(grid, 0, 2).mean())
    assert 0.08 < blow_share < 0.28
    assert float(_quarters(grid, 0, 2).all(axis=1).mean()) < 0.35


def test_box_counting_rates_ignore_the_position_prior():
    acc = empty_accumulator()
    add_game_to_accumulator(
        acc,
        rate_row={"possessions": 80.0, "usage": 0.28, "fta": 8.0, "ftm": 6.0},
        log_row={
            "minutes": 36.0,
            "fga": 22.0,
            "fta": 8.0,
            "tov": 3.0,
            "oreb": 2.0,
            "dreb": 8.0,
            "ast": 9.0,
            "blk": 1.0,
            "stl": 2.0,
        },
        weight=1.0,
    )
    vector = vector_from_accumulator(acc)
    assert vector.reb_per_min == 10.0 / 36.0
    assert vector.ast_per_min == 9.0 / 36.0
    assert vector.blk_per_min == 1.0 / 36.0
    assert vector.stl_per_min == 2.0 / 36.0

    prior = RateVector(
        sample_minutes=4000.0,
        reb_per_min=0.05,
        ast_per_min=0.05,
        blk_per_min=0.01,
        stl_per_min=0.02,
        fga_per_min=0.20,
    )
    mixed = blend_vectors([(vector, 80.0)], prior=prior, prior_strength=40.0)
    assert mixed.reb_per_min == vector.reb_per_min
    assert mixed.ast_per_min == vector.ast_per_min
    assert mixed.blk_per_min == vector.blk_per_min
    assert mixed.stl_per_min == vector.stl_per_min
    assert mixed.usage < vector.usage
