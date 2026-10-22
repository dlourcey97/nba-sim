"""Full-season minutes bakeoff: report MIN/PTS/REB/AST MAE, coverage, Brier, margin/total.

Usage:
  PYTHONPATH=. python scripts/minutes_bakeoff.py \\
    --label step_f_on --seasons 2025-26 --runs 1000 --seed 1 \\
    --step-f on --minutes-model engine \\
    --out-dir results/backtest/minutes_bakeoff/step_f_on
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.metrics import brier_score, log_loss, mean_abs_error
from ingest.parse import parse_seasons
from ingest.rosters import prior_season_label
from nba_sim.settings import load_settings
from nba_sim.storage import finish_run, read_rows
from outputs.summarize import summarize_game
from projections.blend import available_season_window, load_season_bundle
from projections.build import ProjectionCache, build_game_projections
from sim.engine import simulate_game


def _apply_flags(config: dict, *, step_f: bool, minutes_model: str, naive_blend: float) -> dict:
    cfg = deepcopy(config)
    features = dict(cfg.get("features") or {})
    features["stint_rotations_step_f"] = bool(step_f)
    features["minutes_model"] = minutes_model
    features["naive_blend"] = float(naive_blend)
    cfg["features"] = features
    return cfg


def _top_usage_stars(settings, prior_season: str, n: int = 10) -> list[dict]:
    try:
        aggs = read_rows(settings, "player_season_aggregates", prior_season)
    except Exception:
        return []
    ranked = sorted(
        aggs,
        key=lambda r: (-float(r.get("usage") or 0.0), -float(r.get("minutes") or 0.0)),
    )
    seen: set[int] = set()
    stars: list[dict] = []
    for row in ranked:
        pid = int(row["player_id"])
        if pid in seen:
            continue
        games = max(int(row.get("games") or 1), 1)
        mpg = float(row.get("minutes") or 0.0) / games
        if mpg < 20:
            continue
        seen.add(pid)
        stars.append(
            {
                "player_id": pid,
                "player_name": str(row.get("player_name") or pid),
                "prior_mpg": mpg,
                "usage": float(row.get("usage") or 0.0),
            }
        )
        if len(stars) >= n:
            break
    return stars


def evaluate(
    settings,
    seasons: list[str],
    *,
    runs: int,
    seed: int,
    max_games: int | None,
    config: dict,
) -> dict:
    local = replace(settings, config=config)
    seasons_back = list(config["blending"]["season_weights"]["seasons_back"])
    needed: set[str] = set()
    for season in seasons:
        window = available_season_window(local, season, seasons_back)
        needed.update(window)
        needed.add(season)
        prior = prior_season_label(season)
        if prior:
            needed.add(prior)
    bundles = {label: load_season_bundle(local, label) for label in sorted(needed)}

    prior0 = prior_season_label(seasons[0]) or seasons[0]
    stars = _top_usage_stars(local, prior0, n=10)
    star_ids = {s["player_id"] for s in stars}
    star_proj: dict[int, list[float]] = {pid: [] for pid in star_ids}

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
    pred_min_s: list[float] = []
    act_min_s: list[float] = []
    pred_min_b: list[float] = []
    act_min_b: list[float] = []
    cover_hits: list[float] = []
    pred_margin: list[float] = []
    act_margin: list[float] = []
    pred_total: list[float] = []
    act_total: list[float] = []
    games = 0
    proj_cache = ProjectionCache()

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
        window = available_season_window(local, season, seasons_back)
        if season not in window:
            window = [season] + window
        season_bundles = [bundles[label] for label in window if label in bundles]
        for row in schedule:
            if max_games is not None and games >= max_games:
                break
            if not any(item["game_date"] < row["game_date"] for item in schedule):
                continue
            try:
                projection = build_game_projections(
                    local,
                    season=season,
                    game_id=str(row["game_id"]),
                    as_of=row["game_date"],
                    bundles=season_bundles,
                    cache=proj_cache,
                )
            except ValueError:
                continue
            home_n = sum(1 for p in projection.players if p.home_away == "H")
            away_n = sum(1 for p in projection.players if p.home_away == "A")
            if home_n < 5 or away_n < 5:
                continue
            for player in projection.players:
                if int(player.player_id) in star_ids:
                    star_proj[int(player.player_id)].append(float(player.minutes.mean))
            try:
                sim = simulate_game(
                    projection, runs=runs, seed=seed + games, config=config
                )
            except ValueError:
                continue
            summary = summarize_game(projection, sim)
            home_probs.append(summary.home_win_prob)
            home_wins.append(1.0 if int(row["home_pts"]) > int(row["away_pts"]) else 0.0)
            pred_margin.append(float(summary.margin.mean))
            act_margin.append(float(row["home_pts"]) - float(row["away_pts"]))
            pred_total.append(float(summary.total.mean))
            act_total.append(float(row["home_pts"]) + float(row["away_pts"]))
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
                if bool(actual.get("started")):
                    pred_min_s.append(player.stats["min"].mean)
                    act_min_s.append(float(actual["minutes"]))
                else:
                    pred_min_b.append(player.stats["min"].mean)
                    act_min_b.append(float(actual["minutes"]))
                inside = (
                    float(actual["pts"]) >= player.stats["pts"].p10
                    and float(actual["pts"]) <= player.stats["pts"].p90
                )
                cover_hits.append(1.0 if inside else 0.0)
            del sim
            games += 1
            if games % 50 == 0:
                print(f"  evaluated {games} games...", flush=True)
        if max_games is not None and games >= max_games:
            break

    star_rows = []
    star_errs = []
    for star in stars:
        samples = star_proj.get(star["player_id"]) or []
        if not samples:
            continue
        pred = float(np.mean(samples))
        err = abs(pred - star["prior_mpg"])
        star_errs.append(err)
        star_rows.append({**star, "proj_mpg": pred, "abs_err": err, "n_games": len(samples)})

    probs = np.asarray(home_probs, dtype=float)
    outcomes = np.asarray(home_wins, dtype=float)
    return {
        "games": games,
        "player_rows": len(act_pts),
        "brier_win": brier_score(probs, outcomes),
        "log_loss_win": log_loss(probs, outcomes),
        "mae_pts": mean_abs_error(np.asarray(pred_pts), np.asarray(act_pts)),
        "mae_reb": mean_abs_error(np.asarray(pred_reb), np.asarray(act_reb)),
        "mae_ast": mean_abs_error(np.asarray(pred_ast), np.asarray(act_ast)),
        "mae_min": mean_abs_error(np.asarray(pred_min), np.asarray(act_min)),
        "mae_min_starters": mean_abs_error(np.asarray(pred_min_s), np.asarray(act_min_s))
        if pred_min_s
        else None,
        "mae_min_bench": mean_abs_error(np.asarray(pred_min_b), np.asarray(act_min_b))
        if pred_min_b
        else None,
        "starter_rows": len(pred_min_s),
        "bench_rows": len(pred_min_b),
        "coverage_10_90": float(np.mean(cover_hits)) if cover_hits else None,
        "mae_margin": mean_abs_error(np.asarray(pred_margin), np.asarray(act_margin)),
        "mae_total": mean_abs_error(np.asarray(pred_total), np.asarray(act_total)),
        "star_mae_vs_prior_mpg": float(np.mean(star_errs)) if star_errs else None,
        "stars": star_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--seasons", default="2025-26")
    parser.add_argument("--runs", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-games", type=int, default=0, help="0 = all games")
    parser.add_argument("--step-f", choices=["on", "off"], default="on")
    parser.add_argument(
        "--minutes-model",
        choices=["engine", "naive_last10", "blend"],
        default="engine",
    )
    parser.add_argument("--naive-blend", type=float, default=0.5)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)

    settings = load_settings()
    cfg = _apply_flags(
        settings.config,
        step_f=(args.step_f == "on"),
        minutes_model=args.minutes_model,
        naive_blend=args.naive_blend,
    )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    max_games = args.max_games if args.max_games > 0 else None

    print(
        f"=== {args.label} step_f={args.step_f} minutes_model={args.minutes_model} "
        f"runs={args.runs} ===",
        flush=True,
    )
    payload = evaluate(
        settings,
        parse_seasons(args.seasons),
        runs=args.runs,
        seed=args.seed,
        max_games=max_games,
        config=cfg,
    )
    payload["label"] = args.label
    payload["step_f"] = args.step_f
    payload["minutes_model"] = args.minutes_model
    payload["naive_blend"] = args.naive_blend
    payload["runs"] = args.runs
    payload["seed"] = args.seed

    path = out_dir / "metrics.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    summary_keys = [
        "games",
        "mae_min",
        "mae_min_starters",
        "mae_min_bench",
        "star_mae_vs_prior_mpg",
        "mae_pts",
        "mae_reb",
        "mae_ast",
        "coverage_10_90",
        "brier_win",
        "mae_margin",
        "mae_total",
    ]
    print(json.dumps({k: payload.get(k) for k in summary_keys}, indent=2), flush=True)
    print(f"wrote {path}", flush=True)
    finish_run(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
