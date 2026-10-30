"""Walk-forward evaluation using only data available before each game."""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.metrics import (
    MetricReport,
    brier_score,
    calibration_bins,
    log_loss,
    mean_abs_error,
    write_calibration_svg,
)
from backtest.sim_job import score_projected_game
from ingest.parse import parse_seasons
from nba_sim.errors import NbaSimError
from nba_sim.settings import load_settings
from nba_sim.storage import finish_run, read_rows
from projections.blend import available_season_window, load_season_bundle
from projections.build import ProjectionCache, build_game_projections


def evaluate_seasons(
    settings,
    seasons: list[str],
    *,
    runs: int = 500,
    seed: int = 0,
    max_games: int | None = None,
    config_override: dict | None = None,
    progress_every: int = 50,
    workers: int = 1,
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
    pred_stl: list[float] = []
    act_stl: list[float] = []
    pred_blk: list[float] = []
    act_blk: list[float] = []
    pred_tov: list[float] = []
    act_tov: list[float] = []
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
    pred_margin: list[float] = []
    act_margin: list[float] = []
    pred_total: list[float] = []
    act_total: list[float] = []
    games = 0
    game_rows: list[dict] = []

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
        logs_by_game: dict[object, dict[int, dict]] = {}
        for record in read_rows(local, "player_game_logs", season):
            logs_by_game.setdefault(record["game_id"], {})[int(record["player_id"])] = record
        team_results = {
            (row["game_id"], int(row["team_id"])): row
            for row in read_rows(local, "team_game_results", season)
        }
        window = available_season_window(local, season, seasons_back)
        if season not in window:
            window = [season] + window
        bundles = [bundle_cache[label] for label in window if label in bundle_cache]
        proj_cache = ProjectionCache()
        pending: list[dict] = []
        batch_size = max(int(workers), 1)
        pool = (
            ProcessPoolExecutor(max_workers=int(workers))
            if int(workers) > 1
            else None
        )

        def _flush() -> None:
            nonlocal games
            if not pending:
                return
            if pool is None:
                scored = [score_projected_game(item) for item in pending]
            else:
                scored = list(pool.map(score_projected_game, pending, chunksize=1))
            pending.clear()
            for item in scored:
                _absorb(item)
                games += 1
                if progress_every and games % progress_every == 0:
                    print(f"evaluated {games} games...", flush=True)

        def _absorb(item: dict) -> None:
            game_rows.append(
                {
                    "game_id": item["game_id"],
                    "game_date": item["game_date"],
                    "home_win_prob": item["home_win_prob"],
                    "home_win": item["home_win"],
                    "pred_margin": item["pred_margin"],
                    "act_margin": item["act_margin"],
                    "pred_total": item["pred_total"],
                    "act_total": item["act_total"],
                }
            )
            home_probs.append(item["home_win_prob"])
            home_wins.append(item["home_win"])
            pred_margin.append(item["pred_margin"])
            act_margin.append(item["act_margin"])
            pred_total.append(item["pred_total"])
            act_total.append(item["act_total"])
            sim_team_pts.extend(item["sim_team_pts"])
            act_team_pts.extend(item["act_team_pts"])
            sim_poss.extend(item["sim_poss"])
            act_poss.extend(item["act_poss"])
            pred_pts.extend(item["pred_pts"])
            act_pts.extend(item["act_pts"])
            pred_reb.extend(item["pred_reb"])
            act_reb.extend(item["act_reb"])
            pred_ast.extend(item["pred_ast"])
            act_ast.extend(item["act_ast"])
            pred_stl.extend(item["pred_stl"])
            act_stl.extend(item["act_stl"])
            pred_blk.extend(item["pred_blk"])
            act_blk.extend(item["act_blk"])
            pred_tov.extend(item["pred_tov"])
            act_tov.extend(item["act_tov"])
            pred_fg3m.extend(item["pred_fg3m"])
            act_fg3m.extend(item["act_fg3m"])
            pred_min.extend(item["pred_min"])
            act_min.extend(item["act_min"])
            cover_hits.extend(item["cover_hits"])
            crps_pts_vals.extend(item["crps_pts"])
            pit_pts_vals.extend(item["pit_pts"])

        try:
            for row in schedule:
                if max_games is not None and games + len(pending) >= max_games:
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
                game_logs = logs_by_game.get(row["game_id"], {})
                game_seed = seed + games + len(pending)
                pending.append(
                    {
                        "projection": projection,
                        "runs": runs,
                        "seed": game_seed,
                        "config": config,
                        "logs": game_logs,
                        "home_tr": team_results.get((row["game_id"], int(projection.home_team_id))),
                        "away_tr": team_results.get((row["game_id"], int(projection.away_team_id))),
                        "home_pts": row["home_pts"],
                        "away_pts": row["away_pts"],
                    }
                )
                if len(pending) >= batch_size:
                    _flush()
            _flush()
        finally:
            if pool is not None:
                pool.shutdown()

    probs = np.asarray(home_probs, dtype=float)
    outcomes = np.asarray(home_wins, dtype=float)
    if probs.size:
        # Prefer home when P(home)>=0.5; ties (exactly 0.5) count as home picks.
        picks = (probs >= 0.5).astype(float)
        winner_accuracy = float(np.mean(picks == outcomes))
    else:
        winner_accuracy = float("nan")
    return MetricReport(
        games=games,
        player_rows=len(act_pts),
        brier_win=brier_score(probs, outcomes),
        log_loss_win=log_loss(probs, outcomes),
        mae_pts=mean_abs_error(np.asarray(pred_pts), np.asarray(act_pts)),
        mae_reb=mean_abs_error(np.asarray(pred_reb), np.asarray(act_reb)),
        mae_ast=mean_abs_error(np.asarray(pred_ast), np.asarray(act_ast)),
        mae_stl=mean_abs_error(np.asarray(pred_stl), np.asarray(act_stl)),
        mae_blk=mean_abs_error(np.asarray(pred_blk), np.asarray(act_blk)),
        mae_tov=mean_abs_error(np.asarray(pred_tov), np.asarray(act_tov)),
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
        mae_margin=mean_abs_error(np.asarray(pred_margin), np.asarray(act_margin)),
        mae_total=mean_abs_error(np.asarray(pred_total), np.asarray(act_total)),
        winner_accuracy=winner_accuracy,
        game_rows=game_rows,
    )


def _write_game_rows(path: Path, rows: list[dict]) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.Table.from_pylist(rows) if rows else pa.table(
        {
            "game_id": pa.array([], type=pa.string()),
            "game_date": pa.array([], type=pa.string()),
            "home_win_prob": pa.array([], type=pa.float64()),
            "home_win": pa.array([], type=pa.float64()),
            "pred_margin": pa.array([], type=pa.float64()),
            "act_margin": pa.array([], type=pa.float64()),
            "pred_total": pa.array([], type=pa.float64()),
            "act_total": pa.array([], type=pa.float64()),
        }
    )
    pq.write_table(table, path, compression="zstd")


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
        "--workers",
        type=int,
        default=os.cpu_count() or 1,
        help="Parallel games. Projections stay in schedule order; simulations use one thread each.",
    )
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
            workers=max(1, args.workers),
        )
        out_dir = Path(args.out_dir) if args.out_dir else settings.repo_root / "results" / "backtest"
        out_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = out_dir / "metrics.json"
        metrics_path.write_text(json.dumps(report.as_dict(), indent=2) + "\n", encoding="utf-8")
        games_path = out_dir / "games.parquet"
        _write_game_rows(games_path, report.game_rows or [])
        svg_path = out_dir / "calibration.svg"
        write_calibration_svg(report.calibration_bins, svg_path)
        print(json.dumps(report.as_dict(), indent=2))
        print(f"wrote {metrics_path}")
        print(f"wrote {games_path}")
        print(f"wrote {svg_path}")
        finish_run(settings)
    except NbaSimError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
