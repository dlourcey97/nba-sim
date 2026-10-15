"""Phase 6: summaries, JSON, prediction history, run CLI helpers."""

from __future__ import annotations

import json
from dataclasses import replace

from nba_sim.settings import load_settings
from nba_sim.storage import read_rows
from outputs.history import fill_actuals_for_season, history_rows_from_summary, write_prediction_history
from outputs.json_writer import clear_latest, write_game_json
from outputs.pipeline import run_game
from outputs.summarize import summarize_game
from projections.build import build_game_projections
from sim.engine import simulate_game


def test_summarize_and_json(tmp_path):
    settings = replace(load_settings(), repo_root=tmp_path)
    game = next(row for row in read_rows(settings, "schedule", "2024-25") if row["game_id"] == "0022400102")
    projection = build_game_projections(
        settings,
        season="2024-25",
        game_id=game["game_id"],
        as_of=game["game_date"],
    )
    result = simulate_game(projection, runs=100, seed=3, config=settings.config)
    summary = summarize_game(projection, result, thresholds=[("pts", 20.0)])
    assert 0.0 <= summary.home_win_prob <= 1.0
    assert summary.players
    assert "pts" in summary.players[0].stats
    assert summary.players[0].thresholds.get("pts", {}).get("20.0") is not None
    path = write_game_json(tmp_path, summary)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["game_id"] == "0022400102"
    assert payload["home_abbr"] == "ORL"
    assert "players" in payload
    assert clear_latest(tmp_path) == 1


def test_history_rows_and_actuals():
    settings = load_settings()
    game = next(row for row in read_rows(settings, "schedule", "2024-25") if row["game_id"] == "0022400102")
    projection = build_game_projections(
        settings,
        season="2024-25",
        game_id=game["game_id"],
        as_of=game["game_date"],
    )
    result = simulate_game(projection, runs=50, seed=4, config=settings.config)
    summary = summarize_game(projection, result)
    rows = history_rows_from_summary(summary)
    assert any(row["row_kind"] == "game" for row in rows)
    assert any(row["row_kind"] == "player" for row in rows)
    game_row = next(row for row in rows if row["row_kind"] == "game")
    assert game_row["pred_home_pts_mean"] is not None
    assert game_row["pred_pts_mean"] is None

    written = write_prediction_history(settings, summary, allow_historical=True)
    assert written >= 1
    actuals = fill_actuals_for_season(settings, "2024-25", allow_historical=True)
    assert actuals >= 1
    stored = read_rows(settings, "prediction_history", "2024-25")
    filled_game = next(row for row in stored if row["row_kind"] == "game" and row["game_id"] == "0022400102")
    assert filled_game["actual_home_pts"] == game["home_pts"]
    assert filled_game["actual_away_pts"] == game["away_pts"]
    filled_player = next(
        row
        for row in stored
        if row["row_kind"] == "player" and row["game_id"] == "0022400102" and row["actual_pts"] is not None
    )
    assert filled_player["actual_pts"] is not None


def test_run_game_pipeline(tmp_path):
    settings = replace(load_settings(), repo_root=tmp_path)
    slate = run_game(
        settings,
        season="2024-25",
        game_id="0022400102",
        runs=50,
        seed=5,
        write_json=True,
        write_history=True,
        allow_historical=True,
    )
    assert len(slate.summaries) == 1
    assert slate.json_paths
    assert slate.json_paths[0].is_file()
    assert slate.history_rows >= 1
