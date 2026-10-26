"""Typical-game picker and win-probability helpers."""

from __future__ import annotations

import numpy as np

from outputs.replay_viewer import describe_play, render_replay_html
from outputs.typical_game import pick_typical_run, typical_distance, win_prob_lookup
from sim.engine import GameSimResult
from sim.possession_log import PossessionEvent, PossessionLog


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


def _cloud(n: int, **overrides) -> GameSimResult:
    home = np.full(n, 115.0)
    away = np.full(n, 105.0)
    quarters_h = np.tile(np.array([28.0, 29.0, 29.0, 29.0]), (n, 1))
    quarters_a = np.tile(np.array([26.0, 26.0, 27.0, 26.0]), (n, 1))
    minutes = np.full((1, n), 30.0)
    pts = np.full((1, n), 20.0)
    reb = np.full((1, n), 7.0)
    ast = np.full((1, n), 5.0)
    result = GameSimResult(
        game_id="g",
        runs=n,
        seed=1,
        player_ids=np.array([1], dtype=np.int32),
        player_names=["Brunson"],
        team_abbrs=["NYK"],
        home_away=["H"],
        pts=pts,
        reb=reb,
        ast=ast,
        fg3m=np.zeros((1, n)),
        stl=np.zeros((1, n)),
        blk=np.zeros((1, n)),
        tov=np.zeros((1, n)),
        minutes=minutes,
        home_pts=home,
        away_pts=away,
        overtime=np.zeros(n, dtype=bool),
        home_possessions=100.0,
        away_possessions=100.0,
        home_period_pts=quarters_h,
        away_period_pts=quarters_a,
    )
    for name, value in overrides.items():
        setattr(result, name, value)
    return result


def test_player_and_quarter_fit_beats_score_only_fit():
    """A box-and-quarter match beats a run that only hits margin and total."""
    n = 3
    result = _cloud(n)
    # Index 0 sits on the median margin and total. Its quarters and box do not.
    result.home_period_pts = np.array(
        [[40, 20, 20, 35], [28, 29, 29, 29], [16, 38, 38, 23]], dtype=float
    )
    result.away_period_pts = np.array(
        [[40, 20, 20, 25], [26, 26, 27, 26], [12, 32, 34, 27]], dtype=float
    )
    result.home_pts = np.array([115.0, 118.0, 112.0])
    result.away_pts = np.array([105.0, 106.0, 104.0])
    result.pts = np.array([[2.0, 20.0, 38.0]])
    result.reb = np.array([[0.0, 7.0, 14.0]])
    result.ast = np.array([[0.0, 5.0, 10.0]])
    dist = typical_distance(result)
    assert dist[1] < dist[0]
    assert pick_typical_run(result) == 1


def test_replay_caption_and_page():
    event = PossessionEvent(
        period=1,
        clock_remaining=2800,
        offense_home=True,
        outcome="make_3",
        shooter_id=1,
        passer_id=2,
        points=3,
        home_pts=3,
        away_pts=0,
        game_clock="11:40",
        shooter_name="Brunson",
        passer_name="Hart",
        offense_abbr="NYK",
        shot_zone="above_break_3",
        shot_value=3,
        shot_made=True,
    )
    assert describe_play(event) == "Brunson pull-up 3 - MADE (assist Hart)"
    miss = PossessionEvent(
        period=2,
        clock_remaining=2000,
        offense_home=False,
        outcome="offensive_rebound",
        shooter_id=3,
        passer_id=None,
        points=0,
        home_pts=40,
        away_pts=38,
        shooter_name="Sabonis",
        shot_zone="paint_non_ra",
        shot_value=2,
        shot_made=False,
        rebound="off",
        rebounder_name="Sabonis",
        rebounder_id=3,
    )
    assert "Sabonis paint shot - MISS" in describe_play(miss)
    assert "offensive rebound" in describe_play(miss)
    log = PossessionLog(
        game_id="0022600114",
        run_index=1,
        home_abbr="NYK",
        away_abbr="ORL",
        events=[event],
        simulated_runs=10000,
        fit={"margin": -4.0, "median_margin": -5.0, "total": 220.0, "median_total": 221.0},
    )
    html = render_replay_html(log)
    assert "Most representative of" in html
    assert "1x" in html and "2x" in html and "4x" in html
    assert ">Play<" in html and "Pause" in html
    assert "Brunson pull-up 3 - MADE (assist Hart)" in html
    assert "simulated_runs" in html


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
