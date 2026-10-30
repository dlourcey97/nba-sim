"""Tracking multipliers stay off until a flag is on."""

from projections.rates import RateVector
from projections.tracking import _creation_factor, apply_tracking_rates


class _Cache:
    tracking_rows = None


def test_tracking_is_a_noop_when_flags_are_off() -> None:
    rates = RateVector(usage=0.22, sample_games=4)
    out = apply_tracking_rates(
        rates,
        player_id=1,
        season="2025-26",
        config={"context": {}},
        cache=_Cache(),
        settings=None,
    )
    assert out is rates


def test_creation_factor_shrinks_toward_one() -> None:
    row = {"season": "2024-25", "player_id": 1, "pullup_fga": 400.0, "catch_fga": 100.0}
    league = {"season": "2024-25", "player_id": 2, "pullup_fga": 100.0, "catch_fga": 400.0}
    factor = _creation_factor([row, league], "2024-25", row)
    assert 1.0 < factor <= 1.02
