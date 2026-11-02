"""Score one simulated game in a worker process.

Thread pools are pinned to one thread before NumPy loads so a parallel run
uses the same reductions as a one-thread serial run.
"""

from __future__ import annotations

import os

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from backtest.metrics import crps_from_samples, pit_from_samples
from outputs.summarize import summarize_game
from sim.engine import simulate_game


def iter_played(players, logs: dict):
    """Players who actually played, paired with the projection when one exists.

    A log row with 0 minutes did not play. A player the projection left off is
    returned with ``player`` None so the scorer counts him as 0.
    """
    by_player = {int(player.player_id): player for player in players}
    for pid, actual in logs.items():
        if float(actual.get("minutes") or 0.0) <= 0.0:
            continue
        yield int(pid), by_player.get(int(pid)), actual


def score_projected_game(payload: dict) -> dict:
    """Simulate ``payload["projection"]`` and return the scalars the report needs."""
    projection = payload["projection"]
    sim = simulate_game(
        projection,
        runs=int(payload["runs"]),
        seed=int(payload["seed"]),
        config=payload["config"],
    )
    summary = summarize_game(projection, sim)
    logs = payload["logs"]
    home_tr = payload["home_tr"]
    away_tr = payload["away_tr"]
    home_pts = float(payload["home_pts"])
    away_pts = float(payload["away_pts"])
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
    id_to_idx = {int(pid): index for index, pid in enumerate(sim.player_ids)}
    # Every player who played is scored. Someone the projection left off
    # counts as 0 minutes and 0 stats.
    for pid, player, actual in iter_played(summary.players, logs):
        act_pts.append(float(actual["pts"]))
        act_reb.append(float(actual["reb"]))
        act_ast.append(float(actual["ast"]))
        act_stl.append(float(actual["stl"]))
        act_blk.append(float(actual["blk"]))
        act_tov.append(float(actual["tov"]))
        act_fg3m.append(float(actual["fg3m"]))
        act_min.append(float(actual["minutes"]))
        if player is None:
            pred_pts.append(0.0)
            pred_reb.append(0.0)
            pred_ast.append(0.0)
            pred_stl.append(0.0)
            pred_blk.append(0.0)
            pred_tov.append(0.0)
            pred_fg3m.append(0.0)
            pred_min.append(0.0)
            continue
        pred_pts.append(player.stats["pts"].mean)
        pred_reb.append(player.stats["reb"].mean)
        pred_ast.append(player.stats["ast"].mean)
        pred_stl.append(player.stats["stl"].mean)
        pred_blk.append(player.stats["blk"].mean)
        pred_tov.append(player.stats["tov"].mean)
        pred_fg3m.append(player.stats["fg3m"].mean)
        pred_min.append(player.stats["min"].mean)
        inside = (
            float(actual["pts"]) >= player.stats["pts"].p10
            and float(actual["pts"]) <= player.stats["pts"].p90
        )
        cover_hits.append(1.0 if inside else 0.0)
        idx = id_to_idx.get(int(pid))
        if idx is not None:
            samples = sim.pts[idx]
            y_pts = float(actual["pts"])
            crps_pts_vals.append(crps_from_samples(samples, y_pts))
            pit_pts_vals.append(pit_from_samples(samples, y_pts))
    sim_poss = [float(sim.home_possessions), float(sim.away_possessions)]
    del sim
    return {
        "game_id": str(summary.game_id),
        "game_date": summary.game_date.isoformat(),
        "home_win_prob": float(summary.home_win_prob),
        "home_win": 1.0 if home_pts > away_pts else 0.0,
        "pred_margin": float(summary.margin.mean),
        "act_margin": home_pts - away_pts,
        "pred_total": float(summary.total.mean),
        "act_total": home_pts + away_pts,
        "sim_team_pts": [float(summary.home_pts.mean), float(summary.away_pts.mean)],
        "act_team_pts": [home_pts, away_pts],
        "sim_poss": sim_poss,
        "act_poss": _actual_poss(sim_poss, home_tr, away_tr),
        "pred_pts": pred_pts,
        "act_pts": act_pts,
        "pred_reb": pred_reb,
        "act_reb": act_reb,
        "pred_ast": pred_ast,
        "act_ast": act_ast,
        "pred_stl": pred_stl,
        "act_stl": act_stl,
        "pred_blk": pred_blk,
        "act_blk": act_blk,
        "pred_tov": pred_tov,
        "act_tov": act_tov,
        "pred_fg3m": pred_fg3m,
        "act_fg3m": act_fg3m,
        "pred_min": pred_min,
        "act_min": act_min,
        "cover_hits": cover_hits,
        "crps_pts": crps_pts_vals,
        "pit_pts": pit_pts_vals,
        "pred_home_pts": float(summary.home_pts.mean),
        "pred_away_pts": float(summary.away_pts.mean),
        "act_home_pts": home_pts,
        "act_away_pts": away_pts,
    }


def _actual_poss(sim_poss: list[float], home_tr: dict | None, away_tr: dict | None) -> list[float]:
    home = float(home_tr["pace"]) if home_tr is not None and home_tr.get("pace") is not None else float(sim_poss[0])
    away = float(away_tr["pace"]) if away_tr is not None and away_tr.get("pace") is not None else float(sim_poss[1])
    return [home, away]
