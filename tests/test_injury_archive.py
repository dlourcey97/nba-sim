"""Pre-tip selection for the historical injury archive."""

from datetime import date, datetime, time

from ingest.injuries import InjuryEntry
from ingest.injury_archive import ParsedReport, keep_latest_before_tip


def _entry(name: str, matchup: str, status: str) -> InjuryEntry:
    return InjuryEntry(
        game_date=date(2025, 1, 15),
        matchup=matchup,
        team_name=None,
        team_abbr="NYK",
        player_name=name,
        player_id=None,
        status=status,
        reason="",
        minutes_cap=None,
        source="injury_report",
    )


def _report(hour: int, minute: int, tips: dict[str, time], entries: list[InjuryEntry], stamp: str) -> ParsedReport:
    return ParsedReport(
        stamp=stamp,
        published=datetime(2025, 1, 15, hour, minute),
        tips=tips,
        entries=entries,
    )


def test_latest_report_before_each_tip_is_kept() -> None:
    early = _report(
        13,
        0,
        {"NYK@PHI": time(19, 0), "BOS@TOR": time(15, 0)},
        [_entry("Jalen Brunson", "NYK@PHI", "Probable"), _entry("JD Davison", "BOS@TOR", "Out")],
        "01PM",
    )
    late = _report(
        17,
        30,
        {"NYK@PHI": time(19, 0), "BOS@TOR": time(15, 0)},
        [_entry("Jalen Brunson", "NYK@PHI", "Out"), _entry("JD Davison", "BOS@TOR", "Out")],
        "05PM",
    )
    rows = {(row["matchup"], row["player_name"]): row for row in keep_latest_before_tip([late, early])}
    assert rows[("NYK@PHI", "Jalen Brunson")]["status"] == "Out"
    assert rows[("NYK@PHI", "Jalen Brunson")]["report_stamp"] == "05PM"
    assert rows[("BOS@TOR", "JD Davison")]["report_stamp"] == "01PM"


def test_a_report_after_tip_is_dropped() -> None:
    late = _report(
        17,
        30,
        {"BOS@TOR": time(15, 0)},
        [_entry("JD Davison", "BOS@TOR", "Out")],
        "05PM",
    )
    assert keep_latest_before_tip([late]) == []
