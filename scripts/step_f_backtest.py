"""Walk-forward Step F vs baseline comparison (single pass per config).

Reports MIN MAE (overall / starters / bench), PTS MAE, 10–90 coverage, and a
star-minutes check (top-10 usage players' projected MIN vs prior-season MPG).

Usage:
  PYTHONPATH=. python scripts/step_f_backtest.py --seasons 2025-26 --runs 200 --seed 1 --max-games 250
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

from backtest.metrics import (
    brier_score,
    log_loss,
    mean_abs_error,
)
from ingest.parse import parse_seasons
from nba_sim.settings import load_settings
from nba_sim.storage import finish_run, read_rows
from outputs.summarize import summarize_game
from ingest.rosters import prior_season_label
from projections.blend import available_season_window, load_season_bundle
from projections.build import ProjectionCache, build_game_projections
from sim.engine import simulate_game


def _with_step_f(config: dict, enabled: bool) -> dict:
    cfg = deepcopy(config)
    features = dict(cfg.get("features") or {})
    features["stint_rotations_step_f"] = bool(enabled)
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


def evaluate_step_f(
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
    pred_min: list[float] = []
    act_min: list[float] = []
    pred_min_s: list[float] = []
    act_min_s: list[float] = []
    pred_min_b: list[float] = []
    act_min_b: list[float] = []
    cover_hits: list[float] = []
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
            for player in summary.players:
                actual = logs.get((summary.game_id, player.player_id))
                if actual is None:
                    continue
                pred_pts.append(player.stats["pts"].mean)
                act_pts.append(float(actual["pts"]))
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
        "star_mae_vs_prior_mpg": float(np.mean(star_errs)) if star_errs else None,
        "stars": star_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", default="2025-26")
    parser.add_argument("--runs", type=int, default=200)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-games", type=int, default=250)
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "results" / "backtest" / "upgrade_poss_step_f"),
    )
    args = parser.parse_args(argv)
    settings = load_settings()
    seasons = parse_seasons(args.seasons)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    for label, enabled in (("baseline", False), ("step_f", True)):
        print(f"=== {label} (stint_rotations_step_f={enabled}) ===", flush=True)
        cfg = _with_step_f(settings.config, enabled)
        payload = evaluate_step_f(
            settings,
            seasons,
            runs=args.runs,
            seed=args.seed,
            max_games=args.max_games,
            config=cfg,
        )
        results[label] = payload
        path = out_dir / f"metrics_{label}.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        summary = {
            k: payload[k]
            for k in (
                "games",
                "mae_min",
                "mae_min_starters",
                "mae_min_bench",
                "mae_pts",
                "coverage_10_90",
                "brier_win",
                "star_mae_vs_prior_mpg",
            )
        }
        print(json.dumps(summary, indent=2), flush=True)
        print(f"wrote {path}", flush=True)

    comparison = out_dir / "comparison.json"
    comparison.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {comparison}", flush=True)
    finish_run(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
