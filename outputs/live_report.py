"""Text report for a remaining-game re-sim. Does not write history."""

from __future__ import annotations

import numpy as np

from sim.engine import GameSimResult
from sim.resume import ResumeState


def render_live_report(
    projection,
    result: GameSimResult,
    resume: ResumeState,
    *,
    elapsed_seconds: float,
) -> str:
    home = projection.home_abbr
    away = projection.away_abbr
    start_home = float(resume.home.score)
    start_away = float(resume.away.score)
    home_final = result.home_pts
    away_final = result.away_pts
    home_left = home_final - start_home
    away_left = away_final - start_away
    home_win = float(np.mean(home_final > away_final))
    lines = [
        (
            f"{away} {start_away:.0f} @ {home} {start_home:.0f}  "
            f"Q{resume.period} { _clock(resume.clock_seconds)}  "
            f"{result.runs} runs  {elapsed_seconds:.0f}s"
        ),
        (
            f"Win % from here: {home} {100 * home_win:.1f}%, "
            f"{away} {100 * (1.0 - home_win):.1f}%"
        ),
        (
            f"Final: {away} {_band(away_final)}   {home} {_band(home_final)}   "
            f"total {_band(home_final + away_final)}"
        ),
        (
            f"Rest of game: {away} {_band(away_left)}   {home} {_band(home_left)}   "
            f"total {_band(home_left + away_left)}"
        ),
        "",
        "Remaining by quarter (median, points still to score in that quarter)",
    ]
    labels = ("Q1", "Q2", "Q3", "Q4")
    start = int(resume.period_index)
    for period in range(4):
        if period < start:
            lines.append(f"  {labels[period]}: already played")
            continue
        label = f"rest of {labels[period]}" if period == start and resume.clock_seconds > 1 else labels[period]
        h = result.home_period_pts[:, period]
        a = result.away_period_pts[:, period]
        lines.append(f"  {label}: {away} {np.median(a):.0f}  {home} {np.median(h):.0f}")
    played = {int(pid): line for pid, line in resume.players.items()}
    lines.append("")
    lines.append("REMAINING  (10th–90th, median)")
    lines.extend(_player_tables(projection, result, played, remaining=True))
    lines.append("")
    lines.append("FINAL  (already scored plus remaining; 10th–90th, median)")
    lines.extend(_player_tables(projection, result, played, remaining=False))
    return "\n".join(lines)


def _player_tables(projection, result: GameSimResult, played: dict, *, remaining: bool) -> list[str]:
    lines: list[str] = []
    index = {int(player.player_id): i for i, player in enumerate(projection.players)}
    for abbr in (projection.away_abbr, projection.home_abbr):
        rows = []
        for player in projection.players:
            if player.team_abbr != abbr:
                continue
            slot = index[int(player.player_id)]
            prior = played.get(int(player.player_id))
            already = (
                (float(prior.pts), float(prior.reb), float(prior.ast), float(prior.minutes))
                if prior is not None
                else (0.0, 0.0, 0.0, 0.0)
            )
            pts = result.pts[slot] - (already[0] if remaining else 0.0)
            reb = result.reb[slot] - (already[1] if remaining else 0.0)
            ast = result.ast[slot] - (already[2] if remaining else 0.0)
            if remaining:
                minutes = float(np.median(result.minutes[slot]))
            else:
                minutes = already[3] + float(np.median(result.minutes[slot]))
            if max(float(np.mean(pts)), float(np.mean(reb)), float(np.mean(ast))) < 0.25 and minutes < 2:
                continue
            rows.append((float(np.median(pts)), player.player_name, minutes, pts, reb, ast))
        rows.sort(key=lambda item: item[0], reverse=True)
        lines.append(f"  {abbr}")
        lines.append(f"  {'Player':<24} {'MIN':>6}  {'PTS':<16} {'REB':<16} {'AST':<16}")
        for _med, name, minutes, pts, reb, ast in rows:
            lines.append(
                f"  {name:<24} {minutes:6.1f}  {_band(pts):<16} {_band(reb):<16} {_band(ast):<16}"
            )
    return lines


def _band(values: np.ndarray) -> str:
    low, mid, high = np.percentile(values, [10, 50, 90])
    return f"{low:.0f}–{high:.0f} ({mid:.0f})"


def _clock(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60}:{seconds % 60:02d}"
