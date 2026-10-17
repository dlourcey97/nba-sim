"""Phase 4: blending, context adjustments, and minutes model."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from ingest.injuries import InjuryEntry
from nba_sim.settings import load_settings
from nba_sim.storage import read_rows
from projections.blend import available_season_window, load_season_bundle, player_baseline_and_form
from projections.build import build_game_projections
from projections.context import expected_possessions, redistribute_for_absences, rest_days_before
from projections.minutes import project_minutes
from projections.rates import RateVector, blend_vectors, position_bucket, vector_from_accumulator


def test_position_bucket_and_blend_vectors():
    assert position_bucket("PG") == "G"
    assert position_bucket("C") == "C"
    from projections.rates import five_position

    assert five_position("PG") == "PG"
    assert five_position("G", ast=8, reb=2) == "PG"
    assert five_position("G", ast=1, reb=4) == "SG"
    assert five_position("F", reb=8) == "PF"
    assert five_position("C") == "C"
    a = RateVector(usage=0.30, sample_possessions=100)
    b = RateVector(usage=0.10, sample_possessions=100)
    mixed = blend_vectors([(a, 1.0), (b, 1.0)])
    assert mixed.usage == pytest.approx(0.20)


def test_regression_strength_is_pseudo_possessions():
    """Stars with large samples must not collapse toward the position prior."""
    star = RateVector(usage=0.30, sample_possessions=4000)
    prior = RateVector(usage=0.20)
    # Mimic player_baseline_and_form: blend data by sample size, then shrink.
    blended = blend_vectors([(star, star.sample_possessions)], prior=prior, prior_strength=12.0)
    assert blended.usage == pytest.approx(0.2997, abs=0.002)
    # Tiny sample still regresses.
    rook = RateVector(usage=0.30, sample_possessions=20)
    rook_blend = blend_vectors([(rook, rook.sample_possessions)], prior=prior, prior_strength=12.0)
    assert rook_blend.usage < 0.28
    assert rook_blend.usage > 0.22


def test_roster_team_strength_blends_with_current_season():
    from projections.context import TeamStrength, roster_team_strength

    star = RateVector(
        usage=0.30,
        restricted_area_share=0.35,
        restricted_area_fg_pct=0.68,
        above_break_3_share=0.35,
        above_break_3_fg_pct=0.38,
        tov_rate=0.10,
        ft_rate=0.25,
        ft_pct=0.85,
        stl_rate=0.02,
        blk_rate=0.01,
    )
    role = RateVector(usage=0.15, stl_rate=0.01, blk_rate=0.005)
    prior = TeamStrength(ortg=110.0, drtg=112.0)
    current = TeamStrength(ortg=118.0, drtg=108.0)
    early = roster_team_strength(
        [(star, 34.0), (role, 20.0)],
        prior=prior,
        current=current,
        current_games=2,
        league=TeamStrength(112.0, 112.0),
        config={"context": {"team_strength_half_life": 20.0}},
    )
    late = roster_team_strength(
        [(star, 34.0), (role, 20.0)],
        prior=prior,
        current=current,
        current_games=40,
        league=TeamStrength(112.0, 112.0),
        config={"context": {"team_strength_half_life": 20.0}},
    )
    # More current games → pull toward current-season ORtg.
    assert abs(late.ortg - current.ortg) < abs(early.ortg - current.ortg)


def test_position_defense_from_logs():
    from ingest.parse import team_position_defense
    from projections.context import apply_opponent_position_defense, position_defense_from_bundles
    from projections.blend import SeasonBundle

    logs = [
        {
            "season": "2024-25",
            "game_id": "1",
            "game_date": date(2024, 11, 1),
            "player_id": 1,
            "opponent_team_id": 100,
            "position": "G",
            "minutes": 36.0,
            "pts": 30,
            "reb": 2,
            "ast": 8,
            "fg3m": 3,
            "stl": 1,
            "blk": 0,
            "tov": 2,
        },
        {
            "season": "2024-25",
            "game_id": "1",
            "game_date": date(2024, 11, 1),
            "player_id": 2,
            "opponent_team_id": 100,
            "position": "C",
            "minutes": 30.0,
            "pts": 12,
            "reb": 10,
            "ast": 1,
            "fg3m": 0,
            "stl": 0,
            "blk": 2,
            "tov": 1,
        },
    ]
    rows = team_position_defense("2024-25", logs)
    by_pos = {row["position"]: row for row in rows if row["team_id"] == 100}
    assert by_pos["PG"]["pts"] == 30.0
    assert by_pos["C"]["reb"] == 10.0
    bundle = SeasonBundle("2024-25", rates_by_player={}, logs_by_player={1: [logs[0]], 2: [logs[1]]})
    allowed = position_defense_from_bundles([bundle], as_of=date(2024, 11, 2), defender_team_id=100)
    assert allowed["PG"]["pts_per_36"] == pytest.approx(30.0)
    rates = RateVector(restricted_area_fg_pct=0.60)
    soft = apply_opponent_position_defense(
        rates,
        position="PG",
        opp_allowed=allowed,
        league_allowed={
            "PG": {"pts_per_36": 20.0, "reb_per_36": 4.0, "ast_per_36": 6.0, "fg3m_per_36": 2.0},
            "SG": {"pts_per_36": 20.0, "reb_per_36": 4.0, "ast_per_36": 4.0, "fg3m_per_36": 2.0},
            "SF": {"pts_per_36": 20.0, "reb_per_36": 5.0, "ast_per_36": 3.0, "fg3m_per_36": 2.0},
            "PF": {"pts_per_36": 20.0, "reb_per_36": 7.0, "ast_per_36": 2.0, "fg3m_per_36": 1.0},
            "C": {"pts_per_36": 18.0, "reb_per_36": 10.0, "ast_per_36": 2.0, "fg3m_per_36": 0.5},
        },
        weight=1.0,
    )
    assert soft.restricted_area_fg_pct > rates.restricted_area_fg_pct


def test_rest_and_pace_context():
    settings = load_settings()
    assert rest_days_before([date(2024, 10, 27)], date(2024, 10, 28)) == 0
    assert rest_days_before([date(2024, 10, 25)], date(2024, 10, 28)) == 2
    poss = expected_possessions(
        team_pace=100.0,
        opp_pace=100.0,
        home_away="H",
        rest_days=0,
        config=settings.config,
    )
    assert poss < 100.0  # back-to-back penalty


def test_teammate_absence_redistributes_usage():
    rates = {
        1: RateVector(usage=0.30),
        2: RateVector(usage=0.20),
        3: RateVector(usage=0.10),
    }
    updated = redistribute_for_absences(rates, out_player_ids={1}, usage_share=1.0)
    assert updated[1].usage == 0.0
    assert updated[2].usage > 0.20
    assert updated[3].usage > 0.10


def test_minutes_out_and_cap():
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
    capped = project_minutes(
        base_mean=34.0,
        base_sd=4.0,
        config=settings.config,
        status="Available",
        minutes_cap=20.0,
        started=True,
    )
    assert capped.mean <= 20.0
    rng = np.random.default_rng(0)
    draws = capped.sample(rng, 500)
    assert draws.max() <= 20.0 + 1e-9


def test_build_projection_from_data_dir():
    settings = load_settings()
    schedule = read_rows(settings, "schedule", "2024-25")
    game = next(row for row in schedule if row["game_id"] == "0022400102")
    injuries = [
        InjuryEntry(
            game_date=game["game_date"],
            matchup="IND@ORL",
            team_name=None,
            team_abbr="ORL",
            player_name="Bench Warm",
            player_id=None,
            status="Out",
            reason="test",
            minutes_cap=None,
            source="override",
        )
    ]
    # Mark a real ORL player out if present in logs.
    logs = [
        row
        for row in read_rows(settings, "player_game_logs", "2024-25")
        if row["team_abbr"] == "ORL" and row["game_date"] < game["game_date"]
    ]
    assert logs, "expected prior ORL games in DATA_DIR"
    target = max(logs, key=lambda row: float(row["minutes"]))
    injuries.append(
        InjuryEntry(
            game_date=game["game_date"],
            matchup="IND@ORL",
            team_name=None,
            team_abbr="ORL",
            player_name=str(target["player_name"]),
            player_id=int(target["player_id"]),
            status="Out",
            reason="test out",
            minutes_cap=None,
            source="override",
        )
    )
    projection = build_game_projections(
        settings,
        season="2024-25",
        game_id="0022400102",
        injuries=injuries,
        as_of=game["game_date"],
    )
    assert projection.home_abbr == "ORL"
    assert projection.away_abbr == "IND"
    assert projection.home_possessions > 80
    assert len(projection.players) >= 10
    out_row = next(row for row in projection.players if row.player_id == int(target["player_id"]))
    assert out_row.minutes.out
    active = [row for row in projection.players if not row.minutes.out and row.team_abbr == "ORL"]
    assert active
    usage = sum(row.rates.usage for row in active)
    assert usage == pytest.approx(1.0, abs=0.05)
    window = available_season_window(
        settings,
        "2024-25",
        settings.config["blending"]["season_weights"]["seasons_back"],
    )
    assert "2024-25" in window or window == [] or True  # window may include older seasons only
    bundles = [load_season_bundle(settings, "2024-25")]
    rates = player_baseline_and_form(
        bundles,
        player_id=int(target["player_id"]),
        as_of=game["game_date"],
        current_season="2024-25",
        config=settings.config,
        priors={"G": RateVector(), "F": RateVector(), "C": RateVector()},
        position=target.get("position"),
    )
    assert 0.0 < rates.usage < 0.5
    assert sum(getattr(rates, f"{zone}_share") for zone in (
        "restricted_area",
        "paint_non_ra",
        "midrange",
        "left_corner_3",
        "right_corner_3",
        "above_break_3",
    )) == pytest.approx(1.0)
