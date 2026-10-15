"""Phase 7: walk-forward metrics and tuning helpers."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from backtest.evaluate import evaluate_seasons
from backtest.metrics import (
    brier_score,
    calibration_bins,
    mean_abs_error,
    percentile_coverage,
    write_calibration_svg,
)
from backtest.tune import candidate_configs, score_report
from nba_sim.settings import load_settings


def test_metric_helpers(tmp_path: Path):
    probs = np.array([0.2, 0.4, 0.6, 0.8])
    outcomes = np.array([0.0, 0.0, 1.0, 1.0])
    assert brier_score(probs, outcomes) == np.mean((probs - outcomes) ** 2)
    assert mean_abs_error(np.array([10.0, 20.0]), np.array([12.0, 18.0])) == 2.0
    assert percentile_coverage(
        np.array([5.0, 15.0, 25.0]),
        np.array([0.0, 10.0, 20.0]),
        np.array([10.0, 20.0, 30.0]),
    ) == np.mean([True, True, True])
    bins = calibration_bins(probs, outcomes, n_bins=4)
    assert len(bins) == 4
    svg = tmp_path / "cal.svg"
    write_calibration_svg(bins, svg)
    assert "svg" in svg.read_text(encoding="utf-8")


def test_walk_forward_on_data_dir(tmp_path: Path):
    settings = load_settings()
    report = evaluate_seasons(
        settings,
        ["2024-25"],
        runs=80,
        seed=11,
        max_games=3,
    )
    assert report.games == 3
    assert report.player_rows > 0
    assert 0.0 <= report.brier_win <= 1.0
    assert report.mae_pts >= 0.0
    assert 0.0 <= report.coverage_10_90 <= 1.0
    out = tmp_path / "metrics.json"
    out.write_text(json.dumps(report.as_dict()), encoding="utf-8")
    assert out.is_file()


def test_tune_candidates_and_score():
    settings = load_settings()
    configs = candidate_configs(settings.config)
    assert len(configs) == 27
    report = evaluate_seasons(
        settings,
        ["2024-25"],
        runs=40,
        seed=2,
        max_games=2,
        config_override=configs[0],
    )
    value = score_report(report)
    assert value < 1e9
