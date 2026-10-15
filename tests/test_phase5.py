"""Phase 5: possession-level simulation engine."""

from __future__ import annotations

import numpy as np
import pytest

from nba_sim.settings import load_settings
from nba_sim.storage import read_rows
from projections.build import build_game_projections
from sim.engine import simulate_game


def test_simulate_game_reproducible_and_shaped():
    settings = load_settings()
    schedule = read_rows(settings, "schedule", "2024-25")
    game = next(row for row in schedule if row["game_id"] == "0022400102")
    projection = build_game_projections(
        settings,
        season="2024-25",
        game_id=game["game_id"],
        as_of=game["game_date"],
    )
    a = simulate_game(projection, runs=200, seed=7, config=settings.config)
    b = simulate_game(projection, runs=200, seed=7, config=settings.config)
    assert a.runs == 200
    assert a.seed == 7
    assert a.pts.shape == (len(projection.players), 200)
    assert a.home_pts.shape == (200,)
    assert np.array_equal(a.home_pts, b.home_pts)
    assert np.array_equal(a.pts, b.pts)
    assert a.home_pts.mean() > 70
    assert a.away_pts.mean() > 70
    assert a.home_pts.std() > 0
    # Out players (zero projected minutes) should stay near zero points.
    for index, player in enumerate(projection.players):
        if player.minutes.out:
            assert a.pts[index].mean() == pytest.approx(0.0)
            assert a.minutes[index].mean() == pytest.approx(0.0)
    # Top minute players should score something on average.
    order = np.argsort([-p.minutes.mean for p in projection.players])
    top = int(order[0])
    assert a.pts[top].mean() > 5
    assert 0.0 <= float(a.overtime.mean()) <= 1.0


def test_simulate_game_seed_changes_output():
    settings = load_settings()
    game = next(row for row in read_rows(settings, "schedule", "2024-25") if row["game_id"] == "0022400102")
    projection = build_game_projections(
        settings,
        season="2024-25",
        game_id=game["game_id"],
        as_of=game["game_date"],
    )
    a = simulate_game(projection, runs=100, seed=1, config=settings.config)
    b = simulate_game(projection, runs=100, seed=2, config=settings.config)
    assert not np.array_equal(a.home_pts, b.home_pts)
