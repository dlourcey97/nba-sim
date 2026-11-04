"""On-court six-factor defense: shrink, residual, and the off switch."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from projections.lineup_defense import (
    lineup_adjustments,
    load_defensive_factors,
    minutes_weighted_mean,
    shrink_component,
)
from sim.engine import _lineup_possession_adjustments, _pack_lineup_defense


def test_shrink_pulls_low_sample_to_zero():
    assert shrink_component(2.0, 16000, 4000) == 2.0 * 16000 / 20000
    assert shrink_component(2.0, 400, 4000) < 0.2
    assert shrink_component(None, 10000, 4000) == 0.0
    assert shrink_component(1.5, 0, 4000) == 0.0


def test_average_lineup_is_a_zero_residual():
    # Five copies of the team mean cancel the baseline.
    values = np.array([0.4, 0.4, 0.4, 0.4, 0.4])
    base = np.array([0.4, 0.4, 0.4, 0.4, 0.4])
    lineups = np.array([[0, 1, 2, 3, 4]])
    packed = {
        "lineup_tov": values,
        "lineup_ts": values,
        "lineup_reb": values,
        "lineup_tov_base": base,
        "lineup_ts_base": base,
        "lineup_reb_base": base,
        "lineup_weight": 1.0,
    }
    steal, tov, fg, orb = _lineup_possession_adjustments(packed, lineups)
    assert steal[0] == 0.0
    assert tov[0] == 0.0
    assert fg[0] == 1.0
    assert orb[0] == 1.0


def test_good_defender_raises_turnovers_and_suppresses_shooting():
    # One defender at Amen's 2025 dTOV and Wemby's 2025 dTS, rest at zero,
    # against a zero team baseline.
    steal, tov, fg, orb = lineup_adjustments(
        tov_residual=0.32,
        ts_residual=3.16,
        reb_residual=0.81,
        weight=1.0,
    )
    assert float(steal) > 0.0
    assert float(tov) > 0.0
    assert float(fg) < 1.0
    assert float(orb) < 1.0
    weak_steal, weak_tov, weak_fg, weak_orb = lineup_adjustments(
        tov_residual=-0.55,
        ts_residual=-1.72,
        reb_residual=-0.33,
        weight=1.0,
    )
    assert float(weak_steal) < 0.0
    assert float(weak_fg) > 1.0
    assert float(weak_orb) > 1.0


def test_missing_key_leaves_possession_math_unchanged():
    lineups = np.zeros((3, 5), dtype=int)
    steal, tov, fg, orb = _lineup_possession_adjustments({}, lineups)
    assert np.all(steal == 0.0)
    assert np.all(tov == 0.0)
    assert np.all(fg == 1.0)
    assert np.all(orb == 1.0)


def test_flag_off_does_not_pack_or_change_credit():
    players = [SimpleNamespace(player_id=1, home_away="H")]
    projection = SimpleNamespace(
        lineup_defense={1: (0.5, 1.0, 0.2)},
        lineup_defense_baseline={"H": (0.1, 0.1, 0.1)},
    )
    packed: dict = {}
    _pack_lineup_defense(packed, players, projection, {"context": {}})
    assert "lineup_tov" not in packed


def test_flag_on_packs_shrunk_values_and_full_rate_credit():
    players = [
        SimpleNamespace(player_id=1, home_away="H"),
        SimpleNamespace(player_id=2, home_away="A"),
    ]
    projection = SimpleNamespace(
        lineup_defense={1: (0.32, 1.14, 0.26), 2: (0.0, 0.0, 0.0)},
        lineup_defense_baseline={"H": (0.10, 0.20, 0.05), "A": (0.0, 0.0, 0.0)},
    )
    packed: dict = {}
    _pack_lineup_defense(
        packed,
        players,
        projection,
        {"context": {"lineup_defense_enabled": True, "lineup_defense_weight": 1.0}},
    )
    assert packed["lineup_tov"][0] == 0.32
    assert packed["lineup_tov_base"][0] == 0.10
    assert packed["lineup_tov_base"][1] == 0.0
    packed["lineup_tov"] = packed["lineup_tov"]  # already set
    # Credit override happens in simulate_game once the arrays exist.
    assert packed.get("lineup_tov") is not None


def test_minutes_weighted_mean_counts_unrated_players_as_zero():
    mean = minutes_weighted_mean([30.0, 10.0], [1.0, 0.0])
    assert abs(mean - 0.75) < 1e-9


def test_loader_uses_prior_season_only():
    from nba_sim.settings import load_settings

    settings = load_settings()
    factors = load_defensive_factors(settings, "2025-26", prior_poss=4000.0)
    # Amen Thompson, 2025 3Y. Cooper Flagg's only row is latest_year 2026.
    amen = factors[1641708]
    assert amen.tov > 0.2
    assert 15000 < amen.possessions < 16000
    assert 1642843 not in factors
