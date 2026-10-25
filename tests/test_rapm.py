"""Ridge RAPM helpers."""

from __future__ import annotations

from projections.rapm import RapmModel
from projections.context import TeamStrength


def test_roster_net_minutes_weighted():
    model = RapmModel(ratings={1: 10.0, 2: -5.0, 3: 0.0})
    net = model.roster_net([(1, 30.0), (2, 30.0), (3, 0.0)])
    assert abs(net - 2.5) < 1e-9


def test_team_strength_splits_net():
    model = RapmModel(ratings={1: 8.0})
    league = TeamStrength(ortg=112.0, drtg=112.0)
    strength = model.team_strength(
        [(1, 36.0)],
        league=league,
        config={
            "context": {
                "rapm_strength_weight": 1.0,
                "rapm_blend_half_life": 0.0,  # disable sample-size shrink for unit test
                "team_strength_half_life": 20.0,
            }
        },
    )
    # net=8 → ORtg +4, DRtg -4 when fully RAPM-weighted
    assert abs(strength.ortg - 116.0) < 1e-6
    assert abs(strength.drtg - 108.0) < 1e-6
