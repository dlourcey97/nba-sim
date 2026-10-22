"""Grade prediction_history vs actuals and maintain season_scorecard.md."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence

from nba_sim.settings import Settings
from nba_sim.storage import read_rows

PLAYER_GRADE_STATS = ("min", "pts", "reb", "ast", "stl", "blk")
_STAT_ALIASES = {
    "MIN": "min",
    "PTS": "pts",
    "REB": "reb",
    "AST": "ast",
    "STL": "stl",
    "BLK": "blk",
}


@dataclass
class ConfidentPickGrade:
    player_name: str
    team_abbr: str
    opponent_abbr: str
    stat: str
    lo: float
    hi: float
    median: float
    confidence: float
    actual: float | None
    hit: bool | None


@dataclass
class NightGrade:
    game_date: str
    games: list[dict[str, Any]] = field(default_factory=list)
    player_rows: list[dict[str, Any]] = field(default_factory=list)
    winner_correct: int = 0
    games_graded: int = 0
    spread_abs: list[float] = field(default_factory=list)
    total_abs: list[float] = field(default_factory=list)
    score_abs: list[float] = field(default_factory=list)
    player_mae: dict[str, list[float]] = field(default_factory=dict)
    coverage_hits: list[float] = field(default_factory=list)
    pick_grades: list[ConfidentPickGrade] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        def _mae(vals: list[float]) -> float | None:
            return float(sum(vals) / len(vals)) if vals else None

        pick_hits = [p for p in self.pick_grades if p.hit is not None]
        return {
            "game_date": self.game_date,
            "games_graded": self.games_graded,
            "winner_accuracy": (
                self.winner_correct / self.games_graded if self.games_graded else None
            ),
            "spread_mae": _mae(self.spread_abs),
            "total_mae": _mae(self.total_abs),
            "score_mae": _mae(self.score_abs),
            "player_min_mae": _mae(self.player_mae.get("min", [])),
            "player_pts_mae": _mae(self.player_mae.get("pts", [])),
            "player_reb_mae": _mae(self.player_mae.get("reb", [])),
            "player_ast_mae": _mae(self.player_mae.get("ast", [])),
            "player_stl_mae": _mae(self.player_mae.get("stl", [])),
            "player_blk_mae": _mae(self.player_mae.get("blk", [])),
            "coverage_10_90": _mae(self.coverage_hits),
            "player_rows": len(self.player_rows),
            "top_picks": len(self.pick_grades),
            "top_picks_graded": len(pick_hits),
            "top_picks_hits": sum(1 for p in pick_hits if p.hit),
            "top_picks_hit_rate": (
                sum(1 for p in pick_hits if p.hit) / len(pick_hits) if pick_hits else None
            ),
        }


def grade_night(
    settings: Settings,
    season: str,
    game_date: str,
    *,
    picks: Sequence[dict[str, Any]] | None = None,
) -> NightGrade:
    """Grade one slate date from prediction_history (actuals must already be filled)."""
    history = read_rows(settings, "prediction_history", season)
    night = NightGrade(game_date=game_date)
    games = [
        r
        for r in history
        if r["row_kind"] == "game" and str(r["game_date"]) == game_date
    ]
    players = [
        r
        for r in history
        if r["row_kind"] == "player" and str(r["game_date"]) == game_date
    ]
    name_by_id = _player_names(settings, season)

    for g in sorted(games, key=lambda r: str(r["game_id"])):
        if g.get("actual_home_pts") is None or g.get("actual_away_pts") is None:
            continue
        pred_home = float(g["pred_home_pts_p50"])
        pred_away = float(g["pred_away_pts_p50"])
        act_home = float(g["actual_home_pts"])
        act_away = float(g["actual_away_pts"])
        pred_margin = float(g["pred_margin_p50"])
        pred_total = float(g["pred_total_p50"])
        act_margin = act_home - act_away
        act_total = act_home + act_away
        home_wp = float(g["home_win_prob"] or 0.5)
        pred_winner = g["home_abbr"] if home_wp >= 0.5 else g["away_abbr"]
        act_winner = g["home_abbr"] if act_home > act_away else g["away_abbr"]
        if act_home == act_away:
            act_winner = "TIE"
        correct = pred_winner == act_winner
        night.games_graded += 1
        if correct:
            night.winner_correct += 1
        night.spread_abs.append(abs(pred_margin - act_margin))
        night.total_abs.append(abs(pred_total - act_total))
        night.score_abs.append(abs(pred_home - act_home))
        night.score_abs.append(abs(pred_away - act_away))
        night.games.append(
            {
                "game_id": g["game_id"],
                "matchup": f"{g['away_abbr']}@{g['home_abbr']}",
                "pred_winner": pred_winner,
                "pred_wp": max(home_wp, 1.0 - home_wp),
                "act_winner": act_winner,
                "winner_hit": correct,
                "pred_score": f"{g['away_abbr']} {pred_away:.0f} – {g['home_abbr']} {pred_home:.0f}",
                "act_score": f"{g['away_abbr']} {act_away:.0f} – {g['home_abbr']} {act_home:.0f}",
                "pred_margin": pred_margin,
                "act_margin": act_margin,
                "pred_total": pred_total,
                "act_total": act_total,
                "spread_err": pred_margin - act_margin,
                "total_err": pred_total - act_total,
            }
        )

    for p in players:
        if p.get("actual_pts") is None and p.get("actual_min") is None:
            continue
        row: dict[str, Any] = {
            "player_id": int(p["player_id"]),
            "player_name": name_by_id.get(int(p["player_id"]), f"player:{p['player_id']}"),
            "team_abbr": p.get("team_abbr"),
            "game_id": p["game_id"],
            "stats": {},
        }
        any_stat = False
        for stat in PLAYER_GRADE_STATS:
            pred = p.get(f"pred_{stat}_p50")
            actual = p.get(f"actual_{stat}")
            p10 = p.get(f"pred_{stat}_p10")
            p90 = p.get(f"pred_{stat}_p90")
            if pred is None or actual is None:
                continue
            any_stat = True
            err = abs(float(pred) - float(actual))
            night.player_mae.setdefault(stat, []).append(err)
            inside = float(p10) <= float(actual) <= float(p90) if p10 is not None and p90 is not None else None
            if inside is not None:
                night.coverage_hits.append(1.0 if inside else 0.0)
            row["stats"][stat] = {
                "pred": float(pred),
                "actual": float(actual),
                "abs_err": err,
                "p10": float(p10) if p10 is not None else None,
                "p90": float(p90) if p90 is not None else None,
                "inside_10_90": inside,
            }
        if any_stat:
            night.player_rows.append(row)

    if picks:
        night.pick_grades = grade_confident_picks(
            settings, season, picks, game_date=game_date
        )
    return night


def grade_confident_picks(
    settings: Settings,
    season: str,
    picks: Sequence[dict[str, Any]],
    *,
    game_date: str | None = None,
) -> list[ConfidentPickGrade]:
    """Grade top confident picks against player_game_logs / prediction_history actuals."""
    history = read_rows(settings, "prediction_history", season)
    by_key: dict[tuple[str, int], dict[str, Any]] = {}
    by_team_date: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in history:
        if row["row_kind"] != "player" or row.get("player_id") is None:
            continue
        pid = int(row["player_id"])
        by_key[(str(row["game_id"]), pid)] = row
        by_team_date[(str(row["game_date"]), str(row.get("team_abbr") or "").upper(), pid)] = row
    log_rows = read_rows(settings, "player_game_logs", season)
    logs = {(str(r["game_id"]), int(r["player_id"])): r for r in log_rows}
    logs_by_team_date = {
        (str(r["game_date"]), str(r.get("team_abbr") or "").upper(), int(r["player_id"])): r
        for r in log_rows
    }
    name_index = _name_index(settings, season)
    out: list[ConfidentPickGrade] = []
    for pick in picks:
        stat_key = _STAT_ALIASES.get(str(pick["stat"]).upper(), str(pick["stat"]).lower())
        pid = pick.get("player_id")
        game_id = pick.get("game_id")
        team = str(pick.get("team_abbr") or "").upper()
        if pid is None and pick.get("player_name"):
            pid = name_index.get((team, _norm_name(pick["player_name"])))
            if pid is None:
                # Fall back to any-team name match.
                target = _norm_name(pick["player_name"])
                for (t, n), cand in name_index.items():
                    if n == target:
                        pid = cand
                        if not team:
                            team = t
                        break
        actual = None
        hist = None
        log = None
        if pid is not None and game_id is not None:
            hist = by_key.get((str(game_id), int(pid)))
            log = logs.get((str(game_id), int(pid)))
        elif pid is not None and game_date is not None:
            hist = by_team_date.get((game_date, team, int(pid)))
            log = logs_by_team_date.get((game_date, team, int(pid)))
        if hist is not None and hist.get(f"actual_{stat_key}") is not None:
            actual = float(hist[f"actual_{stat_key}"])
        elif log is not None:
            col = "minutes" if stat_key == "min" else stat_key
            if log.get(col) is not None:
                actual = float(log[col])
        hit = None if actual is None else (float(pick["lo"]) <= actual <= float(pick["hi"]))
        out.append(
            ConfidentPickGrade(
                player_name=str(pick.get("player_name") or ""),
                team_abbr=team or str(pick.get("team_abbr") or ""),
                opponent_abbr=str(pick.get("opponent_abbr") or ""),
                stat=str(pick.get("stat") or "").upper(),
                lo=float(pick["lo"]),
                hi=float(pick["hi"]),
                median=float(pick.get("median") or 0.0),
                confidence=float(pick.get("confidence") or 0.0),
                actual=actual,
                hit=hit,
            )
        )
    return out


def parse_confident_picks_from_slate_report(path: Path) -> list[dict[str, Any]]:
    """Parse the Top confident table from slate_report.md."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    m = re.search(
        r"## 3\. Top confident stat lines\n\n(.*?)(?:\n## |\Z)",
        text,
        flags=re.S,
    )
    if not m:
        return []
    block = m.group(1)
    if "No eligible picks" in block:
        return []
    picks: list[dict[str, Any]] = []
    for line in block.splitlines():
        if not line.startswith("|") or line.startswith("| ---") or line.startswith("| #"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 7:
            continue
        # # | Player | Matchup | Stat | Pred | Range | Conf |
        player = cols[1]
        matchup = cols[2]
        stat = cols[3]
        pred = cols[4]
        range_label = cols[5]
        conf = cols[6].rstrip("%")
        team, opp = _split_matchup(matchup)
        lo, hi = _parse_range(range_label)
        if lo is None or hi is None:
            continue
        picks.append(
            {
                "player_name": player,
                "team_abbr": team,
                "opponent_abbr": opp,
                "stat": stat,
                "median": float(pred),
                "lo": lo,
                "hi": hi,
                "confidence": float(conf) / 100.0,
                "range_label": range_label,
                "game_id": None,
                "player_id": None,
            }
        )
    return picks


def refresh_season_scorecard(
    settings: Settings,
    *,
    season: str | None = None,
    slate_report: Path | None = None,
) -> Path | None:
    """Rebuild scorecard for every game_date in prediction_history with actuals.

    Called from daily.py so the scorecard stays current after each night.
    """
    active = season or settings.current_season
    history = read_rows(settings, "prediction_history", active)
    dates = sorted(
        {
            str(r["game_date"])
            for r in history
            if r["row_kind"] == "game" and r.get("actual_home_pts") is not None
        }
    )
    if not dates:
        return None
    report_path = slate_report or (settings.repo_root / "results" / "latest" / "slate_report.md")
    slate_picks = parse_confident_picks_from_slate_report(report_path)
    slate_date = None
    if report_path.exists():
        for line in report_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# NBA Sim Slate Report — "):
                slate_date = line.split("—", 1)[1].strip()
                break
    notes: list[str] = []
    nights: list[NightGrade] = []
    for d in dates:
        picks = slate_picks if d == slate_date else []
        nights.append(grade_night(settings, active, d, picks=picks or None))
    if "2026-10-20" in dates and not any(
        n.game_date == "2026-10-20" and n.pick_grades for n in nights
    ):
        notes.append(
            "2026-10-20: no Top confident picks were produced that night "
            "(feature landed with the 2026-10-21 slate)."
        )
    return write_season_scorecard(
        settings.repo_root, season=active, nights=nights, notes=notes
    )


def write_season_scorecard(
    repo_root: Path,
    *,
    season: str,
    nights: Sequence[NightGrade],
    notes: Sequence[str] | None = None,
) -> Path:
    """Write results/season_scorecard.md with per-night detail + season totals."""
    out = repo_root / "results" / "season_scorecard.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    summaries = [n.summary() for n in nights if n.games_graded]
    season_tot = _aggregate(summaries)

    lines: list[str] = []
    lines.append(f"# NBA Sim Season Scorecard — {season}")
    lines.append("")
    lines.append(
        "Graded from `prediction_history` after finals. No sportsbook lines or odds."
    )
    lines.append("")
    lines.append("## Season to date")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | ---: |")
    lines.append(f"| Games graded | {season_tot['games_graded']} |")
    lines.append(_pct_row("Winner accuracy", season_tot.get("winner_accuracy")))
    lines.append(_num_row("Spread MAE (margin)", season_tot.get("spread_mae")))
    lines.append(_num_row("Total MAE", season_tot.get("total_mae")))
    lines.append(_num_row("Player MIN MAE", season_tot.get("player_min_mae")))
    lines.append(_num_row("Player PTS MAE", season_tot.get("player_pts_mae")))
    lines.append(_pct_row("10–90 coverage (player stats)", season_tot.get("coverage_10_90")))
    lines.append(
        _pct_row(
            "Top confident picks hit rate",
            season_tot.get("top_picks_hit_rate"),
            extra=f"{season_tot.get('top_picks_hits', 0)}/{season_tot.get('top_picks_graded', 0)}",
        )
    )
    lines.append("")

    if notes:
        lines.append("## Notes")
        lines.append("")
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")

    for night in nights:
        s = night.summary()
        lines.append(f"## {night.game_date}")
        lines.append("")
        if night.games_graded == 0:
            lines.append("_No graded games (missing actuals)._")
            lines.append("")
            continue
        lines.append("| Metric | Value |")
        lines.append("| --- | ---: |")
        lines.append(f"| Games graded | {s['games_graded']} |")
        lines.append(_pct_row("Winner accuracy", s.get("winner_accuracy")))
        lines.append(_num_row("Spread MAE", s.get("spread_mae")))
        lines.append(_num_row("Total MAE", s.get("total_mae")))
        lines.append(_num_row("MIN MAE", s.get("player_min_mae")))
        lines.append(_num_row("PTS MAE", s.get("player_pts_mae")))
        lines.append(_num_row("REB MAE", s.get("player_reb_mae")))
        lines.append(_num_row("AST MAE", s.get("player_ast_mae")))
        lines.append(_pct_row("10–90 coverage", s.get("coverage_10_90")))
        if s.get("top_picks_graded"):
            lines.append(
                _pct_row(
                    "Top picks hit rate",
                    s.get("top_picks_hit_rate"),
                    extra=f"{s['top_picks_hits']}/{s['top_picks_graded']}",
                )
            )
        elif s.get("top_picks") == 0:
            lines.append("| Top confident picks | n/a (none produced) |")
        lines.append("")

        lines.append("### Games")
        lines.append("")
        lines.append(
            "| Matchup | Pred winner | Actual | Hit | Pred score | Actual score | "
            "Pred margin | Act margin | Pred total | Act total |"
        )
        lines.append(
            "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |"
        )
        for g in night.games:
            lines.append(
                f"| {g['matchup']} | {g['pred_winner']} ({100*g['pred_wp']:.0f}%) | "
                f"{g['act_winner']} | {'Y' if g['winner_hit'] else 'N'} | "
                f"{g['pred_score']} | {g['act_score']} | "
                f"{g['pred_margin']:+.1f} | {g['act_margin']:+.1f} | "
                f"{g['pred_total']:.1f} | {g['act_total']:.1f} |"
            )
        lines.append("")

        if night.pick_grades:
            lines.append("### Top confident picks")
            lines.append("")
            lines.append("| Player | Matchup | Stat | Range | Actual | Hit |")
            lines.append("| --- | --- | --- | --- | ---: | --- |")
            for p in night.pick_grades:
                act = "—" if p.actual is None else f"{p.actual:.0f}"
                hit = "—" if p.hit is None else ("Y" if p.hit else "N")
                lines.append(
                    f"| {p.player_name} | {p.team_abbr} vs {p.opponent_abbr} | "
                    f"{p.stat} | {int(p.lo)}-{int(p.hi)} | {act} | {hit} |"
                )
            lines.append("")

        # Compact player coverage table: only players with minutes
        scored = [
            r
            for r in night.player_rows
            if r["stats"].get("min", {}).get("actual", 0) and r["stats"]["min"]["actual"] >= 1
        ]
        scored.sort(key=lambda r: -r["stats"].get("pts", {}).get("actual", 0))
        lines.append("### Player grades (MIN / PTS / REB / AST / STL / BLK)")
        lines.append("")
        lines.append(
            "| Player | Team | MIN pred/act | PTS | REB | AST | STL | BLK | "
            "in 10–90 (any miss listed) |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in scored:
            misses = [
                st.upper()
                for st, d in r["stats"].items()
                if d.get("inside_10_90") is False
            ]
            miss_txt = ",".join(misses) if misses else "all"
            lines.append(
                f"| {r['player_name']} | {r['team_abbr']} | "
                f"{_pa(r,'min')} | {_pa(r,'pts')} | {_pa(r,'reb')} | "
                f"{_pa(r,'ast')} | {_pa(r,'stl')} | {_pa(r,'blk')} | {miss_txt} |"
            )
        lines.append("")

    # Machine-readable sidecar for daily updates (gitignored under results/)
    sidecar = repo_root / "results" / "season_scorecard.json"
    sidecar.write_text(
        json.dumps(
            {
                "season": season,
                "updated": date.today().isoformat(),
                "season_totals": season_tot,
                "nights": [n.summary() for n in nights],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def _pa(row: dict[str, Any], stat: str) -> str:
    d = row["stats"].get(stat)
    if not d:
        return "—/—"
    return f"{d['pred']:.1f}/{d['actual']:.0f}"


def _pct_row(label: str, value: float | None, extra: str | None = None) -> str:
    if value is None:
        return f"| {label} | — |"
    suffix = f" ({extra})" if extra else ""
    return f"| {label} | {100.0 * value:.1f}%{suffix} |"


def _num_row(label: str, value: float | None) -> str:
    if value is None:
        return f"| {label} | — |"
    return f"| {label} | {value:.2f} |"


def _aggregate(summaries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(summaries)
    if not rows:
        return {
            "games_graded": 0,
            "winner_accuracy": None,
            "spread_mae": None,
            "total_mae": None,
            "player_min_mae": None,
            "player_pts_mae": None,
            "coverage_10_90": None,
            "top_picks_hit_rate": None,
            "top_picks_hits": 0,
            "top_picks_graded": 0,
        }
    games = sum(int(r["games_graded"]) for r in rows)
    # Reconstruct weighted means from night summaries (approx via games / rows).
    # Prefer exact recompute via stored abs lists when available — summaries only.
    winner_num = sum(
        (r["winner_accuracy"] or 0.0) * r["games_graded"] for r in rows if r["games_graded"]
    )
    def wavg(key: str, weight_key: str) -> float | None:
        num = 0.0
        den = 0.0
        for r in rows:
            v = r.get(key)
            w = r.get(weight_key) or 0
            if v is None or not w:
                continue
            num += float(v) * float(w)
            den += float(w)
        return num / den if den else None

    pick_hits = sum(int(r.get("top_picks_hits") or 0) for r in rows)
    pick_graded = sum(int(r.get("top_picks_graded") or 0) for r in rows)
    return {
        "games_graded": games,
        "winner_accuracy": winner_num / games if games else None,
        "spread_mae": wavg("spread_mae", "games_graded"),
        "total_mae": wavg("total_mae", "games_graded"),
        "player_min_mae": wavg("player_min_mae", "player_rows"),
        "player_pts_mae": wavg("player_pts_mae", "player_rows"),
        "coverage_10_90": wavg("coverage_10_90", "player_rows"),
        "top_picks_hits": pick_hits,
        "top_picks_graded": pick_graded,
        "top_picks_hit_rate": pick_hits / pick_graded if pick_graded else None,
    }


def _player_names(settings: Settings, season: str) -> dict[int, str]:
    names: dict[int, str] = {}
    for table in ("current_rosters", "player_game_logs"):
        try:
            rows = read_rows(settings, table, season)
        except Exception:
            continue
        for r in rows:
            if r.get("player_id") is None:
                continue
            pid = int(r["player_id"])
            name = r.get("player_name")
            if name and pid not in names:
                names[pid] = str(name)
    # Also prior seasons via logs if needed — skip for speed.
    return names


def _name_index(settings: Settings, season: str) -> dict[tuple[str, str], int]:
    idx: dict[tuple[str, str], int] = {}
    for table in ("current_rosters", "player_game_logs"):
        try:
            rows = read_rows(settings, table, season)
        except Exception:
            continue
        for r in rows:
            if r.get("player_id") is None or not r.get("player_name"):
                continue
            team = str(r.get("team_abbr") or "").upper()
            idx[(team, _norm_name(r["player_name"]))] = int(r["player_id"])
    return idx


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _split_matchup(matchup: str) -> tuple[str, str]:
    # "GSW vs LAL"
    parts = re.split(r"\s+vs\.?\s+", matchup, flags=re.I)
    if len(parts) == 2:
        return parts[0].strip().upper(), parts[1].strip().upper()
    return matchup.strip().upper(), ""


def _parse_range(label: str) -> tuple[float | None, float | None]:
    m = re.search(r"(-?\d+)\s*[-–]\s*(-?\d+)", label)
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))
