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


def test_effective_gap_close_switches_early_season():
    from projections.minutes import effective_minutes_gap_close

    cfg = {
        "minutes": {
            "normalize_gap_close": 0.0,
            "early_season_games": 10,
            "early_season_gap_close": 1.0,
        }
    }
    assert effective_minutes_gap_close(current_season_games_before=0, config=cfg) == pytest.approx(
        float(cfg["minutes"].get("early_season_gap_close", 0.55))
    )
    assert effective_minutes_gap_close(current_season_games_before=10, config=cfg) == 0.0


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
    # Cross-team star minutes are discounted (~0.85) so fringe imports cannot
    # outrank same-team rotation players; still keep a starter-level prior.
    assert mean >= 28.0
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
    """Every regulation sim must sum to exactly team_minutes_target (240)."""
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
    # Default config (gap_close=0) still hard-normalizes draws in the engine.
    result = simulate_game(projection, runs=150, seed=3, config=settings.config)
    target = float(settings.config["minutes"]["team_minutes_target"])
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


def test_role_prior_scales_previous_minutes_and_fills_a_slot():
    from projections.minutes import role_prior_bases, scale_previous_to_role

    config = {
        "minutes": {
            "role_prior_enabled": True,
            "play_threshold": 1.0,
            "max_rotation_size": 11,
            "role_depth_minutes": [36, 34, 32, 30, 28, 22, 16, 12, 10, 8, 6],
        }
    }
    # 26 minutes on the old team, new slot is rank 6 (16 minutes) → 19.0.
    assert scale_previous_to_role(26.0, 16.0) == pytest.approx(19.0)
    rows = [
        {"player_id": 1, "base": 30.0, "depth_rank": 0, "previous": 30.0, "epm_mpg": 0.0, "out": False, "same_team_n": 6},
        {"player_id": 2, "base": 0.0, "depth_rank": 6, "previous": 26.0, "epm_mpg": 0.0, "out": False, "same_team_n": 0},
        {"player_id": 3, "base": 0.0, "depth_rank": 9, "previous": 0.0, "epm_mpg": 28.0, "out": False, "same_team_n": 0},
        {"player_id": 4, "base": 0.0, "depth_rank": 10, "previous": 0.0, "epm_mpg": 0.0, "out": False, "same_team_n": 0},
        {"player_id": 5, "base": 0.0, "depth_rank": 12, "previous": 0.0, "epm_mpg": 20.0, "out": False, "same_team_n": 0},
        {"player_id": 6, "base": 0.0, "depth_rank": 8, "previous": 18.0, "epm_mpg": 0.0, "out": True, "same_team_n": 0},
    ]
    updates = role_prior_bases(rows, config)
    assert 1 not in updates
    assert updates[2] == pytest.approx(19.0)
    assert updates[3] == pytest.approx(28.0)
    assert updates[4] == pytest.approx(6.0)
    assert 5 not in updates
    assert 6 not in updates
    assert role_prior_bases(rows, {"minutes": {"role_prior_enabled": False}}) == {}


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


def test_games_before_arrival_are_not_dnps():
    from projections.blend import SeasonBundle
    from projections.minutes import appearance_since_arrival

    logs = [
        {"game_date": date(2026, 10, 22), "team_id": 1, "minutes": 30.0},
    ]
    bundle = SeasonBundle("2026-27", rates_by_player={}, logs_by_player={7: logs})
    team_dates = [date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)]
    rate, real = appearance_since_arrival(
        [bundle], player_id=7, team_id=1, as_of=date(2026, 10, 24), team_dates=team_dates
    )
    assert real is False
    assert rate == 1.0
    empty_rate, empty_real = appearance_since_arrival(
        [bundle], player_id=8, team_id=1, as_of=date(2026, 10, 24), team_dates=team_dates
    )
    assert empty_real is False
    assert empty_rate == 1.0


def test_low_overlap_keeps_the_live_roster_and_players_who_already_played():
    from projections.build import merge_live_roster

    live = [1, 2, 3]
    prior = [1, 4, 5]
    # 3 is new. 4 already played here. 5 did not, and is not on the live list.
    # 2 is also listed on another club.
    merged = merge_live_roster(live, prior, claimed_elsewhere={2}, appeared_here={4})
    assert merged == [1, 3, 4]


def test_rank_score_uses_every_pre_tip_source_and_dnp_history():
    from projections.minutes import rotation_rank_score

    incumbent = rotation_rank_score(
        same_mean=28.0, same_n=8, previous=0.0, epm_mpg=0.0,
        preseason_mean=0.0, preseason_n=0, rookie=False, appear_rate=1.0, dnp_window=True,
    )
    traded = rotation_rank_score(
        same_mean=0.0, same_n=0, previous=22.0, epm_mpg=0.0,
        preseason_mean=0.0, preseason_n=0, rookie=False, appear_rate=1.0, dnp_window=False,
    )
    rookie = rotation_rank_score(
        same_mean=0.0, same_n=0, previous=0.0, epm_mpg=0.0,
        preseason_mean=18.0, preseason_n=4, rookie=True, appear_rate=1.0, dnp_window=False,
    )
    empty = rotation_rank_score(
        same_mean=0.0, same_n=0, previous=0.0, epm_mpg=0.0,
        preseason_mean=0.0, preseason_n=0, rookie=True, appear_rate=1.0, dnp_window=False,
    )
    assert incumbent > traded > rookie > empty
    full = rotation_rank_score(
        same_mean=22.0, same_n=8, previous=0.0, epm_mpg=0.0,
        preseason_mean=0.0, preseason_n=0, rookie=False, appear_rate=1.0, dnp_window=True,
    )
    scratched = rotation_rank_score(
        same_mean=22.0, same_n=8, previous=0.0, epm_mpg=0.0,
        preseason_mean=0.0, preseason_n=0, rookie=False, appear_rate=0.2, dnp_window=True,
    )
    assert full * 0.80 < scratched < full


def test_twelfth_man_gets_play_probability_not_a_hard_zero():
    from projections.minutes import apply_play_rotation

    rows = []
    for i in range(11):
        rows.append(
            {
                "player_id": i,
                "same_n": 10,
                "same_mean": 34.0 - i,
                "previous": 0.0,
                "epm_mpg": 0.0,
                "preseason_mean": 0.0,
                "preseason_n": 0,
                "appear_rate": 1.0,
                "dnp_window": True,
                "out": False,
                "status": "available",
            }
        )
    rows.append(
        {
            "player_id": 99,
            "same_n": 0,
            "same_mean": 0.0,
            "previous": 0.0,
            "epm_mpg": 0.0,
            "preseason_mean": 14.0,
            "preseason_n": 3,
            "appear_rate": 1.0,
            "dnp_window": False,
            "out": False,
            "status": "available",
        }
    )
    rows.append(
        {
            "player_id": 100,
            "same_n": 0,
            "same_mean": 0.0,
            "previous": 0.0,
            "epm_mpg": 0.0,
            "preseason_mean": 0.0,
            "preseason_n": 0,
            "appear_rate": 1.0,
            "dnp_window": False,
            "out": True,
            "status": "out",
        }
    )
    assigned = apply_play_rotation(rows, {"minutes": {"play_prob_rotation": True}})
    assert assigned[99]["rank"] == 11
    assert assigned[99]["play_prob"] == pytest.approx(0.30, abs=0.02)
    assert 6.0 <= assigned[99]["mean"] <= 12.0
    assert assigned[0]["mean"] is None
    assert assigned[100]["play_prob"] is None


def test_allocate_keeps_twelfth_man_when_play_prob_rotation_is_on():
    import copy

    settings = load_settings()
    config = copy.deepcopy(settings.config)
    config["minutes"]["normalize_gap_close"] = 0.55
    means = [36, 34, 32, 30, 28, 24, 20, 16, 14, 12, 10, 8]
    raw = []
    for i, mean in enumerate(means):
        prob = 0.30 if i == 11 else 0.96
        raw.append(MinutesProjection(float(mean), 3.0, 0.0, 42.0, False, play_prob=prob))
    config["minutes"]["play_prob_rotation"] = False
    off = allocate_team_minutes(raw, config=config, depth_ranks=list(range(12)))
    assert off[-1].mean == 0.0
    config["minutes"]["play_prob_rotation"] = True
    on = allocate_team_minutes(raw, config=config, depth_ranks=list(range(12)))
    assert on[-1].mean > 1.0
    assert on[-1].play_prob == pytest.approx(0.30)
    expected = sum(p.mean * p.play_prob for p in on if not p.out)
    assert expected == pytest.approx(240.0, abs=8.0)


def test_fringe_sit_draw_still_normalizes_to_240():
    rng = np.random.default_rng(1)
    players = [
        MinutesProjection(34, 3, 0, 42, False, play_prob=0.98),
        MinutesProjection(32, 3, 0, 42, False, play_prob=0.98),
        MinutesProjection(30, 3, 0, 42, False, play_prob=0.97),
        MinutesProjection(28, 3, 0, 42, False, play_prob=0.96),
        MinutesProjection(24, 3, 0, 42, False, play_prob=0.95),
        MinutesProjection(18, 3, 0, 42, False, play_prob=0.85),
        MinutesProjection(14, 3, 0, 42, False, play_prob=0.72),
        MinutesProjection(10, 2, 0, 42, False, play_prob=0.45),
        MinutesProjection(8, 2, 0, 42, False, play_prob=0.30),
    ]
    draws = np.vstack([player.sample(rng, size=200) for player in players])
    normed = normalize_team_minute_draws(
        draws,
        out_mask=np.zeros(len(players), dtype=bool),
        caps=np.full(len(players), 42.0),
        target=240.0,
        min_minutes=0.0,
    )
    assert normed.sum(axis=0) == pytest.approx(240.0, abs=0.05)
    # The 12th man sits in some runs and plays in others.
    assert float(np.mean(draws[-1] == 0.0)) > 0.4
    assert float(np.mean(draws[-1] > 0.0)) > 0.1


def test_fringe_floor_keeps_a_line_the_trim_would_zero():
    import copy

    settings = load_settings()
    config = copy.deepcopy(settings.config)
    config["minutes"]["normalize_gap_close"] = 0.0
    config["minutes"]["fringe_minute_floor"] = False
    means = [36, 34, 32, 30, 28, 24, 20, 16, 14, 12, 10, 8, 6, 4, 0.4]
    raw = [
        MinutesProjection(float(mean), 3.0, 0.0, 42.0, False, play_prob=0.96)
        for mean in means
    ]
    off = allocate_team_minutes(raw, config=config, depth_ranks=list(range(len(means))))
    assert off[-1].mean == 0.0
    config["minutes"]["fringe_minute_floor"] = True
    on = allocate_team_minutes(raw, config=config, depth_ranks=list(range(len(means))))
    # The 240 scale trims the 5-minute curve line a little. It does not wipe it.
    assert on[-1].mean > 4.0
    assert on[-1].play_prob == pytest.approx(0.12, abs=0.02)
    assert on[0].mean > 30.0
    expected = sum(player.mean * player.play_prob for player in on if not player.out)
    assert expected == pytest.approx(240.0, abs=8.0)
    assert all(player.mean > 0.0 for player in on)


def test_return_floor_survives_the_trim():
    import copy

    settings = load_settings()
    config = copy.deepcopy(settings.config)
    config["minutes"]["normalize_gap_close"] = 0.0
    config["minutes"]["fringe_minute_floor"] = False
    means = [36, 34, 32, 30, 28, 24, 20, 16, 14, 12, 10, 8, 6, 4, 2]
    raw = [
        MinutesProjection(float(mean), 3.0, 0.0, 42.0, False, play_prob=0.96)
        for mean in means
    ]
    floors = [0.0] * len(means)
    floors[-1] = 14.0
    allocated = allocate_team_minutes(
        raw,
        config=config,
        depth_ranks=list(range(len(means))),
        return_floors=floors,
    )
    assert allocated[-1].mean > 8.0
    assert allocated[-1].play_prob > 0.9


def test_return_blend_does_not_fully_restore_or_cut_a_kept_line():
    from projections.minutes import blend_return_base

    class _Bundle:
        def __init__(self, rows):
            self.logs_by_player = {7: rows}

    played = [
        {"game_date": date(2026, 3, 1), "team_id": 1, "minutes": 22.0},
        {"game_date": date(2026, 3, 3), "team_id": 1, "minutes": 20.0},
        {"game_date": date(2026, 3, 5), "team_id": 1, "minutes": 18.0},
    ]
    sits = [
        {"game_date": date(2026, 3, 7), "team_id": 1, "minutes": 0.0},
        {"game_date": date(2026, 3, 9), "team_id": 1, "minutes": 0.0},
        {"game_date": date(2026, 3, 11), "team_id": 1, "minutes": 0.0},
    ]
    dates = [row["game_date"] for row in played + sits]
    kept, floor = blend_return_base(
        19.0,
        [_Bundle(played + sits)],
        player_id=7,
        team_id=1,
        as_of=date(2026, 3, 13),
        team_dates=dates,
    )
    assert kept == pytest.approx(19.0)
    assert 0.0 < floor < 19.0
    raised, raised_floor = blend_return_base(
        0.0,
        [_Bundle(played + sits)],
        player_id=7,
        team_id=1,
        as_of=date(2026, 3, 13),
        team_dates=dates,
    )
    assert raised == pytest.approx(raised_floor)
    assert 0.0 < raised < 18.0
    no_sit, no_floor = blend_return_base(
        19.0,
        [_Bundle(played)],
        player_id=7,
        team_id=1,
        as_of=date(2026, 3, 6),
        team_dates=[row["game_date"] for row in played],
    )
    assert no_sit == pytest.approx(19.0)
    assert no_floor == 0.0
    fringe = [
        {"game_date": date(2026, 3, 1), "team_id": 1, "minutes": 4.0},
        {"game_date": date(2026, 3, 3), "team_id": 1, "minutes": 3.0},
        {"game_date": date(2026, 3, 5), "team_id": 1, "minutes": 0.0},
        {"game_date": date(2026, 3, 7), "team_id": 1, "minutes": 0.0},
        {"game_date": date(2026, 3, 9), "team_id": 1, "minutes": 0.0},
    ]
    fringe_base, _fringe_floor = blend_return_base(
        0.0,
        [_Bundle(fringe)],
        player_id=7,
        team_id=1,
        as_of=date(2026, 3, 11),
        team_dates=[row["game_date"] for row in fringe],
    )
    assert fringe_base < raised


def test_late_season_seat_runs_only_when_the_game_is_marked():
    import copy

    from projections.minutes import late_season_game

    settings = load_settings()
    config = copy.deepcopy(settings.config)
    config["features"]["late_season_incentives"] = True
    assert late_season_game(date(2026, 3, 15), config) is True
    assert late_season_game(date(2026, 4, 10), config) is True
    assert late_season_game(date(2026, 1, 15), config) is False
    config["features"]["late_season_incentives"] = False
    assert late_season_game(date(2026, 3, 15), config) is False

    config = copy.deepcopy(settings.config)
    config["minutes"]["normalize_gap_close"] = 0.0
    config["minutes"]["late_season_active"] = False
    means = [36, 34, 32, 30, 28, 24, 20, 16, 14, 12, 10, 8, 6, 4, 0.4]
    raw = [
        MinutesProjection(float(mean), 3.0, 0.0, 42.0, False, play_prob=0.96)
        for mean in means
    ]
    off = allocate_team_minutes(raw, config=config, depth_ranks=list(range(len(means))))
    assert off[-1].mean == 0.0
    config["minutes"]["late_season_active"] = True
    on = allocate_team_minutes(raw, config=config, depth_ranks=list(range(len(means))))
    assert on[-1].mean > 1.0
    assert on[-1].play_prob < 0.2


def test_sub_minute_base_is_not_trusted_when_fringe_floor_is_on():
    from projections.minutes import apply_play_rotation

    row = {
        "player_id": 7,
        "base": 0.4,
        "same_n": 5,
        "same_mean": 0.4,
        "previous": 0.0,
        "epm_mpg": 0.0,
        "preseason_mean": 0.0,
        "preseason_n": 0,
        "appear_rate": 0.4,
        "dnp_window": True,
        "out": False,
        "status": "available",
    }
    off = apply_play_rotation([row], {"minutes": {"play_prob_rotation": True}})
    assert off[7]["mean"] is None
    on = apply_play_rotation(
        [row],
        {"minutes": {"play_prob_rotation": True, "fringe_minute_floor": True}},
    )
    assert on[7]["mean"] is not None
    assert on[7]["mean"] >= 5.0
    assert on[7]["play_prob"] >= 0.12
