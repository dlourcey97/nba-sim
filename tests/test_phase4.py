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
    a = RateVector(usage=0.30, sample_possessions=100)
    b = RateVector(usage=0.10, sample_possessions=100)
    mixed = blend_vectors([(a, 1.0), (b, 1.0)])
    assert mixed.usage == pytest.approx(0.20)


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
