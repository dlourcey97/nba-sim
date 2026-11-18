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

import numpy as np

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
    crps_min_sum = 0.0
    crps_pts_sum = 0.0
    cover_min_hits = 0.0
    cover_pts_hits = 0.0
    cover_star_hits = 0.0
    cover_star_n = 0
    cover_bench_hits = 0.0
    cover_bench_n = 0
    played_n = 0
    id_to_idx = {int(pid): index for index, pid in enumerate(sim.player_ids)}
    usage_by_id = {int(p.player_id): float(p.rates.usage) for p in projection.players}
    cut = float((payload["config"].get("simulation") or {}).get("star_usage_min", 0.24))
    role_by_id: dict[int, str] = {}
    for proj_player in projection.players:
        if float(proj_player.rates.usage) >= cut:
            role = "top"
        elif bool(proj_player.started) or int(proj_player.depth_rank) <= 5:
            role = "start"
        else:
            role = "bench"
        role_by_id[int(proj_player.player_id)] = role
    tier_crps = {"top": 0.0, "start": 0.0, "bench": 0.0}
    tier_n = {"top": 0, "start": 0, "bench": 0}
    tier_pred = {"top": 0.0, "start": 0.0, "bench": 0.0}
    tier_act = {"top": 0.0, "start": 0.0, "bench": 0.0}
    # Every player who played is scored. Someone the projection left off is a
    # point mass at 0: CRPS is the absolute error, and the 10–90 band is {0}.
    for pid, player, actual in iter_played(summary.players, logs):
        y_pts = float(actual["pts"])
        y_min = float(actual["minutes"])
        act_pts.append(y_pts)
        act_reb.append(float(actual["reb"]))
        act_ast.append(float(actual["ast"]))
        act_stl.append(float(actual["stl"]))
        act_blk.append(float(actual["blk"]))
        act_tov.append(float(actual["tov"]))
        act_fg3m.append(float(actual["fg3m"]))
        act_min.append(y_min)
        played_n += 1
        idx = None if player is None else id_to_idx.get(int(pid))
        if player is None or idx is None:
            pred_pts.append(0.0)
            pred_reb.append(0.0)
            pred_ast.append(0.0)
            pred_stl.append(0.0)
            pred_blk.append(0.0)
            pred_tov.append(0.0)
            pred_fg3m.append(0.0)
            pred_min.append(0.0)
            crps_min_sum += abs(y_min)
            crps_pts_sum += abs(y_pts)
            crps_pts_vals.append(abs(y_pts))
            cover_pts_hits += 1.0 if y_pts == 0.0 else 0.0
            continue
        pred_pts.append(player.stats["pts"].mean)
        pred_reb.append(player.stats["reb"].mean)
        pred_ast.append(player.stats["ast"].mean)
        pred_stl.append(player.stats["stl"].mean)
        pred_blk.append(player.stats["blk"].mean)
        pred_tov.append(player.stats["tov"].mean)
        pred_fg3m.append(player.stats["fg3m"].mean)
        pred_min.append(player.stats["min"].mean)
        pts_crps = crps_from_samples(sim.pts[idx], y_pts)
        min_crps = crps_from_samples(sim.minutes[idx], y_min)
        crps_pts_sum += pts_crps
        crps_min_sum += min_crps
        crps_pts_vals.append(pts_crps)
        pit_pts_vals.append(pit_from_samples(sim.pts[idx], y_pts))
        pts_band = player.stats["pts"]
        min_band = player.stats["min"]
        pts_inside = float(pts_band.p10) <= y_pts <= float(pts_band.p90)
        min_inside = float(min_band.p10) <= y_min <= float(min_band.p90)
        cover_hits.append(1.0 if pts_inside else 0.0)
        cover_pts_hits += 1.0 if pts_inside else 0.0
        cover_min_hits += 1.0 if min_inside else 0.0
        role = role_by_id.get(int(pid), "bench")
        tier_crps[role] += pts_crps
        tier_n[role] += 1
        tier_pred[role] += float(player.stats["pts"].mean)
        tier_act[role] += y_pts
        usage = usage_by_id.get(int(pid), 0.0)
        if usage >= cut:
            cover_star_hits += 1.0 if pts_inside else 0.0
            cover_star_n += 1
        else:
            cover_bench_hits += 1.0 if pts_inside else 0.0
            cover_bench_n += 1
    groups = _star_bust(payload, projection, sim, id_to_idx)
    cond_draws = cond_wins = cond_actual_n = cond_actual_wins = 0
    home_won = sim.home_pts > sim.away_pts
    for side, won in (("H", home_won), ("A", ~home_won)):
        side_players = [p for p in projection.players if p.home_away == side and not p.minutes.out]
        if not side_players:
            continue
        star = max(side_players, key=lambda p: float(p.rates.usage))
        idx = id_to_idx.get(int(star.player_id))
        if idx is None:
            continue
        under = sim.pts[idx] < 20.0
        cond_draws += int(under.sum())
        cond_wins += int((under & won).sum())
        actual = logs.get(int(star.player_id))
        if actual is None:
            actual = logs.get(str(star.player_id))
        scored = float(actual.get("pts") or 0.0) if actual else None
        if scored is not None and scored < 20.0:
            cond_actual_n += 1
            team_pts = home_pts if side == "H" else away_pts
            opp_pts = away_pts if side == "H" else home_pts
            cond_actual_wins += int(team_pts > opp_pts)
    play_brier_sum, play_n, play_bins = _play_calibration(projection, logs)
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
        "crps_min_sum": crps_min_sum,
        "crps_pts_sum": crps_pts_sum,
        "played_n": played_n,
        "cover_min_hits": cover_min_hits,
        "cover_pts_hits": cover_pts_hits,
        "cover_star_hits": cover_star_hits,
        "cover_star_n": cover_star_n,
        "cover_bench_hits": cover_bench_hits,
        "cover_bench_n": cover_bench_n,
        **groups,
        "crps_top": tier_crps["top"],
        "crps_top_n": tier_n["top"],
        "crps_start": tier_crps["start"],
        "crps_start_n": tier_n["start"],
        "crps_bench": tier_crps["bench"],
        "crps_bench_n": tier_n["bench"],
        "pred_top": tier_pred["top"],
        "act_top": tier_act["top"],
        "pred_start": tier_pred["start"],
        "act_start": tier_act["start"],
        "pred_bench": tier_pred["bench"],
        "act_bench": tier_act["bench"],
        "cond_draws": cond_draws,
        "cond_wins": cond_wins,
        "cond_actual_n": cond_actual_n,
        "cond_actual_wins": cond_actual_wins,
        "play_brier_sum": play_brier_sum,
        "play_n": play_n,
        "play_bins": play_bins,
        "pred_home_pts": float(summary.home_pts.mean),
        "pred_away_pts": float(summary.away_pts.mean),
        "act_home_pts": home_pts,
        "act_away_pts": away_pts,
    }


def _star_bust(payload, projection, sim, id_to_idx) -> dict:
    """Sims under half the entering points-per-game, for high-usage players.

    The minutes draw is not the comparison. A player qualifies from the
    pregame usage and a minutes mean of at least 20, with at least 8 prior
    games of 8+ minutes.
    """
    ppg_map = payload.get("season_ppg") or {}
    cut = float((payload["config"].get("simulation") or {}).get("star_usage_min", 0.24))
    logs = payload["logs"]
    bust = draws = actual_bust = n = 0
    pred_sum = med_sum = act_sum = 0.0
    for player in projection.players:
        if float(player.rates.usage) < cut or float(player.minutes.mean) < 20:
            continue
        pid = int(player.player_id)
        rate = ppg_map.get(pid)
        if rate is None or float(rate) < 12:
            continue
        idx = id_to_idx.get(pid)
        if idx is None:
            continue
        pts = sim.pts[idx]
        threshold = 0.5 * float(rate)
        bust += int((pts < threshold).sum())
        draws += int(pts.shape[0])
        pred_sum += float(pts.mean())
        med_sum += float(np.median(pts))
        actual = logs.get(pid)
        if actual is None:
            actual = logs.get(str(pid))
        scored = float(actual.get("pts") or 0.0) if actual else 0.0
        act_sum += scored
        actual_bust += int(scored < threshold)
        n += 1
    return {
        "star_bust": bust,
        "star_bust_draws": draws,
        "star_actual_bust": actual_bust,
        "star_n": n,
        "star_pred_sum": pred_sum,
        "star_med_sum": med_sum,
        "star_act_sum": act_sum,
    }


def _play_calibration(projection, logs: dict) -> tuple[float, int, list[dict]]:
    """P(plays) against whether he actually played.

    Projected players are included even when they sat. A player who played and
    was left off the projection is a predicted probability of 0.
    """
    played = {
        int(pid)
        for pid, actual in logs.items()
        if float(actual.get("minutes") or 0.0) > 0.0
    }
    bins = [
        {"count": 0, "pred_sum": 0.0, "played": 0}
        for _ in range(10)
    ]
    brier = 0.0
    n = 0
    seen: set[int] = set()

    def _add(prob: float, did_play: bool) -> None:
        nonlocal brier, n
        p = min(max(float(prob), 0.0), 1.0)
        y = 1.0 if did_play else 0.0
        brier += (p - y) ** 2
        slot = min(int(p * 10.0), 9)
        bins[slot]["count"] += 1
        bins[slot]["pred_sum"] += p
        bins[slot]["played"] += int(y)
        n += 1

    for player in projection.players:
        pid = int(player.player_id)
        seen.add(pid)
        prob = 0.0 if player.minutes.out else float(player.minutes.play_prob)
        _add(prob, pid in played)
    for pid in played:
        if pid not in seen:
            _add(0.0, True)
    return brier, n, bins


CALIBRATION_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "pra")


def bust_probe(payload: dict) -> dict[str, list[dict]]:
    """Star bust rows for several sim configs of one already-built projection."""
    out: dict[str, list[dict]] = {}
    for name, config, key in payload["jobs"]:
        projection = payload[key]
        sim = simulate_game(
            projection,
            runs=int(payload["runs"]),
            seed=int(payload["seed"]),
            config=config,
        )
        out[name] = _star_player_rows(payload, projection, sim)
    return out


def _star_player_rows(payload, projection, sim) -> list[dict]:
    ppg_map = payload.get("season_ppg") or {}
    cut = float((payload.get("config") or {}).get("simulation", {}).get("star_usage_min", 0.24))
    logs = payload["logs"]
    id_to_idx = {int(pid): index for index, pid in enumerate(sim.player_ids)}
    rows = []
    for player in projection.players:
        if float(player.rates.usage) < cut or float(player.minutes.mean) < 20:
            continue
        pid = int(player.player_id)
        rate = ppg_map.get(pid)
        if rate is None or float(rate) < 12:
            continue
        idx = id_to_idx.get(pid)
        if idx is None:
            continue
        pts = sim.pts[idx]
        threshold = 0.5 * float(rate)
        actual = logs.get(pid)
        if actual is None:
            actual = logs.get(str(pid))
        scored = float(actual.get("pts") or 0.0) if actual else 0.0
        rows.append(
            {
                "player_id": pid,
                "usage": float(player.rates.usage),
                "bust": int((pts < threshold).sum()),
                "draws": int(pts.shape[0]),
                "mean": float(pts.mean()),
                "actual": scored,
                "actual_bust": int(scored < threshold),
            }
        )
    return rows


def calibration_rows(payload: dict) -> list[dict]:
    """Percentile curve and the actual line for one game. No raw draws."""
    projection = payload["projection"]
    sim = simulate_game(
        projection,
        runs=int(payload["runs"]),
        seed=int(payload["seed"]),
        config=payload["config"],
    )
    summary = summarize_game(projection, sim)
    logs = payload["logs"]
    entering = payload.get("entering") or {}
    rows: list[dict] = []
    for player in summary.players:
        actual = logs.get(int(player.player_id))
        if actual is None or float(actual.get("minutes") or 0.0) <= 0.0:
            continue
        if float(player.stats["min"].mean) < 12.0:
            continue
        prior = entering.get(int(player.player_id)) or {}
        row = {
            "season": payload["season"],
            "game_id": payload["game_id"],
            "game_date": payload["game_date"],
            "player_id": int(player.player_id),
            "usage": float(payload["usage"].get(int(player.player_id), 0.0)),
            "started": bool(payload["started"].get(int(player.player_id), False)),
            "depth_rank": int(payload["depth"].get(int(player.player_id), 99)),
            "prior_games": int(prior.get("games") or 0),
        }
        for stat in CALIBRATION_STATS:
            curve = player.stats[stat]
            row[f"{stat}_p10"] = float(curve.p10)
            row[f"{stat}_p25"] = float(curve.p25)
            row[f"{stat}_p50"] = float(curve.p50)
            row[f"{stat}_p75"] = float(curve.p75)
            row[f"{stat}_p90"] = float(curve.p90)
            row[f"{stat}_mean"] = float(curve.mean)
            if stat == "pra":
                row["pra_actual"] = float(actual.get("pts") or 0.0) + float(actual.get("reb") or 0.0) + float(actual.get("ast") or 0.0)
            else:
                row[f"{stat}_actual"] = float(actual.get(stat) or 0.0)
            raw_prior = prior.get(stat)
            row[f"{stat}_prior"] = float("nan") if raw_prior is None else float(raw_prior)
        rows.append(row)
    return rows


def _actual_poss(sim_poss: list[float], home_tr: dict | None, away_tr: dict | None) -> list[float]:
    home = float(home_tr["pace"]) if home_tr is not None and home_tr.get("pace") is not None else float(sim_poss[0])
    away = float(away_tr["pace"]) if away_tr is not None and away_tr.get("pace") is not None else float(sim_poss[1])
    return [home, away]
