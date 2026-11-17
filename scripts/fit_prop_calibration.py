"""Walk-forward prop calibration. Fit on 2025-26, validate on 2024-25.

Pre-tip projections only. Saves percentile curves, not raw draws. 1,000 sims,
seed 1. A season parquet that already exists is not resimulated.
"""

from __future__ import annotations

import json
import math
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pyarrow as pa
import pyarrow.parquet as pq

from backtest.sim_job import CALIBRATION_STATS, calibration_rows
from nba_sim.settings import load_settings
from nba_sim.storage import read_rows
from outputs.calibration import KNOTS_PATH, fit_isotonic, judge_quality, reliability
from outputs.edge_plays import p_over
from outputs.summarize import StatSummary
from projections.blend import available_season_window
from projections.build import ProjectionCache, build_game_projections

RUNS = 1000
SEED = 1
WORKERS = 4
SEASONS = ("2025-26", "2024-25")
FIT_SEASON = "2025-26"
HOLDOUT = "2024-25"


def _out(season: str) -> Path:
    label = season.replace("-", "_")
    return ROOT / "results" / "backtest" / f"calibration_{label}_1000.parquet"


def _nearest_line(value: float) -> float:
    lower = math.floor(value) + 0.5
    if lower > value:
        lower -= 1.0
    upper = lower + 1.0
    if abs(value - lower) <= abs(value - upper):
        return max(0.5, lower)
    return upper


def _curve(row: dict, stat: str) -> StatSummary:
    return StatSummary(
        mean=float(row[f"{stat}_mean"]),
        p10=float(row[f"{stat}_p10"]),
        p25=float(row[f"{stat}_p25"]),
        p50=float(row[f"{stat}_p50"]),
        p75=float(row[f"{stat}_p75"]),
        p90=float(row[f"{stat}_p90"]),
    )


def _assign_tiers(rows: list[dict]) -> None:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_date[str(row["game_date"])[:10]].append(row)
    for group in by_date.values():
        ranked = sorted(group, key=lambda item: float(item["usage"]), reverse=True)
        top = {id(item) for item in ranked[:30]}
        for item in group:
            if id(item) in top:
                item["tier"] = "top"
            elif item.get("started") or int(item.get("depth_rank") or 99) <= 5:
                item["tier"] = "starter"
            else:
                item["tier"] = "bench"


def _pairs(rows: list[dict], stat: str, tier: str) -> list[tuple[float, float]]:
    pairs = []
    for row in rows:
        if row.get("tier") != tier:
            continue
        games = int(row.get("prior_games") or 0)
        prior = row.get(f"{stat}_prior")
        prior_ok = prior is not None and prior == prior
        anchor = float(prior) if games >= 5 and prior_ok else float(row[f"{stat}_mean"])
        if anchor < 0.4:
            continue
        line = _nearest_line(anchor)
        pred = p_over(line, _curve(row, stat))
        hit = 1.0 if float(row[f"{stat}_actual"]) > line else 0.0
        pairs.append((pred, hit))
    return pairs


def fit_from_parquets() -> dict:
    fit_rows = pq.read_table(_out(FIT_SEASON)).to_pylist()
    hold_rows = pq.read_table(_out(HOLDOUT)).to_pylist()
    _assign_tiers(fit_rows)
    _assign_tiers(hold_rows)
    cells = []
    for stat in CALIBRATION_STATS:
        for tier in ("top", "starter", "bench"):
            train = _pairs(fit_rows, stat, tier)
            hold = _pairs(hold_rows, stat, tier)
            xs, ys = fit_isotonic(train)
            scored = reliability(hold, xs, ys)
            quality = judge_quality(scored)
            cells.append(
                {
                    "stat": stat,
                    "tier": tier,
                    "xs": list(xs),
                    "ys": list(ys),
                    "quality": quality,
                    "fit_n": len(train),
                    "holdout_n": int(scored["n"]),
                    "holdout_brier_raw": scored["brier_raw"],
                    "holdout_brier_cal": scored["brier_cal"],
                    "holdout_bias": scored["bias"],
                }
            )
            print(
                f"{stat:5} {tier:8} fit={len(train):5d} hold={int(scored['n']):5d} "
                f"brier {scored['brier_raw']:.4f}->{scored['brier_cal']:.4f} "
                f"bias {scored['bias']:+.3f} {quality}",
                flush=True,
            )
    payload = {
        "source": f"fit {FIT_SEASON}, holdout {HOLDOUT}, {RUNS} sims, seed {SEED}",
        "cells": cells,
    }
    KNOTS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE {KNOTS_PATH}", flush=True)
    return payload


def _sample_season(settings, season: str) -> None:
    path = _out(season)
    done_flag = path.with_suffix(".done")
    if path.exists() and done_flag.exists():
        print(f"SKIP {path.name}", flush=True)
        return
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    config = settings.config
    local = settings
    seasons_back = list(config["blending"]["season_weights"]["seasons_back"])
    window = available_season_window(local, season, seasons_back)
    if season not in window:
        window = [season] + window
    bundles = []
    for label in window:
        from projections.blend import load_season_bundle

        bundles.append(load_season_bundle(local, label))
    schedule = sorted(
        (row for row in read_rows(local, "schedule", season) if row.get("status") == "final"),
        key=lambda row: (row["game_date"], row["game_id"]),
    )
    logs_by_game: dict[object, dict[int, dict]] = {}
    for record in read_rows(local, "player_game_logs", season):
        logs_by_game.setdefault(record["game_id"], {})[int(record["player_id"])] = record
    cache = ProjectionCache()
    entering: dict[int, dict] = {}
    pending: list[dict] = []
    writer: pq.ParquetWriter | None = None
    done = 0
    pool = ProcessPoolExecutor(max_workers=WORKERS)

    def _flush() -> None:
        nonlocal writer, done
        if not pending:
            return
        scored = list(pool.map(calibration_rows, pending, chunksize=1))
        pending.clear()
        flat = [row for batch in scored for row in batch]
        done += len(scored)
        if flat:
            table = pa.Table.from_pylist(flat)
            if writer is None:
                writer = pq.ParquetWriter(path, table.schema)
            writer.write_table(table)
        if done % 20 < WORKERS:
            print(f"{season} games {done}", flush=True)

    try:
        first_date = schedule[0]["game_date"] if schedule else None
        for index, row in enumerate(schedule):
            game_logs = logs_by_game.get(row["game_id"], {})
            if row["game_date"] == first_date:
                _record_logs(entering, game_logs)
                continue
            try:
                projection = build_game_projections(
                    local,
                    season=season,
                    game_id=str(row["game_id"]),
                    as_of=row["game_date"],
                    bundles=bundles,
                    cache=cache,
                )
            except ValueError:
                _record_logs(entering, game_logs)
                continue
            home_n = sum(1 for player in projection.players if player.home_away == "H")
            away_n = sum(1 for player in projection.players if player.home_away == "A")
            if home_n < 5 or away_n < 5:
                _record_logs(entering, game_logs)
                continue
            snapshot = _snapshot(entering)
            pending.append(
                {
                    "projection": projection,
                    "runs": RUNS,
                    "seed": SEED + index,
                    "config": config,
                    "logs": game_logs,
                    "season": season,
                    "game_id": str(row["game_id"]),
                    "game_date": str(row["game_date"])[:10],
                    "usage": {int(p.player_id): float(p.rates.usage) for p in projection.players},
                    "started": {int(p.player_id): bool(p.started) for p in projection.players},
                    "depth": {int(p.player_id): int(p.depth_rank) for p in projection.players},
                    "entering": snapshot,
                }
            )
            _record_logs(entering, game_logs)
            if len(pending) >= WORKERS:
                _flush()
        _flush()
    finally:
        pool.shutdown()
        if writer is not None:
            writer.close()
    done_flag.write_text(f"games={done}\n", encoding="utf-8")
    print(f"FINISHED {path.name} games={done}", flush=True)


def _record_logs(entering: dict[int, dict], game_logs: dict) -> None:
    for pid, actual in game_logs.items():
        if float(actual.get("minutes") or 0.0) <= 0.0:
            continue
        state = entering.setdefault(int(pid), {"games": 0, **{stat: 0.0 for stat in CALIBRATION_STATS}})
        state["games"] += 1
        for stat in CALIBRATION_STATS:
            if stat == "pra":
                value = (
                    float(actual.get("pts") or 0.0)
                    + float(actual.get("reb") or 0.0)
                    + float(actual.get("ast") or 0.0)
                )
            else:
                value = float(actual.get(stat) or 0.0)
            state[stat] += value


def _snapshot(entering: dict[int, dict]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for pid, state in entering.items():
        games = int(state["games"])
        copied: dict = {"games": games}
        for stat in CALIBRATION_STATS:
            copied[stat] = (float(state[stat]) / games) if games else None
        out[int(pid)] = copied
    return out


def main() -> None:
    fit_only = "--fit-only" in sys.argv
    if not fit_only:
        settings = load_settings()
        for season in SEASONS:
            _sample_season(settings, season)
    fit_from_parquets()


if __name__ == "__main__":
    main()
