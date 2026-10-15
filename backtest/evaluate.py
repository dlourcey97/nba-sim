"""Walk-forward evaluation using only data available before each game."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.metrics import (
    MetricReport,
    brier_score,
    calibration_bins,
    mean_abs_error,
    percentile_coverage,
    write_calibration_svg,
)
from ingest.parse import parse_seasons
from nba_sim.errors import NbaSimError
from nba_sim.settings import load_settings
from nba_sim.storage import finish_run, read_rows
from outputs.summarize import summarize_game
from projections.build import build_game_projections
from sim.engine import simulate_game


def evaluate_seasons(
    settings,
    seasons: list[str],
    *,
    runs: int = 500,
    seed: int = 0,
    max_games: int | None = None,
    config_override: dict | None = None,
) -> MetricReport:
    config = settings.config if config_override is None else config_override
    local = replace(settings, config=config)
    home_probs: list[float] = []
    home_wins: list[float] = []
    pred_pts: list[float] = []
    act_pts: list[float] = []
    pred_reb: list[float] = []
    act_reb: list[float] = []
    pred_ast: list[float] = []
    act_ast: list[float] = []
    pred_min: list[float] = []
    act_min: list[float] = []
    cover_hits: list[float] = []
    games = 0

    for season in seasons:
        schedule = [
            row
            for row in read_rows(local, "schedule", season)
            if row.get("status") == "final"
        ]
        schedule = sorted(schedule, key=lambda row: (row["game_date"], row["game_id"]))
        logs = {
            (row["game_id"], int(row["player_id"])): row
            for row in read_rows(local, "player_game_logs", season)
        }
        for row in schedule:
            if max_games is not None and games >= max_games:
                break
            # Need prior games in DATA_DIR so projections are meaningful.
            # Require at least one earlier final in this season so the walk-forward
            # slate uses current-season rotations rather than ancient fallbacks only.
            prior_same_season = any(item["game_date"] < row["game_date"] for item in schedule)
            if not prior_same_season:
                continue
            try:
                projection = build_game_projections(
                    local,
                    season=season,
                    game_id=str(row["game_id"]),
                    as_of=row["game_date"],
                )
            except ValueError:
                continue
            home_n = sum(1 for player in projection.players if player.home_away == "H")
            away_n = sum(1 for player in projection.players if player.home_away == "A")
            if home_n < 5 or away_n < 5:
                continue
            try:
                sim = simulate_game(projection, runs=runs, seed=seed + games, config=config)
            except ValueError:
                continue
            summary = summarize_game(projection, sim)
            del sim
            home_probs.append(summary.home_win_prob)
            home_wins.append(1.0 if int(row["home_pts"]) > int(row["away_pts"]) else 0.0)
            for player in summary.players:
                actual = logs.get((summary.game_id, player.player_id))
                if actual is None:
                    continue
                pred_pts.append(player.stats["pts"].mean)
                act_pts.append(float(actual["pts"]))
                pred_reb.append(player.stats["reb"].mean)
                act_reb.append(float(actual["reb"]))
                pred_ast.append(player.stats["ast"].mean)
                act_ast.append(float(actual["ast"]))
                pred_min.append(player.stats["min"].mean)
                act_min.append(float(actual["minutes"]))
                inside = (
                    float(actual["pts"]) >= player.stats["pts"].p10
                    and float(actual["pts"]) <= player.stats["pts"].p90
                )
                cover_hits.append(1.0 if inside else 0.0)
            games += 1
        if max_games is not None and games >= max_games:
            break

    probs = np.asarray(home_probs, dtype=float)
    outcomes = np.asarray(home_wins, dtype=float)
    return MetricReport(
        games=games,
        player_rows=len(act_pts),
        brier_win=brier_score(probs, outcomes),
        mae_pts=mean_abs_error(np.asarray(pred_pts), np.asarray(act_pts)),
        mae_reb=mean_abs_error(np.asarray(pred_reb), np.asarray(act_reb)),
        mae_ast=mean_abs_error(np.asarray(pred_ast), np.asarray(act_ast)),
        mae_min=mean_abs_error(np.asarray(pred_min), np.asarray(act_min)),
        coverage_10_90=float(np.mean(cover_hits)) if cover_hits else float("nan"),
        calibration_bins=calibration_bins(probs, outcomes),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Walk-forward backtest evaluation.")
    parser.add_argument(
        "--seasons",
        required=True,
        help="One season (2024-25) or a start-year span (2023-2025).",
    )
    parser.add_argument("--runs", type=int, default=500)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-games", type=int)
    parser.add_argument(
        "--out-dir",
        help="Directory for metrics.json and calibration.svg. Default: results/backtest.",
    )
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        seasons = parse_seasons(args.seasons)
        report = evaluate_seasons(
            settings,
            seasons,
            runs=args.runs,
            seed=args.seed,
            max_games=args.max_games,
        )
        out_dir = Path(args.out_dir) if args.out_dir else settings.repo_root / "results" / "backtest"
        out_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = out_dir / "metrics.json"
        metrics_path.write_text(json.dumps(report.as_dict(), indent=2) + "\n", encoding="utf-8")
        svg_path = out_dir / "calibration.svg"
        write_calibration_svg(report.calibration_bins, svg_path)
        print(json.dumps(report.as_dict(), indent=2))
        print(f"wrote {metrics_path}")
        print(f"wrote {svg_path}")
        finish_run(settings)
    except NbaSimError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
