"""Pick the most typical sim run and write its replay.

The Monte Carlo cloud is scored in memory. Persist one possession log and one
self-contained replay page.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from projections.build import GameProjection
from sim.engine import GameSimResult, simulate_game
from sim.possession_log import PERIOD_SECONDS, REGULATION_SECONDS, PossessionLog


# Rotation players are those whose median minutes clear a real-role floor.
_ROTATION_MINUTES = 8.0


def _spread(values: np.ndarray) -> np.ndarray | float:
    """Std across runs. A flat stat uses 1 so a zero gap stays zero."""
    scale = np.std(values, axis=0) if values.ndim > 1 else np.std(values)
    return np.maximum(scale, 1.0)


def _sq(values: np.ndarray, center: np.ndarray | float, scale: np.ndarray | float) -> np.ndarray:
    return ((values - center) / scale) ** 2


def typical_distance(result: GameSimResult) -> np.ndarray:
    """Distance of every run from the median game.

    Game terms: final margin, total, and each team's quarter scores.
    Player terms: PTS, REB, AST, MIN for rotation players, each divided by
    that stat's spread and weighted by the player's median minutes.
    """
    margin = result.home_pts - result.away_pts
    total = result.home_pts + result.away_pts
    dist = _sq(margin, float(np.median(margin)), _spread(margin))
    dist = dist + _sq(total, float(np.median(total)), _spread(total))
    if result.home_period_pts is not None and result.away_period_pts is not None:
        periods = min(4, int(result.home_period_pts.shape[1]))
        for period in range(periods):
            home_q = result.home_period_pts[:, period]
            away_q = result.away_period_pts[:, period]
            dist = dist + _sq(home_q, float(np.median(home_q)), _spread(home_q))
            dist = dist + _sq(away_q, float(np.median(away_q)), _spread(away_q))
    med_min = np.median(result.minutes, axis=1)
    for index in np.flatnonzero(med_min >= _ROTATION_MINUTES):
        weight = float(med_min[index]) / 36.0
        for values in (
            result.pts[index],
            result.reb[index],
            result.ast[index],
            result.minutes[index],
        ):
            dist = dist + weight * _sq(values, float(np.median(values)), _spread(values))
    return dist


def pick_typical_run(result: GameSimResult) -> int:
    """Run index closest to the median margin, total, quarters, and box lines."""
    return int(np.argmin(typical_distance(result)))


def typical_fit(result: GameSimResult, index: int) -> dict:
    """How the chosen run sits against the medians. In-memory only."""
    margin = result.home_pts - result.away_pts
    total = result.home_pts + result.away_pts
    med_min = np.median(result.minutes, axis=1)
    order = [
        int(i)
        for i in np.argsort(-med_min)
        if float(med_min[i]) >= _ROTATION_MINUTES
    ][:8]
    players = []
    for i in order:
        players.append(
            {
                "name": result.player_names[i],
                "team": result.team_abbrs[i],
                "min": round(float(result.minutes[i, index]), 1),
                "min_median": round(float(med_min[i]), 1),
                "pts": int(round(float(result.pts[i, index]))),
                "pts_median": int(round(float(np.median(result.pts[i])))),
                "reb": int(round(float(result.reb[i, index]))),
                "reb_median": int(round(float(np.median(result.reb[i])))),
                "ast": int(round(float(result.ast[i, index]))),
                "ast_median": int(round(float(np.median(result.ast[i])))),
            }
        )
    return {
        "runs": int(result.runs),
        "distance": round(float(typical_distance(result)[index]), 3),
        "margin": round(float(margin[index]), 1),
        "median_margin": round(float(np.median(margin)), 1),
        "total": round(float(total[index]), 1),
        "median_total": round(float(np.median(total)), 1),
        "players": players,
    }


def format_typical_fit(log: PossessionLog) -> str:
    """One block of text for the daily log."""
    fit = log.fit or {}
    lines = [
        (
            f"typical fit {log.away_abbr}@{log.home_abbr} "
            f"margin {float(fit.get('margin', 0)):+.0f} "
            f"(median {float(fit.get('median_margin', 0)):+.0f}), "
            f"total {float(fit.get('total', 0)):.0f} "
            f"(median {float(fit.get('median_total', 0)):.0f}), "
            f"distance {float(fit.get('distance', 0)):.2f}"
        )
    ]
    for player in fit.get("players") or []:
        lines.append(
            f"  {player['name']} MIN {player['min']:.1f} vs {player['min_median']:.1f}, "
            f"PTS {player['pts']} vs {player['pts_median']}, "
            f"REB {player['reb']} vs {player['reb_median']}, "
            f"AST {player['ast']} vs {player['ast_median']}"
        )
    return "\n".join(lines)


def win_prob_lookup(
    *,
    margins: np.ndarray,
    clocks: np.ndarray,
    home_won: np.ndarray,
    query_margin: float,
    query_clock: float,
    margin_bin: float = 4.0,
    clock_bin: float = 180.0,
) -> float:
    """Empirical P(home wins | margin, clock) from the in-memory sim cloud."""
    if margins.size == 0:
        return 0.5
    m_ok = np.abs(margins - query_margin) <= margin_bin
    c_ok = np.abs(clocks - query_clock) <= clock_bin
    mask = m_ok & c_ok
    if int(np.sum(mask)) < 8:
        # Widen clock window, then margin.
        mask = m_ok & (np.abs(clocks - query_clock) <= clock_bin * 2.5)
    if int(np.sum(mask)) < 8:
        mask = np.abs(margins - query_margin) <= margin_bin * 2.0
    if int(np.sum(mask)) == 0:
        return float(np.mean(home_won))
    return float(np.mean(home_won[mask]))


def attach_win_probs(
    log: PossessionLog,
    *,
    trajectory_margins: np.ndarray,
    trajectory_clocks: np.ndarray,
    trajectory_wins: np.ndarray,
) -> PossessionLog:
    """Fill home_win_prob on each event from the in-memory trajectory cloud."""
    for event in log.events:
        event.home_win_prob = win_prob_lookup(
            margins=trajectory_margins,
            clocks=trajectory_clocks,
            home_won=trajectory_wins,
            query_margin=float(event.home_pts - event.away_pts),
            query_clock=float(event.clock_remaining),
        )
    return log


def _players_for_log(
    projection: GameProjection,
    traced: GameSimResult,
    run_index: int,
) -> list[dict]:
    started = {p.player_id: bool(p.started) for p in projection.players}
    rows = []
    for index, player_id in enumerate(traced.player_ids):
        minutes = float(traced.minutes[index, run_index])
        if minutes < 1.0:
            continue
        pid = int(player_id)
        rows.append(
            {
                "player_id": pid,
                "name": traced.player_names[index],
                "team": traced.team_abbrs[index],
                "started": started.get(pid, False),
                "min": round(minutes, 1),
                "pts": int(round(float(traced.pts[index, run_index]))),
                "reb": int(round(float(traced.reb[index, run_index]))),
                "ast": int(round(float(traced.ast[index, run_index]))),
            }
        )
    rows.sort(key=lambda row: (row["team"] != projection.away_abbr, not row["started"], -row["min"]))
    return rows


def build_typical_game(
    projection: GameProjection,
    result: GameSimResult,
    *,
    config: dict | None = None,
) -> tuple[int, PossessionLog]:
    """Re-sim with trace_run for the typical index; attach WP from the cloud.

    The cloud is used only to score runs and fill win probability. The returned
    log is the single kept game.
    """
    typical = pick_typical_run(result)
    traced = simulate_game(
        projection,
        runs=result.runs,
        seed=result.seed,
        config=config,
        trace_run=typical,
    )
    log = traced.possession_log
    if log is None:
        raise RuntimeError("trace_run did not produce a possession log")
    log.simulated_runs = int(result.runs)
    log.players = _players_for_log(projection, traced, typical)
    log.fit = typical_fit(result, typical)
    from outputs.replay_viewer import annotate_captions

    annotate_captions(log)
    traj_m, traj_c, traj_w = _trajectory_from_period_scores(result)
    attach_win_probs(
        log,
        trajectory_margins=traj_m,
        trajectory_clocks=traj_c,
        trajectory_wins=traj_w,
    )
    return typical, log


def _trajectory_from_period_scores(
    result: GameSimResult,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Approximate mid-game (margin, clock) states from period score snapshots."""
    home_won = (result.home_pts > result.away_pts).astype(float)
    if result.home_period_pts is None or result.away_period_pts is None:
        margins = result.home_pts - result.away_pts
        clocks = np.zeros_like(margins)
        return margins, clocks, home_won
    margins_list = []
    clocks_list = []
    wins_list = []
    home_cum = np.zeros(result.runs, dtype=float)
    away_cum = np.zeros(result.runs, dtype=float)
    for period in range(4):
        home_cum = home_cum + result.home_period_pts[:, period]
        away_cum = away_cum + result.away_period_pts[:, period]
        margins_list.append(home_cum - away_cum)
        # Clock at end of this period.
        clocks_list.append(np.full(result.runs, max(0.0, REGULATION_SECONDS - (period + 1) * PERIOD_SECONDS)))
        wins_list.append(home_won)
    # Also include tip-off and final.
    margins_list.insert(0, np.zeros(result.runs))
    clocks_list.insert(0, np.full(result.runs, REGULATION_SECONDS))
    wins_list.insert(0, home_won)
    margins_list.append(result.home_pts - result.away_pts)
    clocks_list.append(np.zeros(result.runs))
    wins_list.append(home_won)
    return (
        np.concatenate(margins_list),
        np.concatenate(clocks_list),
        np.concatenate(wins_list),
    )


def write_typical_game_artifacts(
    *,
    projection: GameProjection,
    result: GameSimResult,
    log: PossessionLog,
    out_dir: Path,
) -> dict[str, Path]:
    """Write the one typical-game log and its replay page under out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if log.simulated_runs <= 0:
        log.simulated_runs = int(result.runs)
    game_tag = f"{projection.away_abbr}-{projection.home_abbr}-{projection.game_id}"
    log_path = out_dir / f"{game_tag}-typical.json"
    html_path = out_dir / f"{game_tag}-typical.html"
    from outputs.replay_viewer import render_replay_html

    log_path.write_text(json.dumps(log.as_dict(), indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_replay_html(log), encoding="utf-8")
    return {"log": log_path, "html": html_path}
