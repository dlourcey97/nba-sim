"""Possession-engine invariants: clock, scores, assists, minutes."""

from __future__ import annotations

import numpy as np
import pytest

from nba_sim.settings import load_settings
from nba_sim.storage import read_rows
from projections.build import build_game_projections
from sim.engine import simulate_game
from sim.possession_log import REGULATION_SECONDS, period_from_clock


def _sample_projection():
    settings = load_settings()
    game = next(
        row
        for row in read_rows(settings, "schedule", "2024-25")
        if row["game_id"] == "0022400102"
    )
    projection = build_game_projections(
        settings,
        season="2024-25",
        game_id=game["game_id"],
        as_of=game["game_date"],
    )
    return settings, projection


def test_period_from_clock_quarters():
    assert period_from_clock(2880) == 1
    assert period_from_clock(2160) == 2
    assert period_from_clock(1440) == 3
    assert period_from_clock(720) == 4
    assert period_from_clock(1) == 4
    assert period_from_clock(0, in_overtime=True) == 5


def test_clock_and_period_scores_present():
    settings, projection = _sample_projection()
    result = simulate_game(projection, runs=50, seed=11, config=settings.config)
    assert result.clock_remaining is not None
    assert result.clock_remaining.shape == (50,)
    assert np.all(result.clock_remaining >= 0)
    assert np.all(result.clock_remaining <= REGULATION_SECONDS)
    assert result.home_period_pts is not None
    assert result.away_period_pts is not None
    assert result.home_period_pts.shape == (50, 4)
    # Period points should sum to regulation score (OT adds after Q4).
    reg_home = result.home_period_pts.sum(axis=1)
    # Allow OT: period sum <= final score.
    assert np.all(reg_home <= result.home_pts + 1e-6)


def test_team_minutes_near_240():
    settings, projection = _sample_projection()
    result = simulate_game(projection, runs=80, seed=3, config=settings.config)
    home = np.array(
        [i for i, side in enumerate(result.home_away) if side == "H"], dtype=int
    )
    away = np.array(
        [i for i, side in enumerate(result.home_away) if side == "A"], dtype=int
    )
    home_tot = result.minutes[home].sum(axis=0)
    away_tot = result.minutes[away].sum(axis=0)
    # Regulation hard-normalized to 240; OT adds 25/period so means can exceed.
    assert 235.0 < float(np.mean(home_tot)) < 255.0
    assert 235.0 < float(np.mean(away_tot)) < 255.0
    reg = ~result.overtime
    if np.any(reg):
        assert float(np.mean(home_tot[reg])) == pytest.approx(240.0, abs=1.0)
        assert float(np.mean(away_tot[reg])) == pytest.approx(240.0, abs=1.0)


def test_scores_match_player_points():
    settings, projection = _sample_projection()
    result = simulate_game(projection, runs=40, seed=5, config=settings.config)
    home = np.array(
        [i for i, side in enumerate(result.home_away) if side == "H"], dtype=int
    )
    away = np.array(
        [i for i, side in enumerate(result.home_away) if side == "A"], dtype=int
    )
    assert np.allclose(result.home_pts, result.pts[home].sum(axis=0), atol=1e-6)
    assert np.allclose(result.away_pts, result.pts[away].sum(axis=0), atol=1e-6)


def test_assists_only_on_makes_via_trace():
    settings, projection = _sample_projection()
    result = simulate_game(
        projection, runs=30, seed=9, config=settings.config, trace_run=0
    )
    assert result.possession_log is not None
    log = result.possession_log
    assert len(log.events) > 50
    for event in log.events:
        if event.passer_id is not None:
            assert event.outcome in {"make_2", "make_3"}
            assert event.points >= 2
        if event.outcome in {"make_2", "make_3", "free_throws", "intentional_foul"}:
            assert event.points >= 0
        if event.outcome == "offensive_rebound":
            assert event.points == 0


def test_trace_reproducible_with_same_seed():
    settings, projection = _sample_projection()
    a = simulate_game(
        projection, runs=25, seed=42, config=settings.config, trace_run=3
    )
    b = simulate_game(
        projection, runs=25, seed=42, config=settings.config, trace_run=3
    )
    assert a.possession_log is not None and b.possession_log is not None
    assert len(a.possession_log.events) == len(b.possession_log.events)
    assert a.possession_log.final_home_pts == b.possession_log.final_home_pts
    assert np.array_equal(a.home_pts, b.home_pts)


def test_trace_fields_do_not_change_the_sim():
    settings, projection = _sample_projection()
    plain = simulate_game(projection, runs=20, seed=7, config=settings.config)
    traced = simulate_game(
        projection, runs=20, seed=7, config=settings.config, trace_run=0
    )
    assert np.array_equal(plain.home_pts, traced.home_pts)
    assert np.array_equal(plain.away_pts, traced.away_pts)
    assert np.array_equal(plain.pts, traced.pts)
    log = traced.possession_log
    assert log is not None
    makes = [e for e in log.events if e.outcome in {"make_2", "make_3"}]
    assert makes
    assert all(
        e.shot_zone and e.shot_made and e.shot_value in {2, 3} and e.game_clock and e.offense_abbr
        for e in makes
    )
    boards = [e for e in log.events if e.rebound in {"off", "def"}]
    assert boards
    assert all(e.shot_made is False and e.shot_zone for e in boards)
    assert sum(e.points for e in log.events) == log.final_home_pts + log.final_away_pts
    assert all(e.period >= 1 and e.home_pts >= 0 and e.away_pts >= 0 for e in log.events)
