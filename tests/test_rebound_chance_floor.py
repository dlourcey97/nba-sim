"""Thin play-by-play chance counts must not inflate rebound rates."""

from projections.rates import (
    add_game_to_accumulator,
    empty_accumulator,
    stabilized_rebound_chances,
    vector_from_accumulator,
)


def test_normal_chance_density_is_unchanged():
    chances = 30.0
    minutes = 32.0
    assert stabilized_rebound_chances(chances, minutes) == chances


def test_carter_style_collapse_uses_league_density():
    # 7 chances in 33 minutes was a 0.94 rate on 6.7 defensive boards.
    chances = stabilized_rebound_chances(7.2, 32.9)
    assert chances == 32.9 * 0.975
    rate = 6.7 / chances
    assert 0.15 < rate < 0.30


def test_short_stint_is_left_alone():
    assert stabilized_rebound_chances(1.0, 6.0) == 1.0


def test_dated_holdout_game_keeps_the_recorded_chances():
    acc = empty_accumulator()
    add_game_to_accumulator(
        acc,
        rate_row={
            "possessions": 80.0,
            "usage": 0.20,
            "oreb_chances": 4.0,
            "dreb_chances": 7.0,
            "fta": 2.0,
            "ftm": 1.0,
            "game_date": "2025-01-15",
        },
        log_row={"minutes": 33.0, "oreb": 3.0, "dreb": 7.0, "tov": 1.0, "stl": 0.0, "blk": 1.0, "ast": 2.0},
        weight=1.0,
    )
    vector = vector_from_accumulator(acc)
    assert vector.dreb_rate == 7.0 / 7.0


def test_accumulator_lowers_the_rate():
    acc = empty_accumulator()
    add_game_to_accumulator(
        acc,
        rate_row={
            "possessions": 80.0,
            "usage": 0.20,
            "oreb_chances": 4.0,
            "dreb_chances": 7.0,
            "fta": 2.0,
            "ftm": 1.0,
        },
        log_row={"minutes": 33.0, "oreb": 3.0, "dreb": 7.0, "tov": 1.0, "stl": 0.0, "blk": 1.0, "ast": 2.0},
        weight=1.0,
    )
    vector = vector_from_accumulator(acc)
    assert vector.dreb_rate < 0.30
    assert vector.dreb_rate == 7.0 / (33.0 * 0.975)
