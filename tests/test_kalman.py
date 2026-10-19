"""Kalman HCA helpers."""

from __future__ import annotations

from projections.kalman import rest_hca_points, rest_fg_adjustment


def test_b2b_hurts_more_than_rested():
    cfg = {"context": {}}
    both_b2b = rest_hca_points(0, 0, config=cfg)
    home_rested = rest_hca_points(3, 0, config=cfg)
    assert home_rested > both_b2b


def test_rest_fg_sign_flips_for_away():
    cfg = {"context": {"hca_points_to_fg": 0.004}}
    home = rest_fg_adjustment(3, 0, home_away="H", config=cfg)
    away = rest_fg_adjustment(3, 0, home_away="A", config=cfg)
    assert home > 0
    assert abs(home + away) < 1e-12
