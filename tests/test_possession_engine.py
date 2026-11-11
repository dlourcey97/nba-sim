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


def test_rotation_lineup_includes_mid_minute_player():
    """A ~18 MPG player must actually crack the five, not just own a minute draw."""
    from types import SimpleNamespace

    from projections.rotations import RotationModel
    from sim.engine import _lineups_state_grid

    rng = np.random.default_rng(1)
    players = [
        SimpleNamespace(team_id=1, player_id=100 + i, depth_rank=i) for i in range(8)
    ]
    column = np.array([36, 34, 32, 30, 24, 20, 18, 10], dtype=float)
    minutes = np.repeat(column[:, None], 300, axis=1)
    grid = _lineups_state_grid(
        rng,
        np.arange(8),
        minutes,
        players,
        rotation=RotationModel(step_f=True),
        flat=False,
    )
    in_lineup = np.any(grid == 6, axis=-1)
    share = float(np.mean(in_lineup))
    star_share = float(np.mean(np.any(grid == 0, axis=-1)))
    assert share > 0.12
    assert star_share > share


def test_budget_lineup_tracks_star_minutes():
    """A 36-minute player stays near 75% of the floor, and rarely under half that."""
    from types import SimpleNamespace

    from sim.engine import _lineups_state_grid

    rng = np.random.default_rng(2)
    minutes_line = np.array([36, 34, 32, 30, 26, 22, 18, 14, 10, 8], dtype=float)
    players = [
        SimpleNamespace(team_id=1, player_id=100 + i, depth_rank=i)
        for i in range(len(minutes_line))
    ]
    runs = 400
    minutes = np.repeat(minutes_line[:, None], runs, axis=1)
    grid = _lineups_state_grid(
        rng,
        np.arange(len(minutes_line)),
        minutes,
        players,
        flat=True,
        substints=4,
        budget_noise=0.40,
    )
    assert grid.ndim == 5
    # Close bucket only. Count substints on the floor across four quarters.
    chosen = grid[:, :, 0, :, :]  # runs, periods, substints, 5
    on = np.zeros((runs, len(minutes_line)), dtype=float)
    for period in range(4):
        for sub in range(4):
            five = chosen[:, period, sub, :]
            for slot in range(5):
                on[np.arange(runs), five[:, slot]] += 1.0
    share = on / 16.0
    star = share[:, 0]
    bench = share[:, 6]  # 18 minutes
    assert abs(float(star.mean()) - 36.0 / 48.0) < 0.06
    assert float((star < 0.5 * 36.0 / 48.0).mean()) < 0.05
    assert float(bench.mean()) > 0.12


def test_star_dispersion_is_tighter_than_bench():
    from sim.engine import _group_dispersion

    rng = np.random.default_rng(3)
    usage = np.array([0.34, 0.12])
    hot, used = _group_dispersion(
        rng,
        usage,
        4000,
        {
            "star_usage_min": 0.24,
            "player_shoot_sd": 0.32,
            "player_usage_sd": 0.28,
            "star_shoot_sd": 0.14,
            "star_usage_sd": 0.10,
        },
    )
    assert float(hot[0].std()) < float(hot[1].std())
    assert float(used[0].std()) < float(used[1].std())
    assert abs(float(hot[0].mean()) - 1.0) < 0.03
    assert abs(float(hot[1].mean()) - 1.0) < 0.03
