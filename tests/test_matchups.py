"""Defender impact aggregation and primary-defender assignment."""

from __future__ import annotations

import pytest

from ingest.matchups import (
    bucket_weights,
    buckets_from_logs,
    defender_impact_from_league_matchups,
    matchup_shares_from_league_matchups,
    offensive_bucket,
    primary_defender_weights,
    scorer_ids_from_logs,
)


def test_defender_impact_collapses_pairs():
    rows = [
        {
            "DEF_PLAYER_ID": 1,
            "DEF_PLAYER_NAME": "A",
            "PARTIAL_POSS": 10.0,
            "MATCHUP_FGA": 8.0,
            "MATCHUP_FGM": 4.0,
            "MATCHUP_FG3A": 2.0,
            "MATCHUP_FG3M": 1.0,
            "PLAYER_PTS": 10.0,
            "MATCHUP_TIME_SEC": 100.0,
        },
        {
            "DEF_PLAYER_ID": 1,
            "DEF_PLAYER_NAME": "A",
            "PARTIAL_POSS": 5.0,
            "MATCHUP_FGA": 4.0,
            "MATCHUP_FGM": 1.0,
            "MATCHUP_FG3A": 1.0,
            "MATCHUP_FG3M": 0.0,
            "PLAYER_PTS": 2.0,
            "MATCHUP_TIME_SEC": 50.0,
        },
        {
            "DEF_PLAYER_ID": 2,
            "DEF_PLAYER_NAME": "B",
            "PARTIAL_POSS": 20.0,
            "MATCHUP_FGA": 10.0,
            "MATCHUP_FGM": 3.0,
            "MATCHUP_FG3A": 5.0,
            "MATCHUP_FG3M": 1.0,
            "PLAYER_PTS": 8.0,
            "MATCHUP_TIME_SEC": 200.0,
        },
    ]
    out = defender_impact_from_league_matchups("2024-25", rows)
    assert len(out) == 2
    by_id = {row["defender_id"]: row for row in out}
    assert by_id[1]["fga"] == 12.0
    assert by_id[1]["fgm"] == 5.0
    assert abs(by_id[1]["fg_pct"] - 5.0 / 12.0) < 1e-9


def test_primary_defender_prefers_same_position():
    weights = primary_defender_weights(
        offense_positions=["PG"],
        defense_positions=["C", "PG", "SF"],
        defense_minutes=[30.0, 10.0, 20.0],
    )
    assert len(weights) == 1
    assert len(weights[0]) == 3
    # PG defender should dominate despite lower minutes.
    assert weights[0][1] == max(weights[0])


def test_offensive_bucket_counts_a_scoring_center_as_a_scorer():
    assert offensive_bucket("C", is_scorer=True) == "scorer"
    assert offensive_bucket("C", is_scorer=False) == "big"
    assert offensive_bucket("SF", is_scorer=False) == "wing"
    assert offensive_bucket(None, is_scorer=False) == "wing"


def test_matchup_shares_split_seconds_and_skip_unknown_offense():
    rows = [
        {
            "DEF_PLAYER_ID": 10,
            "DEF_PLAYER_NAME": "Amen",
            "OFF_PLAYER_ID": 1,
            "MATCHUP_TIME_SEC": 70.0,
        },
        {
            "DEF_PLAYER_ID": 10,
            "DEF_PLAYER_NAME": "Amen",
            "OFF_PLAYER_ID": 2,
            "MATCHUP_TIME_SEC": 30.0,
        },
        {
            "DEF_PLAYER_ID": 10,
            "DEF_PLAYER_NAME": "Amen",
            "OFF_PLAYER_ID": 99,
            "MATCHUP_TIME_SEC": 500.0,
        },
    ]
    out = matchup_shares_from_league_matchups(
        "2024-25",
        rows,
        buckets_by_offense_id={1: "scorer", 2: "big"},
    )
    assert len(out) == 1
    row = out[0]
    assert row["matchup_sec"] == 100.0
    assert row["share_scorer"] == 0.70
    assert row["share_wing"] == 0.0
    assert row["share_big"] == 0.30


def test_bucket_weights_follow_who_actually_guarded_scorers():
    # Defender 0 lives on scorers. Defender 1 has no history. Defender 2 guards bigs.
    shares = [(0.80, 0.10, 0.10), None, (0.05, 0.15, 0.80)]
    affinity = [1.0, 1.0, 1.0]
    weights = bucket_weights(shares, affinity, "scorer")
    assert weights[0] == max(weights)
    assert abs(sum(weights) - 1.0) < 1e-9
    # A missing row does not get the scorer's history; he stays on affinity.
    assert weights[1] > weights[2]


def test_scorer_ids_require_eighteen_points_and_twenty_games():
    rows = []
    for game in range(20):
        rows.append({"player_id": 1, "minutes": 30, "pts": 18, "position": "C"})
        rows.append({"player_id": 2, "minutes": 30, "pts": 10, "position": "C"})
    rows.append({"player_id": 3, "minutes": 30, "pts": 40, "position": "PG"})
    assert scorer_ids_from_logs(rows) == {1}
    buckets = buckets_from_logs(rows)
    assert buckets[1] == "scorer"
    assert buckets[2] == "big"


def test_engine_bucket_blend_matches_the_share_weights():
    import numpy as np

    from sim.engine import _blend_bucket_shares

    affinity = np.array([[1.0, 0.55, 0.20, 0.20, 0.35]])
    shares = np.array(
        [
            [0.80, 0.10, 0.10],
            [0.05, 0.15, 0.80],
            [np.nan, np.nan, np.nan],
            [0.20, 0.60, 0.20],
            [0.10, 0.20, 0.70],
        ]
    )
    def_lineups = np.array([[0, 1, 2, 3, 4]])
    off_bucket = np.array([0])
    shooters = np.array([0])
    blended = _blend_bucket_shares(affinity, def_lineups, shares, off_bucket, shooters)[0]
    expected = bucket_weights(
        [
            (0.80, 0.10, 0.10),
            (0.05, 0.15, 0.80),
            None,
            (0.20, 0.60, 0.20),
            (0.10, 0.20, 0.70),
        ],
        [1.0, 0.55, 0.20, 0.20, 0.35],
        "scorer",
    )
    assert list(blended) == pytest.approx(expected)
