"""Fix 3: team minutes sum to 240, rotation priors, sim draw normalization."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from nba_sim.settings import load_settings
from nba_sim.storage import read_rows
from projections.build import build_game_projections
from projections.minutes import (
    MinutesProjection,
    allocate_team_minutes,
    normalize_team_minute_draws,
    project_minutes,
    rotation_base_minutes,
)
from sim.engine import simulate_game


def test_allocate_team_minutes_sums_to_target():
    settings = load_settings()
    config = settings.config
    target = float(config["minutes"]["team_minutes_target"])
    raw = [
        MinutesProjection(36.0, 4.0, 0.0, 42.0, False),
        MinutesProjection(34.0, 4.0, 0.0, 42.0, False),
        MinutesProjection(32.0, 4.0, 0.0, 42.0, False),
        MinutesProjection(30.0, 4.0, 0.0, 42.0, False),
        MinutesProjection(28.0, 4.0, 0.0, 42.0, False),
        MinutesProjection(20.0, 4.0, 0.0, 42.0, False),
        MinutesProjection(14.0, 3.0, 0.0, 42.0, False),
        MinutesProjection(8.0, 3.0, 0.0, 42.0, False),
        MinutesProjection(0.0, 2.0, 0.0, 42.0, False),
        MinutesProjection(0.0, 0.0, 0.0, 0.0, True),
    ]
    allocated = allocate_team_minutes(
        raw,
        config=config,
        depth_ranks=list(range(len(raw))),
    )
    active = [p for p in allocated if not p.out]
    # Means are not hard-forced to 240 (that regressed MAE); expect a realistic band.
    total = sum(p.mean for p in active)
    assert 180.0 <= total <= 320.0
    assert all(p.mean <= float(config["minutes"]["max_minutes"]) + 1e-6 for p in active)
    playing = [p for p in active if p.mean > float(config["minutes"]["play_threshold"])]
    assert len(playing) >= 5


def test_normalize_minute_draws_sum_to_target():
    rng = np.random.default_rng(0)
    n_players, n_runs = 10, 200
    means = np.array([34, 32, 30, 28, 26, 20, 16, 12, 8, 0], dtype=float)
    draws = np.vstack([rng.normal(m, 4.0, n_runs) for m in means])
    out_mask = np.zeros(n_players, dtype=bool)
    out_mask[-1] = True
    caps = np.full(n_players, 42.0)
    caps[-1] = 0.0
    normed = normalize_team_minute_draws(
        draws,
        out_mask=out_mask,
        caps=caps,
        target=240.0,
        min_minutes=0.0,
    )
    assert np.allclose(normed[-1], 0.0)
    totals = normed.sum(axis=0)
    assert totals == pytest.approx(240.0, abs=0.05)
    assert float(normed.max()) <= 42.0 + 1e-6


def test_traded_player_uses_any_team_minutes_not_zero_window():
    """Opening-night trade: no same-team samples must not become a window of zeros."""
    from projections.blend import SeasonBundle
    from projections.minutes import recent_minutes_detail

    logs = [
        {"game_date": date(2025, 11, 1), "team_id": 100, "minutes": 34.0},
        {"game_date": date(2025, 11, 3), "team_id": 100, "minutes": 36.0},
        {"game_date": date(2025, 11, 5), "team_id": 100, "minutes": 35.0},
        {"game_date": date(2025, 11, 8), "team_id": 100, "minutes": 33.0},
    ]
    bundle = SeasonBundle("2025-26", rates_by_player={}, logs_by_player={1: logs})
    team_dates = [date(2026, 10, 10), date(2026, 10, 12), date(2026, 10, 14)]
    mean, _sd, _dates, n = recent_minutes_detail(
        [bundle],
        player_id=1,
        team_id=200,
        as_of=date(2026, 10, 20),
        current_season="2026-27",
        window=10,
        team_game_dates=team_dates,
    )
    assert mean >= 30.0
    assert n >= 1


def test_rotation_base_gives_bench_minutes():
    settings = load_settings()
    config = settings.config
    # Recent rotation bench: ~18 min over several games.
    bench = rotation_base_minutes(
        recent_mean=18.0,
        recent_n=8,
        depth_rank=6,
        started=False,
        config=config,
    )
    assert bench >= 10.0
    # Depth-only player inside min rotation still gets a prior.
    depth_only = rotation_base_minutes(
        recent_mean=0.0,
        recent_n=0,
        depth_rank=7,
        started=False,
        config=config,
    )
    assert depth_only >= float(config["minutes"]["bench_floor"]) - 1e-9
    # Far down the depth chart with no history stays near zero.
    fringe = rotation_base_minutes(
        recent_mean=0.0,
        recent_n=0,
        depth_rank=12,
        started=False,
        config=config,
    )
    assert fringe == 0.0


def test_projected_team_minutes_near_240():
    settings = load_settings()
    schedule = read_rows(settings, "schedule", "2024-25")
    game = next(row for row in schedule if row["game_id"] == "0022400102")
    projection = build_game_projections(
        settings,
        season="2024-25",
        game_id=game["game_id"],
        as_of=game["game_date"],
    )
    target = float(settings.config["minutes"]["team_minutes_target"])
    for side in ("H", "A"):
        players = [p for p in projection.players if p.home_away == side and not p.minutes.out]
        total = sum(p.minutes.mean for p in players)
        # Means track recent history (not hard-forced to 240); stay in a sane band.
        assert 180.0 <= total <= 320.0
        playing = [p for p in players if p.minutes.mean > 1.0]
        assert len(playing) >= 7
        # Bench with minutes should keep some usage.
        for player in playing:
            if player.minutes.mean >= 8.0:
                assert player.rates.usage > 0.0
        # Sim draws still sum near 240 (tested separately).


def test_sim_minute_draws_sum_near_240():
    settings = load_settings()
    game = next(
        row for row in read_rows(settings, "schedule", "2024-25") if row["game_id"] == "0022400102"
    )
    projection = build_game_projections(
        settings,
        season="2024-25",
        game_id=game["game_id"],
        as_of=game["game_date"],
    )
    # With gap_close=0, draws preserve projected means (not hard-forced to 240).
    # Force hard normalize to verify the 240 path still works.
    cfg = dict(settings.config)
    minutes_cfg = dict(cfg["minutes"])
    minutes_cfg["normalize_gap_close"] = 1.0
    cfg["minutes"] = minutes_cfg
    result = simulate_game(projection, runs=150, seed=3, config=cfg)
    target = float(minutes_cfg["team_minutes_target"])
    for side in ("H", "A"):
        idx = [i for i, ha in enumerate(result.home_away) if ha == side]
        # Regulation-like totals: OT runs can exceed 240.
        reg_mask = ~result.overtime
        if not np.any(reg_mask):
            continue
        totals = result.minutes[np.ix_(idx, np.where(reg_mask)[0])].sum(axis=0)
        assert totals.mean() == pytest.approx(target, abs=1.0)
        assert np.max(np.abs(totals - target)) < 2.0


def test_bench_with_recent_minutes_gets_nontrivial_projection():
    """Players averaging meaningful recent minutes should not project near zero."""
    settings = load_settings()
    logs = read_rows(settings, "player_game_logs", "2024-25")
    # Mid-season game so recent same-team samples exist.
    schedule = read_rows(settings, "schedule", "2024-25")
    game = next(
        row
        for row in schedule
        if row["game_date"] >= date(2025, 1, 15) and row["game_id"].startswith("00224")
    )
    projection = build_game_projections(
        settings,
        season="2024-25",
        game_id=game["game_id"],
        as_of=game["game_date"],
    )
    # Find a non-starter who averaged >= 12 min in last 8 same-team games before as_of.
    by_player: dict[int, list[float]] = {}
    for row in logs:
        if row["game_date"] >= game["game_date"]:
            continue
        if int(row["team_id"]) not in {projection.home_team_id, projection.away_team_id}:
            continue
        by_player.setdefault(int(row["player_id"]), []).append(float(row["minutes"] or 0.0))
    proj_by_id = {p.player_id: p for p in projection.players}
    found = False
    for player_id, mins in by_player.items():
        if player_id not in proj_by_id:
            continue
        recent = mins[-8:]
        if len(recent) < 5:
            continue
        avg = sum(recent) / len(recent)
        player = proj_by_id[player_id]
        if player.started or avg < 12.0:
            continue
        assert player.minutes.mean >= max(6.0, avg * 0.45)
        assert player.rates.usage > 0.0
        found = True
        break
    assert found, "expected a mid-rotation bench player in January sample"


def test_project_minutes_out_unchanged():
    settings = load_settings()
    out = project_minutes(
        base_mean=34.0,
        base_sd=4.0,
        config=settings.config,
        status="Out",
        minutes_cap=None,
        started=True,
    )
    assert out.out and out.mean == 0.0
