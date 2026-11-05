"""Help defense moves make rate from the other four, not the primary again."""

from __future__ import annotations

import numpy as np
import pytest

from sim.engine import _help_make_factor, _side_factor_mean


class _Minutes:
    def __init__(self, mean: float, play_prob: float = 1.0, out: bool = False) -> None:
        self.mean = mean
        self.play_prob = play_prob
        self.out = out


class _Player:
    def __init__(self, side: str, mean: float, play_prob: float = 1.0) -> None:
        self.home_away = side
        self.minutes = _Minutes(mean, play_prob)


def test_average_helpers_do_not_change_the_make_rate():
    # Primary is column 0. The other four average exactly 1.0.
    on_court = np.array([[0.96, 0.98, 1.02, 0.97, 1.03]])
    factor = _help_make_factor(on_court, np.array([0]), np.array([1.0]), help_weight=0.35)
    assert float(factor[0]) == pytest.approx(1.0)


def test_primary_is_not_counted_as_help():
    on_court = np.array([[0.90, 1.00, 1.00, 1.00, 1.00]])
    factor = _help_make_factor(on_court, np.array([0]), np.array([1.0]), help_weight=0.35)
    assert float(factor[0]) == pytest.approx(1.0)


def test_strong_help_lowers_the_make_rate():
    on_court = np.array([[1.00, 0.90, 0.90, 0.90, 0.90]])
    factor = _help_make_factor(on_court, np.array([0]), np.array([1.0]), help_weight=0.35)
    assert float(factor[0]) == pytest.approx(1.0 + 0.35 * (0.90 - 1.0))


def test_weak_help_raises_the_make_rate_above_a_good_team_mean():
    # The other four are league average, but this team usually defends better.
    on_court = np.array([[0.94, 1.00, 1.00, 1.00, 1.00]])
    factor = _help_make_factor(on_court, np.array([0]), np.array([0.96]), help_weight=0.35)
    assert float(factor[0]) == pytest.approx(1.0 + 0.35 * (1.00 - 0.96))


def test_team_mean_weights_expected_minutes_and_ignores_the_other_side():
    players = [
        _Player("H", 30.0),
        _Player("H", 10.0),
        _Player("A", 40.0),
    ]
    factors = np.array([0.90, 1.10, 0.50])
    means = _side_factor_mean(players, factors)
    home = (30.0 * 0.90 + 10.0 * 1.10) / 40.0
    assert float(means[0]) == pytest.approx(home)
    assert float(means[1]) == pytest.approx(home)
    assert float(means[2]) == pytest.approx(0.50)
