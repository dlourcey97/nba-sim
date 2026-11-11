"""Box usage replaces play-by-play possession credit."""

from projections.rates import add_game_to_accumulator, empty_accumulator, vector_from_accumulator


def test_box_usage_matches_pace_and_minutes():
    acc = empty_accumulator()
    add_game_to_accumulator(
        acc,
        rate_row={
            "possessions": 190.0,
            "usage": 0.31,
            "pace": 100.0,
            "fta": 11.0,
            "ftm": 9.0,
        },
        log_row={"minutes": 36.0, "fga": 25.0, "fta": 11.0, "tov": 4.0, "stl": 1.0, "blk": 0.0},
        weight=1.0,
        align=True,
    )
    vector = vector_from_accumulator(acc)
    offensive = 100.0 * 36.0 / 48.0
    uses = 25.0 + 0.44 * 11.0 + 4.0
    assert vector.usage == uses / offensive
    # Free-throw rate stays FTA per box use, so the extra shots are field goals.
    assert vector.ft_rate == 11.0 / uses


def test_missing_pace_keeps_the_stored_usage():
    acc = empty_accumulator()
    add_game_to_accumulator(
        acc,
        rate_row={"possessions": 100.0, "usage": 0.31, "fta": 4.0, "ftm": 3.0},
        log_row={"minutes": 36.0, "fga": 25.0, "fta": 4.0, "tov": 2.0},
        weight=1.0,
    )
    vector = vector_from_accumulator(acc)
    assert vector.usage == 0.31
