"""Pick the most typical sim run and build a win-probability narrative chart.

The win-probability grid is computed from the full Monte Carlo cloud in memory
only. Persist just the single typical-game possession log and the chart.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from projections.build import GameProjection
from sim.engine import GameSimResult, simulate_game
from sim.possession_log import PERIOD_SECONDS, REGULATION_SECONDS, PossessionLog


def pick_typical_run(result: GameSimResult) -> int:
    """Run index closest to median margin and median total."""
    margin = result.home_pts - result.away_pts
    total = result.home_pts + result.away_pts
    med_m = float(np.median(margin))
    med_t = float(np.median(total))
    # Normalize distances by MAD-like scales so margin and total share weight.
    scale_m = float(np.std(margin)) or 1.0
    scale_t = float(np.std(total)) or 1.0
    dist = ((margin - med_m) / scale_m) ** 2 + ((total - med_t) / scale_t) ** 2
    return int(np.argmin(dist))


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


def build_typical_game(
    projection: GameProjection,
    result: GameSimResult,
    *,
    config: dict | None = None,
) -> tuple[int, PossessionLog]:
    """Re-sim with trace_run for the typical index; attach WP from the cloud."""
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
    """Write possession log JSON + HTML win-probability chart under out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    game_tag = f"{projection.away_abbr}-{projection.home_abbr}-{projection.game_id}"
    log_path = out_dir / f"{game_tag}-typical.json"
    html_path = out_dir / f"{game_tag}-typical.html"
    log_path.write_text(json.dumps(log.as_dict(), indent=2) + "\n", encoding="utf-8")
    html_path.write_text(
        _render_html(projection, result, log),
        encoding="utf-8",
    )
    return {"log": log_path, "html": html_path}


def _render_html(
    projection: GameProjection,
    result: GameSimResult,
    log: PossessionLog,
) -> str:
    home = projection.home_abbr
    away = projection.away_abbr
    events = log.events
    xs = [REGULATION_SECONDS - float(e.clock_remaining) for e in events]
    # Extend OT clocks as elapsed beyond regulation.
    elapsed = []
    for event in events:
        if event.period <= 4:
            elapsed.append(REGULATION_SECONDS - float(event.clock_remaining))
        else:
            ot = event.period - 4
            elapsed.append(REGULATION_SECONDS + (ot - 1) * 300.0 + (300.0 - float(event.clock_remaining)))
    wps = [float(e.home_win_prob if e.home_win_prob is not None else 0.5) for e in events]
    q_home = log.home_period_pts
    q_away = log.away_period_pts
    # Simple SVG chart.
    width, height = 720, 280
    pad = 40
    if not elapsed:
        elapsed = [0.0]
        wps = [0.5]
    max_x = max(elapsed) or 1.0
    points = []
    for x, y in zip(elapsed, wps):
        px = pad + (width - 2 * pad) * (x / max_x)
        py = pad + (height - 2 * pad) * (1.0 - y)
        points.append(f"{px:.1f},{py:.1f}")
    poly = " ".join(points)
    mid_y = pad + (height - 2 * pad) * 0.5
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{away} @ {home} typical game</title>
<style>
body {{ font-family: Georgia, serif; margin: 2rem; color: #1a1a1a; background: #f7f4ef; }}
h1 {{ font-size: 1.6rem; margin-bottom: 0.2rem; }}
.sub {{ color: #555; margin-bottom: 1.5rem; }}
.score {{ font-size: 2rem; font-weight: bold; }}
table {{ border-collapse: collapse; margin: 1rem 0 1.5rem; }}
td, th {{ padding: 0.35rem 0.75rem; border-bottom: 1px solid #ddd; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
svg {{ background: #fff; border: 1px solid #ddd; max-width: 100%; }}
</style></head><body>
<h1>{away} @ {home}</h1>
<p class="sub">Most typical sim (run {log.run_index}) · seed {result.seed} · {result.runs} runs</p>
<p class="score">{away} {log.final_away_pts} — {home} {log.final_home_pts}</p>
<table>
<tr><th>Team</th><th>Q1</th><th>Q2</th><th>Q3</th><th>Q4</th><th>Final</th></tr>
<tr><td>{away}</td>{''.join(f'<td>{int(v)}</td>' for v in q_away)}<td>{log.final_away_pts}</td></tr>
<tr><td>{home}</td>{''.join(f'<td>{int(v)}</td>' for v in q_home)}<td>{log.final_home_pts}</td></tr>
</table>
<h2>Home win probability</h2>
<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}">
  <line x1="{pad}" y1="{mid_y}" x2="{width-pad}" y2="{mid_y}" stroke="#ccc" stroke-dasharray="4 4"/>
  <polyline fill="none" stroke="#1d4ed8" stroke-width="2.5" points="{poly}"/>
  <text x="{pad}" y="24" font-size="12" fill="#555">P({home} win)</text>
  <text x="{pad}" y="{height-12}" font-size="11" fill="#777">0%</text>
  <text x="{pad}" y="{pad+8}" font-size="11" fill="#777">100%</text>
</svg>
<p class="sub">{len(events)} possessions logged. Win probability from the Monte Carlo cloud
(margin × time remaining); only this typical-game log is persisted.</p>
</body></html>
"""
