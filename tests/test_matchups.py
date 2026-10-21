"""Defender impact aggregation and primary-defender assignment."""

from __future__ import annotations

from ingest.matchups import defender_impact_from_league_matchups, primary_defender_weights


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
