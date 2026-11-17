"""Isotonic prop calibration."""

from outputs.calibration import fit_isotonic, judge_quality, reliability


def test_isotonic_removes_a_reversal():
    pairs = [(0.2, 0.4), (0.4, 0.3), (0.6, 0.7), (0.8, 0.75)]
    xs, ys = fit_isotonic(pairs)
    assert xs == tuple(sorted(xs))
    assert ys == tuple(sorted(ys))
    assert ys[0] >= 0.3


def test_holdout_quality_rejects_a_map_that_gets_worse():
    pairs = [(0.2, 1.0), (0.8, 0.0)]
    xs, ys = fit_isotonic([(0.2, 0.0), (0.8, 1.0)])
    scored = reliability(pairs, xs, ys)
    assert judge_quality(scored) == "unusable"


def test_a_flat_map_on_a_large_holdout_can_be_strong():
    pairs = [(0.55, 1.0), (0.55, 0.0)] * 120
    xs, ys = fit_isotonic(pairs)
    scored = reliability(pairs, xs, ys)
    assert scored["n"] == 240
    assert judge_quality(scored) == "strong"
