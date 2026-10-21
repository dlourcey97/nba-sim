"""Typical-game picker and win-probability helpers."""

from __future__ import annotations

import numpy as np

from outputs.typical_game import pick_typical_run, win_prob_lookup
from sim.engine import GameSimResult


def test_pick_typical_run_near_medians():
    n = 100
    home = np.linspace(100, 120, n)
    away = np.linspace(110, 105, n)
    # Force one run exactly at median margin/total-ish.
    home[50] = float(np.median(home))
    away[50] = float(np.median(away))
    result = GameSimResult(
        game_id="g",
        runs=n,
        seed=1,
        player_ids=np.array([1], dtype=np.int32),
        player_names=["x"],
        team_abbrs=["H"],
        home_away=["H"],
        pts=np.zeros((1, n)),
        reb=np.zeros((1, n)),
        ast=np.zeros((1, n)),
        fg3m=np.zeros((1, n)),
        stl=np.zeros((1, n)),
        blk=np.zeros((1, n)),
        tov=np.zeros((1, n)),
        minutes=np.zeros((1, n)),
        home_pts=home,
        away_pts=away,
        overtime=np.zeros(n, dtype=bool),
        home_possessions=100.0,
        away_possessions=100.0,
    )
    idx = pick_typical_run(result)
    assert 0 <= idx < n


def test_win_prob_lookup_respects_margin():
    rng = np.random.default_rng(0)
    margins = np.concatenate([np.full(50, 10.0), np.full(50, -10.0)])
    clocks = np.full(100, 600.0)
    home_won = (margins > 0).astype(float)
    p_lead = win_prob_lookup(
        margins=margins,
        clocks=clocks,
        home_won=home_won,
        query_margin=10.0,
        query_clock=600.0,
    )
    p_trail = win_prob_lookup(
        margins=margins,
        clocks=clocks,
        home_won=home_won,
        query_margin=-10.0,
        query_clock=600.0,
    )
    assert p_lead > 0.8
    assert p_trail < 0.2
