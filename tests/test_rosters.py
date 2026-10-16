"""As-of-date team rosters from game-log stints (no future leakage)."""

from __future__ import annotations

from datetime import date

from ingest.rosters import (
    active_roster_player_ids,
    merge_common_roster,
    prior_season_label,
    rebuild_team_rosters,
    team_rosters_from_logs,
)
from nba_sim.storage import read_rows, store_rows
from projections.blend import SeasonBundle
from projections.build import _roster_for_team


def _log(
    *,
    player_id: int,
    team_id: int,
    team_abbr: str,
    game_date: date,
    game_id: str,
    player_name: str = "Trade Chip",
    position: str | None = "G",
) -> dict:
    return {
        "season": "2024-25",
        "game_id": game_id,
        "game_date": game_date,
        "player_id": player_id,
        "player_name": player_name,
        "team_id": team_id,
        "team_abbr": team_abbr,
        "opponent_team_id": 99,
        "opponent_abbr": "OPP",
        "home_away": "H",
        "win": True,
        "started": True,
        "position": position,
        "minutes": 30.0,
        "pts": 10,
        "reb": 4,
        "ast": 3,
        "fg3m": 1,
        "stl": 1,
        "blk": 0,
        "tov": 2,
        "fgm": 4,
        "fga": 9,
        "fg3a": 3,
        "ftm": 1,
        "fta": 2,
        "oreb": 1,
        "dreb": 3,
        "plus_minus": 0,
    }


def test_traded_player_stints_from_logs():
    """Player moves NYK -> MIN mid-season; as-of dates pick the right team."""
    player_id = 203944  # synthetic trade chip id
    nyk, minn = 1610612752, 1610612750
    logs = [
        _log(player_id=player_id, team_id=nyk, team_abbr="NYK", game_date=date(2024, 11, 1), game_id="a1"),
        _log(player_id=player_id, team_id=nyk, team_abbr="NYK", game_date=date(2024, 12, 15), game_id="a2"),
        _log(player_id=player_id, team_id=minn, team_abbr="MIN", game_date=date(2025, 1, 20), game_id="b1"),
        _log(player_id=player_id, team_id=minn, team_abbr="MIN", game_date=date(2025, 2, 1), game_id="b2"),
        # Teammates so each side has a roster.
        _log(
            player_id=1,
            team_id=nyk,
            team_abbr="NYK",
            game_date=date(2024, 11, 1),
            game_id="a1",
            player_name="Stay NYK",
        ),
        _log(
            player_id=2,
            team_id=minn,
            team_abbr="MIN",
            game_date=date(2025, 1, 20),
            game_id="b1",
            player_name="Stay MIN",
        ),
    ]
    stints = team_rosters_from_logs("2024-25", logs)
    by_team = {(int(r["team_id"]), int(r["player_id"])): r for r in stints if int(r["player_id"]) == player_id}
    assert nyk in {int(r["team_id"]) for r in stints if int(r["player_id"]) == player_id}
    assert minn in {int(r["team_id"]) for r in stints if int(r["player_id"]) == player_id}
    nyk_stint = by_team[(nyk, player_id)]
    min_stint = by_team[(minn, player_id)]
    assert nyk_stint["from_date"] == date(2024, 11, 1)
    assert nyk_stint["to_date"] == date(2025, 1, 20)
    assert min_stint["from_date"] == date(2025, 1, 20)
    assert min_stint["to_date"] is None

    # Mid-season before trade: on NYK, not MIN.
    mid = date(2025, 1, 10)
    assert player_id in active_roster_player_ids(stints, team_id=nyk, as_of=mid)
    assert player_id not in active_roster_player_ids(stints, team_id=minn, as_of=mid)

    # After first MIN appearance is known (as_of after that game): on MIN only.
    after = date(2025, 1, 21)
    assert player_id not in active_roster_player_ids(stints, team_id=nyk, as_of=after)
    assert player_id in active_roster_player_ids(stints, team_id=minn, as_of=after)

    # Trade debut day: not yet on MIN (from_date < as_of), already off NYK.
    debut = date(2025, 1, 20)
    assert player_id not in active_roster_player_ids(stints, team_id=nyk, as_of=debut)
    assert player_id not in active_roster_player_ids(stints, team_id=minn, as_of=debut)


def test_common_roster_adds_unsigned_player_before_box_score():
    stints = team_rosters_from_logs(
        "2025-26",
        [
            _log(
                player_id=10,
                team_id=1610612738,
                team_abbr="BOS",
                game_date=date(2025, 10, 22),
                game_id="g1",
                player_name="Home Star",
            )
        ],
    )
    # Override season label on the helper rows used above.
    for row in stints:
        row["season"] = "2025-26"
    merged = merge_common_roster(
        stints,
        [
            {
                "team_id": 1610612738,
                "team_abbr": "BOS",
                "player_id": 99,
                "player_name": "New Signing",
                "position": "F",
                "jersey": "7",
                "roster_status": None,
            }
        ],
        season="2025-26",
        as_of=date(2025, 10, 25),
    )
    assert 99 in active_roster_player_ids(merged, team_id=1610612738, as_of=date(2025, 10, 25))
    new_row = next(r for r in merged if int(r["player_id"]) == 99)
    assert new_row["source"] == "common_roster"
    assert new_row["jersey"] == "7"


def test_rebuild_and_roster_for_team_uses_stored_stints(settings):
    season = "2024-25"
    player_id = 42
    team_a, team_b = 100, 200
    logs = [
        _log(player_id=player_id, team_id=team_a, team_abbr="AAA", game_date=date(2024, 11, 5), game_id="1"),
        _log(player_id=player_id, team_id=team_a, team_abbr="AAA", game_date=date(2024, 12, 1), game_id="2"),
        _log(player_id=player_id, team_id=team_b, team_abbr="BBB", game_date=date(2025, 1, 15), game_id="3"),
        _log(
            player_id=7,
            team_id=team_a,
            team_abbr="AAA",
            game_date=date(2025, 1, 15),
            game_id="3",
            player_name="Stay A",
        ),
        _log(
            player_id=8,
            team_id=team_b,
            team_abbr="BBB",
            game_date=date(2025, 1, 15),
            game_id="3",
            player_name="Stay B",
        ),
    ]
    store_rows(settings, "player_game_logs", season, logs, allow_historical=True)
    n = rebuild_team_rosters(settings, season, refresh_common=False, log=lambda *_: None)
    assert n >= 3
    stored = read_rows(settings, "team_rosters", season)
    assert stored
    mid = date(2025, 1, 10)
    bundle = SeasonBundle(
        season,
        rates_by_player={},
        logs_by_player={
            player_id: [row for row in logs if int(row["player_id"]) == player_id],
            7: [row for row in logs if int(row["player_id"]) == 7],
            8: [row for row in logs if int(row["player_id"]) == 8],
        },
    )
    aaa = _roster_for_team(settings, season, [bundle], team_a, mid)
    bbb = _roster_for_team(settings, season, [bundle], team_b, mid)
    assert player_id in aaa
    assert player_id not in bbb
    # Debut day: exclusive to_date drops old team; from_date < as_of keeps them
    # off the new team until the next day (no box-score leakage). last_known must
    # not put them back on the old team.
    debut = date(2025, 1, 15)
    assert player_id not in _roster_for_team(settings, season, [bundle], team_a, debut)
    assert player_id not in _roster_for_team(settings, season, [bundle], team_b, debut)
    after = date(2025, 1, 16)
    aaa_after = _roster_for_team(settings, season, [bundle], team_a, after)
    bbb_after = _roster_for_team(settings, season, [bundle], team_b, after)
    assert player_id not in aaa_after
    assert player_id in bbb_after


def test_prior_season_label():
    assert prior_season_label("2024-25") == "2023-24"
    assert prior_season_label("2025-26") == "2024-25"
