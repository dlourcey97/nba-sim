"""Early-season league pace / efficiency environment helpers."""

from __future__ import annotations

from datetime import date

from projections.context import (
    apply_league_efficiency_scale,
    blended_team_pace_map,
    league_environment_scales,
)
from projections.rates import RateVector


def test_apply_league_efficiency_scale_moves_fg_and_ft():
    rates = RateVector(restricted_area_fg_pct=0.60, ft_rate=0.20)
    up = apply_league_efficiency_scale(rates, efficiency_scale=1.05)
    assert up.restricted_area_fg_pct > rates.restricted_area_fg_pct
    assert up.ft_rate > rates.ft_rate
    same = apply_league_efficiency_scale(rates, efficiency_scale=1.0)
    assert same.restricted_area_fg_pct == rates.restricted_area_fg_pct


def test_blended_team_pace_prefers_prior_with_zero_games(settings):
    from nba_sim.storage import store_rows

    # Empty current season results → pure prior.
    store_rows(
        settings,
        "team_game_results",
        "2026-27",
        [],
        allow_historical=True,
    )
    prior = {1610612738: 98.0, 1610612739: 102.0}
    out = blended_team_pace_map(
        settings,
        season="2026-27",
        as_of=date(2026, 10, 20),
        prior_season="2025-26",
        prior_pace=prior,
        half_life_games=10.0,
        team_ids=list(prior.keys()),
    )
    assert out[1610612738] == 98.0
    assert out[1610612739] == 102.0


def test_league_environment_scales_no_prior_is_identity(settings):
    pace_s, eff_s = league_environment_scales(
        settings,
        season="2026-27",
        as_of=date(2026, 10, 25),
        prior_season=None,
    )
    assert pace_s == 1.0 and eff_s == 1.0
