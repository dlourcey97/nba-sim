"""Stint extraction and margin-conditioned rotation helpers."""

from __future__ import annotations

from projections.rotations import RotationModel, expected_abs_margin_from_strength
from ingest.stints import clock_to_seconds, margin_bucket


def test_clock_to_seconds():
    assert abs(clock_to_seconds("PT11M27.00S") - (11 * 60 + 27)) < 0.01
    assert clock_to_seconds("PT00M00.00S") == 0.0


def test_margin_bucket():
    assert margin_bucket(3) == "close"
    assert margin_bucket(10) == "moderate"
    assert margin_bucket(-20) == "blowout"


def test_adjust_means_close_shortens_rotation():
    model = RotationModel()
    means = [34.0, 32.0, 30.0, 28.0, 26.0, 20.0, 16.0, 12.0, 8.0, 4.0, 0.0]
    ranks = list(range(11))
    close = model.adjust_means(means, ranks, expected_abs_margin=3.0, config={"minutes": {}})
    blow = model.adjust_means(means, ranks, expected_abs_margin=20.0, config={"minutes": {}})
    # Stars get relatively more in close games than in blowouts.
    assert close[0] / close[7] > blow[0] / blow[7]
    # Bench (rank 7+) gets more relative share in blowouts.
    assert blow[7] > close[7]


def test_expected_abs_margin_from_strength():
    # Large net gap → larger expected margin.
    wide = expected_abs_margin_from_strength(118, 108, 108, 118)
    tight = expected_abs_margin_from_strength(112, 112, 111, 111)
    assert wide > tight
