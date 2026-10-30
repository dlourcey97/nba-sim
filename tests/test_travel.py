"""Travel uses only earlier games, and the pace shift stays off until enabled."""

from datetime import date

from projections.travel import travel_pace_delta, travel_state


def _row(when: date, home: str, away: str, home_id: int, away_id: int) -> dict:
    return {
        "game_date": when,
        "home_abbr": home,
        "away_abbr": away,
        "home_team_id": home_id,
        "away_team_id": away_id,
    }


def test_a_later_game_does_not_change_todays_trip() -> None:
    denver = 1610612743
    boston = 1610612738
    schedule = [
        _row(date(2025, 1, 10), "BOS", "DEN", boston, denver),
        _row(date(2025, 1, 12), "DEN", "BOS", denver, boston),
        _row(date(2025, 1, 20), "MIA", "DEN", 1610612748, denver),
    ]
    before = travel_state(
        schedule,
        team_id=denver,
        team_abbr="DEN",
        game_date=date(2025, 1, 12),
        home_away="H",
        opponent_abbr="BOS",
    )
    assert before.miles > 1500
    assert before.games_last_4 == 1
    opener = travel_state(
        schedule,
        team_id=denver,
        team_abbr="DEN",
        game_date=date(2025, 1, 10),
        home_away="A",
        opponent_abbr="BOS",
    )
    assert opener.miles == 0.0
    assert opener.games_last_6 == 0


def test_pace_delta_is_zero_when_disabled() -> None:
    state = travel_state(
        [],
        team_id=1,
        team_abbr="DEN",
        game_date=date(2025, 1, 12),
        home_away="H",
        opponent_abbr="BOS",
    )
    assert travel_pace_delta(state, enabled=False) == 0.0
    assert travel_pace_delta(state, enabled=True) == 0.0
