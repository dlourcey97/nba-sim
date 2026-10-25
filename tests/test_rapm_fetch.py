"""nbarapm.com external RAPM fetch helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from ingest.rapm_fetch import (
    _parse_six_factor,
    _parse_timedecay,
    format_rapm_age_line,
    load_timedecay_ratings,
    refresh_nbarapm_rapm,
)


def _settings(tmp_path: Path):
    from nba_sim.settings import Settings

    return Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        archive_dir=None,
        max_bytes=2_000_000_000,
        current_season="2026-27",
        config={
            "context": {
                "nbarapm_enabled": True,
                "nbarapm_fetch_interval_days": 7,
            },
            "http": {"timeout_seconds": 5},
        },
    )


def test_parse_timedecay_keeps_as_of():
    payload = [
        {
            "nba_id": "203999",
            "player_name": "Nikola Jokic",
            "team_abbreviation": "DEN",
            "year": 2026,
            "Latest_Year": 2026,
            "Year_Interval": "TD",
            "RAPM": 9.1,
            "ORAPM": 8.0,
            "DRAPM": 1.1,
            "Off_Poss": 1000,
            "MP2": 2000,
            "half_life_days": 550,
            "as_of_date": "2026-08-21",
        }
    ]
    table, updated = _parse_timedecay(
        payload, fetched_at=datetime(2026, 10, 24, tzinfo=timezone.utc)
    )
    assert updated == "2026-08-21"
    assert table.num_rows == 1
    assert table.column("rapm")[0].as_py() == 9.1


def test_parse_six_factor_rejects_bad_shape():
    try:
        _parse_six_factor([{"foo": 1}], fetched_at=datetime.now(timezone.utc))
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "format changed" in str(exc)


def test_refresh_writes_parquet_and_fallback(tmp_path: Path):
    settings = _settings(tmp_path)
    timedecay = [
        {
            "nba_id": "1629029",
            "player_name": "Luka Doncic",
            "team_abbreviation": "DAL",
            "year": 2026,
            "Latest_Year": 2026,
            "Year_Interval": "TD",
            "RAPM": 4.0,
            "ORAPM": 5.0,
            "DRAPM": -1.0,
            "Off_Poss": 500,
            "MP2": 1000,
            "half_life_days": 550,
            "as_of_date": "2026-08-21",
        }
    ]
    six = [
        {
            "nba_id": "1629029",
            "player_name": "Luka Doncic",
            "Latest_Year": 2026,
            "Year_Interval": "TD",
            "OVR_RAPM": 4.0,
            "Off_RAPM": 5.0,
            "Def_RAPM": -1.0,
            "Off_Poss": 500,
            "sc_OFF_TS": 1.0,
            "sc_OFF_TOV": 0.0,
            "sc_OFF_REB": 0.0,
            "sc_DEF_TS": 0.0,
            "sc_DEF_TOV": 0.0,
            "sc_DEF_REB": 0.0,
            "sc_POSS": 0.0,
        }
    ]

    def fake_download(url, timeout_seconds, log):
        if "timedecay" in url:
            return timedecay
        return six

    with patch("ingest.rapm_fetch._download_json", side_effect=fake_download):
        status = refresh_nbarapm_rapm(settings, log=lambda *_: None, force=True)
    assert status.fetched
    ratings = load_timedecay_ratings(settings)
    assert ratings[1629029] == 4.0
    current = settings.data_dir / "external" / "nbarapm_timedecay.parquet"
    assert current.is_file()

    # Second fetch with failure keeps last good copy.
    def boom(url, timeout_seconds, log):
        raise RuntimeError("blocked")

    with patch("ingest.rapm_fetch._download_json", side_effect=boom):
        # Force past freshness by clearing meta check via force=True
        status2 = refresh_nbarapm_rapm(settings, log=lambda *_: None, force=True)
    assert not status2.fetched
    assert status2.warnings
    assert load_timedecay_ratings(settings)[1629029] == 4.0
    assert "source_updated=2026-08-21" in format_rapm_age_line(settings)


def test_skip_when_fresh(tmp_path: Path):
    settings = _settings(tmp_path)
    timedecay = [
        {
            "nba_id": "1",
            "player_name": "X",
            "team_abbreviation": "BOS",
            "year": 2026,
            "Latest_Year": 2026,
            "Year_Interval": "TD",
            "RAPM": 1.0,
            "as_of_date": "2026-08-21",
        }
    ]

    def fake_download(url, timeout_seconds, log):
        return timedecay if "timedecay" in url else [
            {
                "nba_id": "200",
                "player_name": "Y",
                "Latest_Year": 2026,
                "Year_Interval": "TD",
                "OVR_RAPM": 1.0,
                "Off_RAPM": 1.0,
                "Def_RAPM": 0.0,
                "Off_Poss": 1,
                "sc_OFF_TS": 0,
                "sc_OFF_TOV": 0,
                "sc_OFF_REB": 0,
                "sc_DEF_TS": 0,
                "sc_DEF_TOV": 0,
                "sc_DEF_REB": 0,
                "sc_POSS": 0,
            }
        ]

    calls = {"n": 0}

    def counting_download(url, timeout_seconds, log):
        calls["n"] += 1
        return fake_download(url, timeout_seconds, log)

    with patch("ingest.rapm_fetch._download_json", side_effect=counting_download):
        refresh_nbarapm_rapm(settings, log=lambda *_: None, force=True)
        first = calls["n"]
        status = refresh_nbarapm_rapm(settings, log=lambda *_: None, force=False)
    assert status.skipped_fresh
    assert calls["n"] == first  # no additional downloads
