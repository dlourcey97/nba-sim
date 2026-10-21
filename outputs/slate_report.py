"""Build results/latest/slate_report.md from summaries + confident picks."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ingest.injuries import InjuryEntry
from outputs.confidence import ConfidentPick
from outputs.summarize import GameSummary, PlayerSummary


def write_slate_report(
    repo_root: Path,
    *,
    game_date: str,
    summaries: Sequence[GameSummary],
    picks: Sequence[ConfidentPick],
    injuries: Sequence[InjuryEntry],
    notes: Sequence[str],
    assumptions: Sequence[str],
    projections_started: dict[int, bool] | None = None,
) -> Path:
    """Write markdown report. Returns path."""
    out_dir = repo_root / "results" / "latest"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "slate_report.md"
    started = projections_started or {}

    lines: list[str] = []
    lines.append(f"# NBA Sim Slate Report — {game_date}")
    lines.append("")
    lines.append("Predictions from the Monte Carlo engine only. No sportsbook lines, odds, or props.")
    lines.append("")

    lines.append("## 1. Injury / lineup notes (changes that affected sims)")
    lines.append("")
    if notes:
        for note in notes:
            lines.append(f"- {note}")
    else:
        lines.append("- (none beyond official OUT/Doubtful removals)")
    lines.append("")

    lines.append("## 2. Games")
    lines.append("")
    for summary in sorted(summaries, key=lambda s: s.game_id):
        lines.extend(_game_section(summary, started))

    lines.append("## 3. Top confident stat lines")
    lines.append("")
    if not picks:
        lines.append("_No eligible picks met the confidence filters._")
        lines.append("")
    else:
        lines.append("| # | Player | Matchup | Stat | Pred | Range | Conf |")
        lines.append("| --- | --- | --- | --- | ---: | --- | ---: |")
        for i, pick in enumerate(picks, 1):
            matchup = f"{pick.team_abbr} vs {pick.opponent_abbr}"
            lines.append(
                f"| {i} | {pick.player_name} | {matchup} | {pick.stat} | "
                f"{int(pick.median)} | {pick.range_label} | {100.0 * pick.confidence:.1f}% |"
            )
        lines.append("")

    lines.append("## 4. Assumptions")
    lines.append("")
    if assumptions:
        for item in assumptions:
            lines.append(f"- {item}")
    else:
        lines.append("- None noted.")
    lines.append("")

    # Compact injury appendix for audit
    tonight = [e for e in injuries if e.game_date.isoformat() == game_date]
    if tonight:
        lines.append("## Appendix: injury inputs used")
        lines.append("")
        for e in sorted(tonight, key=lambda x: (x.team_abbr or "", x.player_name)):
            cap = f", cap={e.minutes_cap}" if e.minutes_cap is not None else ""
            lines.append(
                f"- {e.team_abbr or '?'} {e.player_name}: {e.status} "
                f"({e.source}{cap}) — {e.reason}"
            )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _game_section(summary: GameSummary, started: dict[int, bool]) -> list[str]:
    home_wp = summary.home_win_prob
    away_wp = 1.0 - home_wp
    if home_wp >= away_wp:
        winner = summary.home_abbr
        win_pct = 100.0 * home_wp
    else:
        winner = summary.away_abbr
        win_pct = 100.0 * away_wp
    home_med = summary.home_pts.p50
    away_med = summary.away_pts.p50
    margin = summary.margin.p50  # home - away
    total = summary.total.p50
    spread = -margin  # from home perspective as "home favored by X" if positive margin

    lines = [
        f"### {summary.away_abbr} @ {summary.home_abbr} (`{summary.game_id}`)",
        "",
        f"- **Winner:** {winner} ({win_pct:.1f}%)",
        f"- **Median score:** {summary.away_abbr} {away_med:.0f} – {summary.home_abbr} {home_med:.0f}",
        f"- **Projected spread (median margin, home−away):** {margin:+.1f}"
        f" ({summary.home_abbr} {'favored' if margin > 0 else 'underdog' if margin < 0 else 'pick'})",
        f"- **Projected total (median):** {total:.1f}",
        f"- **Runs:** {summary.runs}",
        "",
        "#### Projected box score",
        "",
    ]

    for side, abbr in (("Away", summary.away_abbr), ("Home", summary.home_abbr)):
        players = [p for p in summary.players if p.team_abbr == abbr]
        players = [p for p in players if p.stats["min"].p50 >= 1.0]
        players.sort(
            key=lambda p: (
                -(1 if (started.get(p.player_id) or p.started) else 0),
                -p.stats["min"].p50,
            )
        )
        lines.append(f"**{abbr} ({side})**")
        lines.append("")
        lines.append("| Role | Player | MIN | PTS | REB | AST | STL | BLK |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for p in players:
            role = "Starter" if (started.get(p.player_id) or p.started) else "Bench"
            lines.append(
                f"| {role} | {p.player_name} | "
                f"{_r(p, 'min')} | {_r(p, 'pts')} | {_r(p, 'reb')} | "
                f"{_r(p, 'ast')} | {_r(p, 'stl')} | {_r(p, 'blk')} |"
            )
        lines.append("")
    return lines


def _r(player: PlayerSummary, stat: str) -> str:
    return f"{player.stats[stat].p50:.1f}"
