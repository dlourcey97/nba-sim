"""Referee crews: page parse, polite fetch, and leakage-safe tendencies."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pyarrow.parquet as pq

from ingest.referees import (
    AssignmentGame,
    _write_rows,
    officials_from_summary,
    officials_path,
    parse_assignment_page,
    refresh_referees,
)
from projections.referees import RefereeIndex, _GameStat


_PAGE = """
<h2>NBA Referee Assignments</h2>
<table>
<tr><th>Game</th><th>Crew Chief</th><th>Referee</th><th>Umpire</th><th>Alternate</th></tr>
<tr><td>Cleveland @ Atlanta</td><td>Justin Van Duyne (#64)</td><td>Jacyn Goble (#68)</td>
<td>Matt Kallio (#53)</td><td></td></tr>
<tr><td>LA Clippers @ LA Lakers</td><td>A Chief (#1)</td><td>B Ref (#2)</td><td>C Ump (#3)</td>
<td>D Alt (#4)</td></tr>
</table>
<p>October 30, 2026</p>
<h2>WNBA Referee Assignments</h2>
<table>
<tr><th>Game</th><th>Crew Chief</th><th>Referee</th><th>Umpire</th><th>Alternate</th></tr>
<tr><td>Golden State @ Atlanta</td><td>Fatou Cissoko-Stephens (#15)</td>
<td>Ashley Gloss (#10)</td><td>Ryan Sassano (#3)</td><td>Kevin Fahy (#43)</td></tr>
</table>
"""


class _Response:
    def __init__(self, status: int, payload: str = "", json_body: dict | None = None) -> None:
        self.status_code = status
        self.text = payload
        self._json = json_body or {}
        self.headers = {"content-type": "text/html" if json_body is None else "application/json"}
        self.content = payload.encode()

    def json(self) -> dict:
        return self._json


class _Session:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.calls = 0

    def get(self, url, params=None, headers=None, timeout=None):  # noqa: ANN001
        self.calls += 1
        assert headers["User-Agent"].startswith("nba-sim/1.0")
        return self.response


def _settings(tmp_path: Path):
    from nba_sim.settings import Settings

    return Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        archive_dir=None,
        max_bytes=2_000_000_000,
        current_season="2026-27",
        config={
            "context": {"referees_fetch_enabled": True, "referees_backfill_per_run": 5},
            "http": {
                "timeout_seconds": 5,
                "delay_seconds": 0,
                "max_retries": 0,
                "backoff_seconds": 0,
            },
        },
    )


def test_parse_nba_crews_and_skip_wnba() -> None:
    games = parse_assignment_page(_PAGE)
    assert len(games) == 2
    first = games[0]
    assert first == AssignmentGame(
        game_date=date(2026, 10, 30),
        away_abbr="CLE",
        home_abbr="ATL",
        crew_chief="Justin Van Duyne",
        referee="Jacyn Goble",
        umpire="Matt Kallio",
        crew_chief_jersey="64",
        referee_jersey="68",
        umpire_jersey="53",
    )
    assert games[1].away_abbr == "LAC"
    assert games[1].home_abbr == "LAL"


def test_summary_keeps_three_crew_roles() -> None:
    crew = officials_from_summary(
        {
            "boxScoreSummary": {
                "officials": [
                    {"personId": 1, "name": "A", "jerseyNum": "10  ", "assignment": ""},
                    {"personId": 2, "name": "B", "jerseyNum": "11", "assignment": ""},
                    {"personId": 3, "name": "C", "jerseyNum": "12", "assignment": ""},
                    {"personId": 4, "name": "Alt", "jerseyNum": "13", "assignment": "Alternate"},
                ]
            }
        }
    )
    assert [row["role"] for row in crew] == ["crew_chief", "referee", "umpire"]
    assert crew[0]["jersey"] == "10"


def test_refresh_stops_on_403_and_keeps_parquet(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    path = officials_path(settings)
    _write_rows(
        path,
        [
            {
                "season": "2025-26",
                "game_id": "0022500001",
                "game_date": date(2025, 10, 22),
                "official_id": 7,
                "official_name": "A Ref",
                "jersey": "7",
                "role": "crew_chief",
                "source": "boxscoresummaryv3",
            }
        ],
    )
    session = _Session(_Response(403, "no"))
    status = refresh_referees(
        settings,
        log=lambda _msg: None,
        session=session,
        sleep=lambda _seconds: None,
        today=date(2026, 10, 30),
        max_games=0,
    )
    assert status.stopped_status == 403
    assert session.calls == 1
    kept = pq.read_table(path).to_pylist()
    assert kept[0]["official_name"] == "A Ref"
    assert list(tmp_path.rglob("*.json")) == []
    assert list(tmp_path.rglob("*.html")) == []


def test_tendencies_ignore_the_game_itself_and_shrink() -> None:
    games = [
        _GameStat(
            game_date=date(2025, 11, 1 + index),
            game_id=f"pad-{index}",
            pace=100.0,
            fta_per_100=20.0,
            pf_per_100=40.0,
            pts=220.0,
        )
        for index in range(25)
    ]
    games.append(
        _GameStat(
            game_date=date(2025, 12, 1),
            game_id="g-high",
            pace=110.0,
            fta_per_100=30.0,
            pf_per_100=50.0,
            pts=240.0,
        )
    )
    index = RefereeIndex(
        games,
        officials_by_game={"g-high": [7]},
        official_game_pos={7: [25]},
        assignments={},
    )
    before = index.effect_for(
        game_id="g-high",
        game_date=date(2025, 12, 1),
        home_abbr="ATL",
        away_abbr="CLE",
        prior_games=0,
        pace_weight=0.5,
        ft_weight=0.5,
        clip=0.015,
    )
    assert before.pace_factor == 1.0
    assert before.ft_factor == 1.0
    after = index.effect_for(
        game_id="g-high",
        game_date=date(2025, 12, 2),
        home_abbr="ATL",
        away_abbr="CLE",
        prior_games=0,
        pace_weight=0.5,
        ft_weight=0.5,
        clip=0.015,
    )
    # The ref's prior game is inside the league mean, so the residual is
    # slightly under 10 possessions. Unshrunk, the pace factor clips at +1.5%.
    league_pace = (25 * 100.0 + 110.0) / 26.0
    league_pts = (25 * 220.0 + 240.0) / 26.0
    assert after.sample_games == 1
    assert abs(after.pace_delta - (110.0 - league_pace)) < 1e-9
    assert abs(after.points_delta - (240.0 - league_pts)) < 1e-9
    assert after.pace_factor == 1.015
    shrunk = index.effect_for(
        game_id="g-high",
        game_date=date(2025, 12, 2),
        home_abbr="ATL",
        away_abbr="CLE",
        prior_games=25,
        pace_weight=0.5,
        ft_weight=0.5,
        clip=0.015,
    )
    assert abs(shrunk.pace_delta - (110.0 - league_pace) / 26.0) < 1e-9
    assert shrunk.pace_factor < 1.015
