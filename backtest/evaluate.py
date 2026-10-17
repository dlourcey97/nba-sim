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
    crps_from_samples,
    log_loss,
    mean_abs_error,
    pit_from_samples,
    write_calibration_svg,
)
from ingest.parse import parse_seasons
from nba_sim.errors import NbaSimError
from nba_sim.settings import load_settings
from nba_sim.storage import finish_run, read_rows
from outputs.summarize import summarize_game
from projections.blend import available_season_window, load_season_bundle
from projections.build import ProjectionCache, build_game_projections
from sim.engine import simulate_game


def evaluate_seasons(
    settings,
    seasons: list[str],
    *,
    runs: int = 500,
    seed: int = 0,
    max_games: int | None = None,
    config_override: dict | None = None,
    progress_every: int = 50,
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
    pred_fg3m: list[float] = []
    act_fg3m: list[float] = []
    pred_min: list[float] = []
    act_min: list[float] = []
    cover_hits: list[float] = []
    crps_pts_vals: list[float] = []
    pit_pts_vals: list[float] = []
    sim_team_pts: list[float] = []
    act_team_pts: list[float] = []
    sim_poss: list[float] = []
    act_poss: list[float] = []
    games = 0

    # Cache season bundles once across the whole evaluation so walk-forward does
    # not re-read Parquet for every game.
    seasons_back = list(config["blending"]["season_weights"]["seasons_back"])
    needed: set[str] = set()
    for season in seasons:
        window = available_season_window(local, season, seasons_back)
        needed.update(window)
        needed.add(season)
    bundle_cache = {
        label: load_season_bundle(local, label) for label in sorted(needed)
    }

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
        team_results = {
            (row["game_id"], int(row["team_id"])): row
            for row in read_rows(local, "team_game_results", season)
        }
        window = available_season_window(local, season, seasons_back)
        if season not in window:
            window = [season] + window
        bundles = [bundle_cache[label] for label in window if label in bundle_cache]
        proj_cache = ProjectionCache()
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
                    bundles=bundles,
                    cache=proj_cache,
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
            sim_team_pts.append(float(summary.home_pts.mean))
            sim_team_pts.append(float(summary.away_pts.mean))
            act_team_pts.append(float(row["home_pts"]))
            act_team_pts.append(float(row["away_pts"]))
            sim_poss.append(float(sim.home_possessions))
            sim_poss.append(float(sim.away_possessions))
            home_tr = team_results.get((summary.game_id, int(projection.home_team_id)))
            away_tr = team_results.get((summary.game_id, int(projection.away_team_id)))
            if home_tr is not None and home_tr.get("pace") is not None:
                act_poss.append(float(home_tr["pace"]))
            else:
                act_poss.append(float(sim.home_possessions))
            if away_tr is not None and away_tr.get("pace") is not None:
                act_poss.append(float(away_tr["pace"]))
            else:
                act_poss.append(float(sim.away_possessions))
            home_probs.append(summary.home_win_prob)
            home_wins.append(1.0 if int(row["home_pts"]) > int(row["away_pts"]) else 0.0)
            id_to_idx = {int(pid): index for index, pid in enumerate(sim.player_ids)}
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
                pred_fg3m.append(player.stats["fg3m"].mean)
                act_fg3m.append(float(actual["fg3m"]))
                pred_min.append(player.stats["min"].mean)
                act_min.append(float(actual["minutes"]))
                inside = (
                    float(actual["pts"]) >= player.stats["pts"].p10
                    and float(actual["pts"]) <= player.stats["pts"].p90
                )
                cover_hits.append(1.0 if inside else 0.0)
                idx = id_to_idx.get(int(player.player_id))
                if idx is not None:
                    samples = sim.pts[idx]
                    y_pts = float(actual["pts"])
                    crps_pts_vals.append(crps_from_samples(samples, y_pts))
                    pit_pts_vals.append(pit_from_samples(samples, y_pts))
            del sim
            games += 1
            if progress_every and games % progress_every == 0:
                print(f"evaluated {games} games...", flush=True)
        if max_games is not None and games >= max_games:
            break

    probs = np.asarray(home_probs, dtype=float)
    outcomes = np.asarray(home_wins, dtype=float)
    return MetricReport(
        games=games,
        player_rows=len(act_pts),
        brier_win=brier_score(probs, outcomes),
        log_loss_win=log_loss(probs, outcomes),
        mae_pts=mean_abs_error(np.asarray(pred_pts), np.asarray(act_pts)),
        mae_reb=mean_abs_error(np.asarray(pred_reb), np.asarray(act_reb)),
        mae_ast=mean_abs_error(np.asarray(pred_ast), np.asarray(act_ast)),
        mae_fg3m=mean_abs_error(np.asarray(pred_fg3m), np.asarray(act_fg3m)),
        mae_min=mean_abs_error(np.asarray(pred_min), np.asarray(act_min)),
        crps_pts=float(np.mean(crps_pts_vals)) if crps_pts_vals else float("nan"),
        pit_pts_mean=float(np.mean(pit_pts_vals)) if pit_pts_vals else float("nan"),
        coverage_10_90=float(np.mean(cover_hits)) if cover_hits else float("nan"),
        calibration_bins=calibration_bins(probs, outcomes),
        sim_ppg=float(np.mean(sim_team_pts)) if sim_team_pts else float("nan"),
        actual_ppg=float(np.mean(act_team_pts)) if act_team_pts else float("nan"),
        sim_possessions=float(np.mean(sim_poss)) if sim_poss else float("nan"),
        actual_possessions=float(np.mean(act_poss)) if act_poss else float("nan"),
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
