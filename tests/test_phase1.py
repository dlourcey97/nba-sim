from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pyarrow as pa
import pytest

from nba_sim.errors import (
    ConfigError,
    PathInsideRepoError,
    SeasonFrozenError,
    StorageCapExceeded,
    StorageError,
)
from nba_sim.schema import TABLES, render_schema_markdown
from nba_sim.settings import load_settings
from nba_sim.storage import (
    cleanup_temp,
    collect_storage_report,
    directory_size,
    enforce_cap,
    finish_run,
    format_storage_report,
    list_seasons,
    mark_season_complete,
    store_rows,
    stored_keys,
)

REPO = Path(__file__).resolve().parents[1]
REQUIRED_IGNORE = (
    "DATA_DIR",
    "ARCHIVE_DIR",
    "results/",
    "*.parquet",
    "*.duckdb",
    "*.db",
    "*.csv",
    "*.json.gz",
)


def _value(field: pa.Field, index: int, season: str):
    if field.name == "season":
        return season
    typ = field.type
    if pa.types.is_string(typ):
        return "H" if field.name == "home_away" else f"{field.name}-{index}"
    if pa.types.is_integer(typ):
        return index + 1
    if pa.types.is_floating(typ):
        return float(index) + 0.5
    if pa.types.is_boolean(typ):
        return index % 2 == 0
    if pa.types.is_date(typ):
        return date(2025, 10, 21)
    if pa.types.is_timestamp(typ):
        return datetime(2025, 10, 21, 12, 0, 0)
    raise AssertionError(f"unsupported type {typ}")


def _rows(table: str, season: str, count: int, **overrides) -> list[dict]:
    spec = TABLES[table]
    rows = []
    for index in range(count):
        row = {field.name: _value(field, index, season) for field in spec.arrow_schema()}
        row.update(overrides)
        rows.append(row)
    return rows


def test_env_and_config_load():
    settings = load_settings()
    assert settings.data_dir.is_absolute()
    assert settings.archive_dir is not None
    assert settings.repo_root not in settings.data_dir.parents
    assert settings.max_bytes == 2_147_483_648
    assert settings.current_season == "2026-27"
    assert settings.config["simulation"]["runs"] == 10000
    assert settings.config["features"]["late_season_incentives"] is False
    weights = settings.config["blending"]["season_weights"]["weights"]
    assert abs(sum(weights) - 1) < 1e-9


def test_data_dir_inside_repo_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(REPO / "data"))
    monkeypatch.setenv("ARCHIVE_DIR", str(tmp_path / "archive"))
    with pytest.raises(PathInsideRepoError):
        load_settings()


def test_relative_data_dir_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", "relative/data")
    monkeypatch.setenv("ARCHIVE_DIR", str(tmp_path / "archive"))
    with pytest.raises(ConfigError, match="absolute"):
        load_settings()


def test_ignore_files_exclude_data_artifacts():
    for name in (".gitignore", ".cursorignore"):
        text = (REPO / name).read_text(encoding="utf-8")
        for pattern in REQUIRED_IGNORE:
            assert pattern in text, f"{name} missing {pattern}"


def test_schema_markdown_matches_code():
    assert (REPO / "SCHEMA.md").read_text(encoding="utf-8") == render_schema_markdown()


def test_every_table_round_trips(settings):
    for name, spec in TABLES.items():
        rows = _rows(name, "2024-25", 2)
        result = store_rows(settings, name, "2024-25", rows, allow_historical=True)
        assert result.rows_written == 2
        assert result.path is not None and result.path.is_file()
        keys = stored_keys(settings, name, "2024-25")
        assert len(keys) == 2
        assert spec.key[0] in spec.arrow_schema().names
    assert list_seasons(settings.data_dir, "player_game_logs") == ["2024-25"]
    assert not list(settings.data_dir.rglob("*.duckdb"))


def test_incremental_skips_existing_keys_and_keeps_original_values(settings):
    season = settings.current_season
    first = _rows("player_game_logs", season, 1)
    store_rows(settings, "player_game_logs", season, first)
    changed = _rows("player_game_logs", season, 1, pts=99)
    added = _rows("player_game_logs", season, 1)
    added[0]["game_id"] = "game-new"
    added[0]["player_id"] = 50
    result = store_rows(settings, "player_game_logs", season, changed + added)
    assert result.rows_written == 1
    assert result.rows_skipped == 1
    import duckdb

    points = duckdb.sql(
        f"SELECT pts FROM read_parquet('{result.path}') WHERE game_id = '{first[0]['game_id']}'"
    ).fetchall()
    assert points == [(1,)]
    assert len(stored_keys(settings, "player_game_logs", season)) == 2


def test_completed_season_is_frozen(settings):
    store_rows(
        settings,
        "team_game_results",
        "2023-24",
        _rows("team_game_results", "2023-24", 1),
        allow_historical=True,
    )
    with pytest.raises(StorageError, match="current season"):
        store_rows(settings, "team_game_results", "2023-24", _rows("team_game_results", "2023-24", 1))
    mark_season_complete(settings, "team_game_results", "2023-24")
    with pytest.raises(SeasonFrozenError):
        store_rows(
            settings,
            "team_game_results",
            "2023-24",
            _rows("team_game_results", "2023-24", 1),
            allow_historical=True,
        )


def test_replace_overwrites_and_drops_completion_marker(settings):
    store_rows(settings, "player_game_rates", "2024-25", _rows("player_game_rates", "2024-25", 2))
    mark_season_complete(settings, "player_game_rates", "2024-25")
    result = store_rows(settings, "player_game_rates", "2024-25", _rows("player_game_rates", "2024-25", 1))
    assert result.rows_written == 1
    import duckdb

    count = duckdb.sql(f"SELECT count(*) FROM read_parquet('{result.path}')").fetchone()
    assert count == (1,)
    assert not (result.path.parent / "_COMPLETE").exists()
    files = list(result.path.parent.iterdir())
    assert files == [result.path]


def test_upsert_replaces_matching_key(settings):
    season = settings.current_season
    original = _rows("schedule", season, 1, status="scheduled", home_pts=None, away_pts=None)
    store_rows(settings, "schedule", season, original)
    updated = _rows("schedule", season, 1, status="final", home_pts=110, away_pts=101)
    result = store_rows(settings, "schedule", season, updated)
    assert result.rows_written == 1
    import duckdb

    row = duckdb.sql(
        f"SELECT status, home_pts, away_pts FROM read_parquet('{result.path}')"
    ).fetchone()
    assert row == ("final", 110, 101)


def test_prediction_game_row_allows_null_player(settings):
    season = settings.current_season
    row = _rows("prediction_history", season, 1, row_kind="game", player_id=None)[0]
    result = store_rows(settings, "prediction_history", season, [row])
    assert stored_keys(settings, "prediction_history", season) == {("game", row["game_id"], None)}
    assert result.rows_written == 1


def test_rejects_bad_rows(settings):
    season = settings.current_season
    row = _rows("player_game_logs", season, 1)[0]
    row["season"] = "2024-25"
    with pytest.raises(Exception, match="does not match partition"):
        store_rows(settings, "player_game_logs", season, [row])
    dup = _rows("player_game_logs", season, 1) * 2
    with pytest.raises(Exception, match="duplicate key"):
        store_rows(settings, "player_game_logs", season, dup)
    extra = _rows("player_game_logs", season, 1)[0]
    extra["odds"] = 1.5
    with pytest.raises(Exception, match="unexpected columns"):
        store_rows(settings, "player_game_logs", season, [extra])


def test_storage_report_uses_file_sizes_only(settings):
    season_dir = settings.data_dir / "player_game_logs" / "season=2024-25"
    season_dir.mkdir(parents=True)
    payload = b"not parquet, and the report must not parse it"
    (season_dir / "data.parquet").write_bytes(payload)
    (settings.data_dir / "_tmp").mkdir()
    (settings.data_dir / "_tmp" / "scratch.tmp").write_bytes(b"12345")
    report = collect_storage_report(settings)
    assert report.used_bytes == directory_size(settings.data_dir)
    assert sum(row.num_bytes for row in report.rows) == report.used_bytes
    text = format_storage_report(report)
    assert "player_game_logs" in text
    assert "2024-25" in text
    assert "TOTAL" in text
    assert len(payload) == next(
        row.num_bytes for row in report.rows if row.table == "player_game_logs" and row.season == "2024-25"
    )


def test_cap_discards_the_new_file(settings):
    season = settings.current_season
    settings.data_dir.mkdir()
    blob = settings.data_dir / "blob.bin"
    blob.write_bytes(b"x" * 1000)
    tight = replace(settings, max_bytes=1000)
    with pytest.raises(StorageCapExceeded) as caught:
        store_rows(tight, "player_game_logs", season, _rows("player_game_logs", season, 1))
    assert caught.value.cap == 1000
    assert "Aborting" in str(caught.value) or "discarded" in str(caught.value)
    assert blob.read_bytes() == b"x" * 1000
    assert list(settings.data_dir.rglob("*.tmp")) == []
    assert not (settings.data_dir / "player_game_logs").exists()


def test_enforce_cap_allows_exact_size(settings):
    settings.data_dir.mkdir()
    (settings.data_dir / "blob.bin").write_bytes(b"x" * 40)
    exact = replace(settings, max_bytes=40)
    assert enforce_cap(exact) == 40
    over = replace(settings, max_bytes=39)
    with pytest.raises(StorageCapExceeded):
        enforce_cap(over)


def test_cleanup_and_finish_run(settings, capsys):
    season = settings.current_season
    scratch = settings.data_dir / "_tmp"
    scratch.mkdir(parents=True)
    (scratch / "raw.json").write_text("{}", encoding="utf-8")
    (settings.data_dir / "player_game_logs").mkdir()
    (settings.data_dir / "player_game_logs" / "partial.parquet.tmp").write_bytes(b"temp")
    store_rows(settings, "schedule", season, _rows("schedule", season, 1))
    removed = cleanup_temp(settings.data_dir)
    assert removed >= 2
    assert not scratch.exists()
    assert list(settings.data_dir.rglob("*.tmp")) == []
    report = finish_run(settings)
    printed = capsys.readouterr().out
    assert "schedule" in printed
    assert "TOTAL" in printed
    assert report.within_cap
    assert report.used_bytes == directory_size(settings.data_dir)


def test_cli_report(settings, tmp_path):
    season = settings.current_season
    store_rows(settings, "schedule", season, _rows("schedule", season, 1))
    env = os.environ.copy()
    env["DATA_DIR"] = str(settings.data_dir)
    env["ARCHIVE_DIR"] = str(settings.archive_dir)
    completed = subprocess.run(
        [sys.executable, "-m", "nba_sim"],
        cwd=REPO,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "schedule" in completed.stdout
    assert season in completed.stdout
    assert "within_cap: yes" in completed.stdout
    assert "TOTAL" in completed.stdout
