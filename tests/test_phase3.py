"""Phase 3: injury PDF parsing and overrides.yaml precedence."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from ingest.injuries import (
    InjuryEntry,
    InjuryReportError,
    active_absences,
    load_overrides,
    merge_injuries,
    minutes_caps,
    parse_injury_pdf_bytes,
    parse_injury_text,
)

SAMPLE_TEXT = """
Injury Report: 10/22/25 08:30 PM Page 1 of 6
Game Date Game Time Matchup Team Player Name Current Status Reason
10/22/2025 07:00 (ET) BKN@CHA Brooklyn Nets Highsmith, Haywood Out Injury/Illness - Right Knee; Surgery
Wolf, Danny Out Injury/Illness - Left Ankle; Sprain
Charlotte Hornets Green, Josh Out Injury/Illness - Left Shoulder; Surgery
CLE@NYK Cleveland Cavaliers Garland, Darius Out Injury/Illness - Left Great Toe; Surgery
New York Knicks Anunoby, OG Available Injury/Illness - Left Ankle; Sprain
Towns, Karl- Anthony Questionable Injury/Illness - Right Quad; Strain
07:30 (ET) PHI@BOS Boston Celtics Tatum, Jayson Out Injury/Illness - Right Achilles; Repair
Brown, Jaylen Probable Injury/Illness - Left Hamstring; Strain
"""


def test_parse_injury_text_players_and_statuses():
    rows = parse_injury_text(SAMPLE_TEXT, report_date=date(2025, 10, 22))
    by_name = {row.player_name: row for row in rows}
    assert by_name["Haywood Highsmith"].status == "Out"
    assert by_name["Haywood Highsmith"].team_abbr == "BKN"
    assert by_name["Haywood Highsmith"].matchup == "BKN@CHA"
    assert by_name["Josh Green"].team_abbr == "CHA"
    assert by_name["OG Anunoby"].status == "Available"
    assert by_name["Karl-Anthony Towns"].status == "Questionable"
    assert by_name["Jayson Tatum"].matchup == "PHI@BOS"
    assert by_name["Jaylen Brown"].status == "Probable"
    assert all(row.source == "injury_report" for row in rows)


def test_overrides_take_precedence(tmp_path: Path):
    report = [
        InjuryEntry(
            game_date=date(2025, 10, 22),
            matchup="PHI@BOS",
            team_name="Boston Celtics",
            team_abbr="BOS",
            player_name="Jayson Tatum",
            player_id=1628369,
            status="Out",
            reason="Achilles",
            minutes_cap=None,
            source="injury_report",
        )
    ]
    overrides_path = tmp_path / "overrides.yaml"
    overrides_path.write_text(
        yaml.safe_dump(
            {
                "players": [
                    {
                        "player_id": 1628369,
                        "player_name": "Jayson Tatum",
                        "team_abbr": "BOS",
                        "game_date": "2025-10-22",
                        "status": "available",
                        "reason": "cleared",
                        "minutes_cap": 24.0,
                    },
                    {
                        "player_id": 203114,
                        "player_name": "Khris Middleton",
                        "team_abbr": "WAS",
                        "game_date": "2025-10-22",
                        "status": "out",
                        "reason": "manual",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    overrides = load_overrides(overrides_path)
    merged = merge_injuries(report, overrides, game_date=date(2025, 10, 22))
    by_id = {row.player_id: row for row in merged}
    assert by_id[1628369].status == "Available"
    assert by_id[1628369].source == "override"
    assert by_id[1628369].minutes_cap == 24.0
    assert by_id[203114].status == "Out"
    assert minutes_caps(merged)[1628369] == 24.0
    assert {row.player_id for row in active_absences(merged)} == {203114}


def test_load_overrides_validates_status(tmp_path: Path):
    path = tmp_path / "overrides.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "players": [
                    {
                        "player_id": 1,
                        "game_date": "2025-10-22",
                        "status": "suspended",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(InjuryReportError):
        load_overrides(path)


def test_repo_overrides_yaml_loads():
    path = Path(__file__).resolve().parents[1] / "overrides.yaml"
    rows = load_overrides(path)
    # Game-day file may be empty or hold tonight's manual rows; just require valid parse.
    assert isinstance(rows, list)
    for row in rows:
        assert row.status in {"Out", "Doubtful", "Questionable", "Probable", "Available"}
        assert row.source == "override"


def test_parse_real_pdf_bytes_when_available():
    """Use a live PDF if the network answers; otherwise skip."""
    import requests

    url = "https://ak-static.cms.nba.com/referee/injury/Injury-Report_2025-10-22_08PM.pdf"
    try:
        response = requests.get(
            url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"},
        )
    except requests.RequestException:
        pytest.skip("injury PDF host unreachable")
    if response.status_code != 200 or not response.content.startswith(b"%PDF"):
        pytest.skip("injury PDF not available")
    rows = parse_injury_pdf_bytes(response.content, report_date=date(2025, 10, 22))
    assert len(rows) >= 20
    assert any(row.player_name == "Jayson Tatum" and row.status == "Out" for row in rows)
    assert any(row.team_abbr == "NYK" for row in rows)
