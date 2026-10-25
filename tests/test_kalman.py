"""Kalman HCA helpers."""

from __future__ import annotations

from projections.context import (
    TeamStrength,
    kalman_blend_weight,
    prior_strength_after_absences,
)
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


def test_kalman_blend_weight_scales_with_games():
    assert kalman_blend_weight(0.45, 0, half_life=15.0) == 0.0
    early = kalman_blend_weight(0.45, 2, half_life=15.0)
    mid = kalman_blend_weight(0.45, 15, half_life=15.0)
    assert 0.04 < early < 0.06
    assert abs(mid - 0.225) < 1e-9
    assert kalman_blend_weight(0.45, 100, half_life=0.0) == 0.45


def test_prior_strength_after_absences_hurts_when_stars_out():
    prior = TeamStrength(ortg=118.0, drtg=110.0)
    # Healthy rotation +4 RAPM, available (stars out) 0 → gap 4.
    adj = prior_strength_after_absences(
        prior, healthy_net=4.0, available_net=0.0, weight=1.0
    )
    assert adj is not None
    assert adj.ortg == 116.0
    assert adj.drtg == 112.0


def test_prior_absence_ignores_negative_rapm_gap():
    prior = TeamStrength(ortg=112.0, drtg=116.0)
    # Stars rated negative by RAPM — do not improve the prior by sitting them.
    adj = prior_strength_after_absences(
        prior, healthy_net=-1.0, available_net=0.5, weight=1.0
    )
    assert adj == prior


def test_prior_absence_minutes_penalty():
    prior = TeamStrength(ortg=112.0, drtg=116.0)
    # 72 base minutes out → 72/36 * 3.5 = 7 net → ±3.5 on ORtg/DRtg.
    adj = prior_strength_after_absences(
        prior,
        healthy_net=0.0,
        available_net=0.0,
        weight=0.0,
        out_base_minutes=72.0,
        minutes_net_per_36=3.5,
    )
    assert adj is not None
    assert abs(adj.ortg - 108.5) < 1e-9
    assert abs(adj.drtg - 119.5) < 1e-9


def test_sos_adjust_credits_tough_schedule():
    from projections.context import sos_adjust_game_ratings

    league = TeamStrength(ortg=115.0, drtg=115.0)
    elite = TeamStrength(ortg=120.0, drtg=108.0)  # great O and D
    weak = TeamStrength(ortg=108.0, drtg=120.0)
    # Same raw 110/110 box score:
    vs_elite = sos_adjust_game_ratings(110.0, 110.0, opponent=elite, league=league)
    vs_weak = sos_adjust_game_ratings(110.0, 110.0, opponent=weak, league=league)
    # Tough D → higher adj ORtg; tough O → lower (better) adj DRtg.
    assert vs_elite[0] > vs_weak[0]
    assert vs_elite[1] < vs_weak[1]
    # Net rating vs elite should look better than vs weak for the same box.
    assert (vs_elite[0] - vs_elite[1]) > (vs_weak[0] - vs_weak[1])
