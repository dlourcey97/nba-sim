"""Walk-forward evaluation using only data available before each game."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
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
from backtest.zero_causes import CauseIndex, count_causes
from ingest.injury_archive import load_injury_index
from ingest.parse import parse_seasons
from nba_sim.errors import NbaSimError
from nba_sim.settings import load_settings
from nba_sim.storage import finish_run, read_rows
from projections.blend import available_season_window, load_season_bundle
from projections.build import ProjectionCache, build_game_projections


def _entering_ppg(logs_by_game: dict, schedule: list[dict]) -> dict:
    """Points per game from games strictly before this one, minutes at least 8."""
    running: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
    out: dict = {}
    for row in schedule:
        gid = row["game_id"]
        game_logs = logs_by_game.get(gid, {})
        snap = {}
        for pid in game_logs:
            games, pts = running[int(pid)]
            if games >= 8:
                snap[int(pid)] = pts / games
        out[gid] = snap
        for pid, rec in game_logs.items():
            if float(rec.get("minutes") or 0.0) < 8:
                continue
            games, pts = running[int(pid)]
            running[int(pid)] = [games + 1.0, pts + float(rec.get("pts") or 0.0)]
    return out


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
    projected_zero_played = 0
    projected_eight_dnp = 0
    cause_a = cause_b = cause_c = cause_d = cause_e = 0
    crps_min_sum = 0.0
    crps_pts_sum = 0.0
    played_for_crps = 0
    cover_min_hits = 0.0
    cover_pts_hits = 0.0
    cover_star_hits = 0.0
    cover_star_n = 0
    cover_bench_hits = 0.0
    cover_bench_n = 0
    star_bust = 0
    star_bust_draws = 0
    star_actual_bust = 0
    star_n = 0
    star_pred_sum = 0.0
    star_med_sum = 0.0
    star_act_sum = 0.0
    cover_star_hits = 0.0
    cover_star_n = 0
    cover_bench_hits = 0.0
    cover_bench_n = 0
    star_bust = 0
    star_bust_draws = 0
    star_actual_bust = 0
    star_n = 0
    star_pred_sum = 0.0
    star_med_sum = 0.0
    star_act_sum = 0.0
    play_brier_sum = 0.0
    play_n = 0
    play_bin_count = [0] * 10
    play_bin_pred = [0.0] * 10
    play_bin_played = [0] * 10
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
    injury_index = (
        load_injury_index(local)
        if bool((config.get("context") or {}).get("injury_archive_enabled", False))
        else None
    )

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
        entering_ppg = _entering_ppg(logs_by_game, schedule)
        team_results = {
            (row["game_id"], int(row["team_id"])): row
            for row in read_rows(local, "team_game_results", season)
        }
        roster_rows = read_rows(local, "team_rosters", season)
        window = available_season_window(local, season, seasons_back)
        if season not in window:
            window = [season] + window
        bundles = [bundle_cache[label] for label in window if label in bundle_cache]
        cause_index = CauseIndex(schedule, bundles, season)
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
            nonlocal crps_min_sum, crps_pts_sum, played_for_crps
            nonlocal cover_min_hits, cover_pts_hits, play_brier_sum, play_n
            nonlocal cover_star_hits, cover_star_n, cover_bench_hits, cover_bench_n
            nonlocal star_bust, star_bust_draws, star_actual_bust, star_n
            nonlocal star_pred_sum, star_med_sum, star_act_sum
            nonlocal cover_star_hits, cover_star_n, cover_bench_hits, cover_bench_n
            nonlocal star_bust, star_bust_draws, star_actual_bust, star_n
            nonlocal star_pred_sum, star_med_sum, star_act_sum
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
                    "pred_home_pts": item.get("pred_home_pts"),
                    "pred_away_pts": item.get("pred_away_pts"),
                    "act_home_pts": item.get("act_home_pts"),
                    "act_away_pts": item.get("act_away_pts"),
                    "crps_min_sum": item.get("crps_min_sum", 0.0),
                    "crps_pts_sum": item.get("crps_pts_sum", 0.0),
                    "played_n": item.get("played_n", 0),
                    "cover_min_hits": item.get("cover_min_hits", 0.0),
                    "cover_pts_hits": item.get("cover_pts_hits", 0.0),
                    "play_brier_sum": item.get("play_brier_sum", 0.0),
                    "play_n": item.get("play_n", 0),
                    "play_bins": item.get("play_bins") or [],
                }
            )
            crps_min_sum += float(item.get("crps_min_sum") or 0.0)
            crps_pts_sum += float(item.get("crps_pts_sum") or 0.0)
            played_for_crps += int(item.get("played_n") or 0)
            cover_min_hits += float(item.get("cover_min_hits") or 0.0)
            cover_pts_hits += float(item.get("cover_pts_hits") or 0.0)
            cover_star_hits += float(item.get("cover_star_hits") or 0.0)
            cover_star_n += int(item.get("cover_star_n") or 0)
            cover_bench_hits += float(item.get("cover_bench_hits") or 0.0)
            cover_bench_n += int(item.get("cover_bench_n") or 0)
            star_bust += int(item.get("star_bust") or 0)
            star_bust_draws += int(item.get("star_bust_draws") or 0)
            star_actual_bust += int(item.get("star_actual_bust") or 0)
            star_n += int(item.get("star_n") or 0)
            star_pred_sum += float(item.get("star_pred_sum") or 0.0)
            star_med_sum += float(item.get("star_med_sum") or 0.0)
            star_act_sum += float(item.get("star_act_sum") or 0.0)
            play_brier_sum += float(item.get("play_brier_sum") or 0.0)
            play_n += int(item.get("play_n") or 0)
            for slot, row in enumerate(item.get("play_bins") or []):
                if slot >= 10:
                    break
                play_bin_count[slot] += int(row.get("count") or 0)
                play_bin_pred[slot] += float(row.get("pred_sum") or 0.0)
                play_bin_played[slot] += int(row.get("played") or 0)
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
                injuries = []
                if injury_index is not None:
                    when = row["game_date"]
                    when_key = when.isoformat() if hasattr(when, "isoformat") else str(when)[:10]
                    matchup = f"{row['away_abbr']}@{row['home_abbr']}"
                    injuries = injury_index.get((when_key, matchup), [])
                try:
                    projection = build_game_projections(
                        local,
                        season=season,
                        game_id=str(row["game_id"]),
                        as_of=row["game_date"],
                        bundles=bundles,
                        cache=proj_cache,
                        injuries=injuries,
                    )
                except ValueError:
                    continue
                home_n = sum(1 for player in projection.players if player.home_away == "H")
                away_n = sum(1 for player in projection.players if player.home_away == "A")
                if home_n < 5 or away_n < 5:
                    continue
                game_logs = logs_by_game.get(row["game_id"], {})
                zero_played, eight_dnp = _minute_miss_counts(projection, game_logs)
                projected_zero_played += zero_played
                projected_eight_dnp += eight_dnp
                a, b, c, d, e = count_causes(
                    projection,
                    game_logs,
                    logs_by_game,
                    roster_rows,
                    cause_index,
                )
                cause_a += a
                cause_b += b
                cause_c += c
                cause_d += d
                cause_e += e
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
                        "season_ppg": entering_ppg.get(row["game_id"], {}),
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
        crps_pts=(crps_pts_sum / played_for_crps) if played_for_crps else float("nan"),
        pit_pts_mean=float(np.mean(pit_pts_vals)) if pit_pts_vals else float("nan"),
        coverage_10_90=(cover_pts_hits / played_for_crps) if played_for_crps else float("nan"),
        crps_min=(crps_min_sum / played_for_crps) if played_for_crps else float("nan"),
        coverage_min_10_90=(cover_min_hits / played_for_crps) if played_for_crps else float("nan"),
        coverage_pts_10_90=(cover_pts_hits / played_for_crps) if played_for_crps else float("nan"),
        coverage_star_pts=(cover_star_hits / cover_star_n) if cover_star_n else float("nan"),
        coverage_bench_pts=(cover_bench_hits / cover_bench_n) if cover_bench_n else float("nan"),
        star_bust_rate=(star_bust / star_bust_draws) if star_bust_draws else float("nan"),
        star_actual_bust_rate=(star_actual_bust / star_n) if star_n else float("nan"),
        star_pred_mean=(star_pred_sum / star_n) if star_n else float("nan"),
        star_med_mean=(star_med_sum / star_n) if star_n else float("nan"),
        star_act_mean=(star_act_sum / star_n) if star_n else float("nan"),
        star_players=star_n,
        play_brier=(play_brier_sum / play_n) if play_n else float("nan"),
        play_bins=[
            {
                "bin_left": index / 10.0,
                "bin_right": (index + 1) / 10.0,
                "count": float(play_bin_count[index]),
                "pred_mean": (
                    play_bin_pred[index] / play_bin_count[index]
                    if play_bin_count[index]
                    else float("nan")
                ),
                "actual_freq": (
                    play_bin_played[index] / play_bin_count[index]
                    if play_bin_count[index]
                    else float("nan")
                ),
            }
            for index in range(10)
        ],
        calibration_bins=calibration_bins(probs, outcomes),
        sim_ppg=float(np.mean(sim_team_pts)) if sim_team_pts else float("nan"),
        actual_ppg=float(np.mean(act_team_pts)) if act_team_pts else float("nan"),
        sim_possessions=float(np.mean(sim_poss)) if sim_poss else float("nan"),
        actual_possessions=float(np.mean(act_poss)) if act_poss else float("nan"),
        mae_margin=mean_abs_error(np.asarray(pred_margin), np.asarray(act_margin)),
        mae_total=mean_abs_error(np.asarray(pred_total), np.asarray(act_total)),
        winner_accuracy=winner_accuracy,
        projected_zero_played=projected_zero_played,
        projected_eight_dnp=projected_eight_dnp,
        cause_a=cause_a,
        cause_b=cause_b,
        cause_c=cause_c,
        cause_d=cause_d,
        cause_e=cause_e,
        game_rows=game_rows,
    )


def _minute_miss_counts(projection, logs: dict) -> tuple[int, int]:
    """(projected 0 and played 8+, projected 8+ and did not play).

    The projection is expected minutes: conditional mean times P(plays).
    A box-score player missing from the projection counts as 0. A player we
    expect to play 8 or more who has no log row counts as a DNP.
    """
    expected_by_id: dict[int, float] = {}
    for player in projection.players:
        if player.minutes.out or float(player.minutes.play_prob) <= 0.0:
            expected = 0.0
        else:
            expected = float(player.minutes.mean) * float(player.minutes.play_prob)
        expected_by_id[int(player.player_id)] = expected
    zero = 0
    dnp = 0
    seen: set[int] = set()
    for pid, row in logs.items():
        actual = float(row.get("minutes") or 0.0)
        seen.add(int(pid))
        expected = expected_by_id.get(int(pid), 0.0)
        if expected < 0.5 and actual >= 8.0:
            zero += 1
        if expected >= 8.0 and actual < 0.5:
            dnp += 1
    for pid, expected in expected_by_id.items():
        if pid not in seen and expected >= 8.0:
            dnp += 1
    return zero, dnp


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
