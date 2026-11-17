"""Turn off one random piece at a time and measure the star bust tail.

Sample of the 2025-26 season, pre-tip projections, same seed on every piece.
The star cut matches the published bust check: usage at least 0.24, minutes
mean at least 20, and at least 8 prior games at 12+ points.
"""

from __future__ import annotations

import copy
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

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.evaluate import _entering_ppg
from backtest.sim_job import bust_probe
from nba_sim.settings import load_settings
from nba_sim.storage import read_rows
from projections.blend import available_season_window, load_season_bundle
from projections.build import ProjectionCache, build_game_projections

RUNS = 400
SEED = 1
WORKERS = 4
STRIDE = 16
SEASON = "2025-26"


def _scale_modes(base: dict) -> list[tuple[str, dict, str]]:
    jobs = []
    for scale in (1.0, 0.65, 0.45, 0.25, 0.10):
        config = copy.deepcopy(base)
        config.setdefault("simulation", {})["star_lineup_scale"] = scale
        jobs.append((f"scale_{scale:.2f}", config, "projection"))
    return jobs


def _modes(base: dict) -> list[tuple[str, dict, str]]:
    def sim(name: str, **flags: object) -> tuple[str, dict, str]:
        config = copy.deepcopy(base)
        config.setdefault("simulation", {}).update(flags)
        return name, config, "projection"

    foul = copy.deepcopy(base)
    foul.setdefault("minutes", {})["foul_trouble_rate_prior"] = 0.0
    return [
        sim("baseline"),
        sim("no_shooting", player_shoot_sd=0.0, star_shoot_sd=0.0),
        sim("no_usage", player_usage_sd=0.0, star_usage_sd=0.0),
        sim("no_minutes", freeze_minutes_sd=True),
        ("no_foul", foul, "foul_projection"),
        sim("no_blowout", freeze_blowout=True),
        sim("no_lineup", lineup_temperature=0.05),
        sim("no_play_prob", freeze_play_prob=True),
    ]


def _summarize(rows: list[dict]) -> str:
    draws = sum(row["draws"] for row in rows)
    bust = sum(row["bust"] for row in rows)
    actual_n = len(rows)
    actual_bust = sum(row["actual_bust"] for row in rows)
    mean = sum(row["mean"] for row in rows) / actual_n if actual_n else float("nan")
    actual = sum(row["actual"] for row in rows) / actual_n if actual_n else float("nan")
    rate = bust / draws if draws else float("nan")
    actual_rate = actual_bust / actual_n if actual_n else float("nan")
    return (
        f"bust {rate:.3f} (actual {actual_rate:.3f}) "
        f"mean {mean:.2f} vs {actual:.2f}  n={actual_n} draws={draws}"
    )


def _top30(rows: list[dict]) -> list[dict]:
    by_player: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        by_player[int(row["player_id"])].append(row)
    ranked = sorted(
        by_player,
        key=lambda pid: sum(item["usage"] for item in by_player[pid]) / len(by_player[pid]),
        reverse=True,
    )
    chosen = set(ranked[:30])
    return [row for row in rows if int(row["player_id"]) in chosen]


def main() -> None:
    settings = load_settings()
    config = settings.config
    seasons_back = list(config["blending"]["season_weights"]["seasons_back"])
    window = available_season_window(settings, SEASON, seasons_back)
    if SEASON not in window:
        window = [SEASON] + window
    bundles = [load_season_bundle(settings, label) for label in window]
    schedule = sorted(
        (row for row in read_rows(settings, "schedule", SEASON) if row.get("status") == "final"),
        key=lambda row: (row["game_date"], row["game_id"]),
    )
    logs_by_game: dict[object, dict[int, dict]] = {}
    for record in read_rows(settings, "player_game_logs", SEASON):
        logs_by_game.setdefault(record["game_id"], {})[int(record["player_id"])] = record
    entering = _entering_ppg(logs_by_game, schedule)
    cache = ProjectionCache()
    foul_cache = ProjectionCache()
    foul_config = copy.deepcopy(config)
    foul_config.setdefault("minutes", {})["foul_trouble_rate_prior"] = 0.0
    foul_settings = replace(settings, config=foul_config)
    sweep = "--sweep" in sys.argv
    jobs = _scale_modes(config) if sweep else _modes(config)
    stride = 48 if sweep else STRIDE
    picked = [row for index, row in enumerate(schedule) if index > 200 and index % stride == 0]
    print(f"sample games={len(picked)} runs={RUNS}", flush=True)
    pending: list[dict] = []
    pooled: dict[str, list[dict]] = {name: [] for name, _, _ in jobs}
    pool = ProcessPoolExecutor(max_workers=WORKERS)

    def _flush() -> None:
        if not pending:
            return
        for item in pool.map(bust_probe, pending, chunksize=1):
            for name, rows in item.items():
                pooled[name].extend(rows)
        pending.clear()
        first = next(iter(pooled))
        print(f"games_done {first} stars={len(pooled[first])} {_summarize(pooled[first])}", flush=True)

    try:
        for index, row in enumerate(picked):
            try:
                projection = build_game_projections(
                    settings,
                    season=SEASON,
                    game_id=str(row["game_id"]),
                    as_of=row["game_date"],
                    bundles=bundles,
                    cache=cache,
                )
                foul_projection = projection
                if not sweep:
                    foul_projection = build_game_projections(
                        foul_settings,
                        season=SEASON,
                        game_id=str(row["game_id"]),
                        as_of=row["game_date"],
                        bundles=bundles,
                        cache=foul_cache,
                    )
            except ValueError:
                continue
            home_n = sum(1 for player in projection.players if player.home_away == "H")
            away_n = sum(1 for player in projection.players if player.home_away == "A")
            if home_n < 5 or away_n < 5:
                continue
            pending.append(
                {
                    "projection": projection,
                    "foul_projection": foul_projection,
                    "runs": RUNS,
                    "seed": SEED + index,
                    "config": config,
                    "logs": logs_by_game.get(row["game_id"], {}),
                    "season_ppg": entering.get(row["game_id"], {}),
                    "jobs": jobs,
                }
            )
            if len(pending) >= WORKERS:
                _flush()
        _flush()
    finally:
        pool.shutdown()

    print("\nALL STARS (usage>=0.24)", flush=True)
    base_rows = pooled[jobs[0][0]]
    for name, _, _ in jobs:
        print(f"{name:14} {_summarize(pooled[name])}", flush=True)
    print("\nTOP 30 BY USAGE IN THIS SAMPLE", flush=True)
    top_ids_source = _top30(base_rows)
    top_ids = {int(row["player_id"]) for row in top_ids_source}
    for name, _, _ in jobs:
        chosen = [row for row in pooled[name] if int(row["player_id"]) in top_ids]
        print(f"{name:14} {_summarize(chosen)}", flush=True)


if __name__ == "__main__":
    main()
