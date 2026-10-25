"""Synergy play-type transform, regression, leakage season selection."""

from __future__ import annotations

from ingest.play_types import (
    PLAY_TYPES,
    blend_rates,
    league_baselines,
    load_entity_rates,
    matchup_factors,
    play_type_season_for_projection,
    apply_play_type_factors,
    _finalize_row,
    _merge_raw_row,
)
from projections.rates import RateVector


def test_merge_and_finalize_player_isolation():
    acc: dict = {}
    _merge_raw_row(
        acc,
        {
            "PLAYER_ID": 1,
            "PLAYER_NAME": "Star",
            "TEAM_ID": 10,
            "POSS": 100,
            "POSS_PCT": 0.25,
            "PPP": 1.1,
            "TOV_POSS_PCT": 0.10,
            "FT_POSS_PCT": 0.15,
            "SCORE_POSS_PCT": 0.50,
            "GP": 40,
        },
        entity_kind="player",
        play_type="Isolation",
        side="offense",
        season="2024-25",
        fetched_at="2026-10-25T00:00:00+00:00",
    )
    rows = [_finalize_row(v) for v in acc.values()]
    assert len(rows) == 1
    row = rows[0]
    assert row["entity_id"] == 1
    assert row["play_type"] == "Isolation"
    assert row["possessions"] == 100
    assert abs(row["ppp"] - 1.1) < 1e-9
    assert abs(row["frequency"] - 0.25) < 1e-9


def test_regression_pulls_toward_league_on_tiny_sample():
    rows = [
        {
            "entity_kind": "player",
            "entity_id": 1,
            "play_type": "Isolation",
            "side": "offense",
            "possessions": 5.0,
            "frequency": 0.9,
            "ppp": 2.0,
            "tov_pct": 0.01,
            "ft_pct": 0.01,
            "score_pct": 0.9,
        }
    ]
    league = {
        pt: {
            "ppp": 1.0,
            "tov_pct": 0.12,
            "ft_pct": 0.12,
            "score_pct": 0.45,
            "frequency": 1.0 / len(PLAY_TYPES),
        }
        for pt in PLAY_TYPES
    }
    rates = load_entity_rates(
        rows,
        entity_kind="player",
        entity_id=1,
        side="offense",
        league=league,
        regression_possessions=200.0,
    )
    assert rates is not None
    # 5/(5+200) ≈ 0.024 toward the extreme 2.0 PPP → near 1.0
    assert 0.95 < rates.ppp["Isolation"] < 1.10


def test_matchup_factors_punish_iso_specialist_vs_elite_iso_d():
    from ingest.play_types import PlayTypeRates

    mix = {pt: 0.0 for pt in PLAY_TYPES}
    mix["Isolation"] = 1.0
    player = PlayTypeRates(
        mix=mix,
        ppp={pt: 1.1 for pt in PLAY_TYPES},
        tov_pct={pt: 0.10 for pt in PLAY_TYPES},
        ft_pct={pt: 0.12 for pt in PLAY_TYPES},
        score_pct={pt: 0.5 for pt in PLAY_TYPES},
        possessions={pt: 100.0 for pt in PLAY_TYPES},
    )
    soft_d = PlayTypeRates(
        mix=mix,
        ppp={pt: 1.0 for pt in PLAY_TYPES},
        tov_pct={pt: 0.12 for pt in PLAY_TYPES},
        ft_pct={pt: 0.12 for pt in PLAY_TYPES},
        score_pct={pt: 0.45 for pt in PLAY_TYPES},
        possessions={pt: 1000.0 for pt in PLAY_TYPES},
    )
    # Elite iso D: low PPP allowed
    soft_d.ppp["Isolation"] = 0.75
    league = {pt: {"ppp": 1.0, "tov_pct": 0.12, "ft_pct": 0.12} for pt in PLAY_TYPES}
    fg, tov, ft = matchup_factors(player, soft_d, league, weight=0.35)
    assert fg < 1.0
    assert 0.92 <= fg <= 1.08


def test_blend_weights_prior_when_current_sample_tiny():
    from ingest.play_types import PlayTypeRates

    prior = PlayTypeRates(
        mix={pt: 1.0 / len(PLAY_TYPES) for pt in PLAY_TYPES},
        ppp={pt: 1.2 for pt in PLAY_TYPES},
        tov_pct={pt: 0.1 for pt in PLAY_TYPES},
        ft_pct={pt: 0.1 for pt in PLAY_TYPES},
        score_pct={pt: 0.5 for pt in PLAY_TYPES},
        possessions={pt: 500.0 for pt in PLAY_TYPES},
    )
    current = PlayTypeRates(
        mix={pt: 1.0 / len(PLAY_TYPES) for pt in PLAY_TYPES},
        ppp={pt: 0.5 for pt in PLAY_TYPES},
        tov_pct={pt: 0.2 for pt in PLAY_TYPES},
        ft_pct={pt: 0.2 for pt in PLAY_TYPES},
        score_pct={pt: 0.3 for pt in PLAY_TYPES},
        possessions={pt: 10.0 for pt in PLAY_TYPES},
    )
    blended = blend_rates(
        current, prior, current_poss_total=20.0, half_life_possessions=400.0
    )
    assert blended is not None
    # w = 20/420 ≈ 0.05 → near prior 1.2
    assert blended.ppp["Isolation"] > 1.1


def test_play_type_season_leakage_rule(tmp_path, monkeypatch):
    from nba_sim.settings import Settings

    settings = Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        archive_dir=tmp_path / "archive",
        current_season="2026-27",
        max_bytes=2_000_000_000,
        config={},
    )
    primary, prior, blend = play_type_season_for_projection(settings, season="2025-26")
    assert primary == "2024-25"
    assert prior is None
    assert blend is False
    primary, prior, blend = play_type_season_for_projection(settings, season="2026-27")
    assert primary == "2026-27"
    assert prior == "2025-26"
    assert blend is True


def test_apply_play_type_factors_scales_rates():
    rates = RateVector(tov_rate=0.10, ft_rate=0.10, restricted_area_fg_pct=0.60)
    out = apply_play_type_factors(rates, fg_factor=1.05, tov_factor=1.10, ft_factor=0.95)
    assert out.tov_rate > rates.tov_rate
    assert out.ft_rate < rates.ft_rate
    assert out.restricted_area_fg_pct > rates.restricted_area_fg_pct


def test_league_baselines_possession_weighted():
    rows = [
        {
            "entity_kind": "team",
            "side": "defense",
            "play_type": "Isolation",
            "possessions": 100.0,
            "ppp": 0.8,
            "tov_pct": 0.1,
            "ft_pct": 0.1,
            "score_pct": 0.4,
            "frequency": 0.1,
        },
        {
            "entity_kind": "team",
            "side": "defense",
            "play_type": "Isolation",
            "possessions": 300.0,
            "ppp": 1.2,
            "tov_pct": 0.2,
            "ft_pct": 0.2,
            "score_pct": 0.5,
            "frequency": 0.2,
        },
    ]
    lg = league_baselines(rows, entity_kind="team", side="defense")
    assert abs(lg["Isolation"]["ppp"] - 1.1) < 1e-9
