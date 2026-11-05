"""Grade prediction_history vs actuals and maintain season_scorecard.md."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from backtest.metrics import crps_from_quantiles
from nba_sim.settings import Settings
from nba_sim.storage import read_rows

_QUANTILE_LEVELS = (0.10, 0.25, 0.50, 0.75, 0.90)
_QUANTILE_KEYS = ("p10", "p25", "p50", "p75", "p90")

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
    player_crps: dict[str, list[float]] = field(default_factory=dict)
    coverage_hits: list[float] = field(default_factory=list)
    pick_grades: list[ConfidentPickGrade] = field(default_factory=list)
    dd_grades: list[ConfidentPickGrade] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        def _mae(vals: list[float]) -> float | None:
            return float(sum(vals) / len(vals)) if vals else None

        def _rate(grades: list[ConfidentPickGrade]) -> dict[str, Any]:
            graded = [p for p in grades if p.hit is not None]
            hits = sum(1 for p in graded if p.hit)
            return {
                "n": len(grades),
                "graded": len(graded),
                "hits": hits,
                "rate": hits / len(graded) if graded else None,
                "claimed": (
                    float(sum(p.confidence for p in graded) / len(graded))
                    if graded
                    else (
                        float(sum(p.confidence for p in grades) / len(grades))
                        if grades
                        else None
                    )
                ),
            }

        pick_hits = _rate(self.pick_grades)
        dd = _rate(self.dd_grades)
        return {
            "game_date": self.game_date,
            "games_graded": self.games_graded,
            "winner_accuracy": (
                self.winner_correct / self.games_graded if self.games_graded else None
            ),
            "spread_mae": _mae(self.spread_abs),
            "total_mae": _mae(self.total_abs),
            "score_mae": _mae(self.score_abs),
            "player_min_crps": _mae(self.player_crps.get("min", [])),
            "player_pts_crps": _mae(self.player_crps.get("pts", [])),
            "player_min_mae": _mae(self.player_mae.get("min", [])),
            "player_pts_mae": _mae(self.player_mae.get("pts", [])),
            "player_reb_mae": _mae(self.player_mae.get("reb", [])),
            "player_ast_mae": _mae(self.player_mae.get("ast", [])),
            "player_stl_mae": _mae(self.player_mae.get("stl", [])),
            "player_blk_mae": _mae(self.player_mae.get("blk", [])),
            "coverage_10_90": _mae(self.coverage_hits),
            "player_rows": len(self.player_rows),
            "top_picks": pick_hits["n"],
            "top_picks_graded": pick_hits["graded"],
            "top_picks_hits": pick_hits["hits"],
            "top_picks_hit_rate": pick_hits["rate"],
            "top_picks_avg_claimed_conf": pick_hits["claimed"],
            "dd_picks": dd["n"],
            "dd_graded": dd["graded"],
            "dd_hits": dd["hits"],
            "dd_hit_rate": dd["rate"],
            "dd_avg_claimed": dd["claimed"],
        }


def _published_crps(row: dict[str, Any], stat: str) -> float | None:
    """CRPS of the five stored percentiles. All zeros is a point mass at 0."""
    actual = row.get(f"actual_{stat}")
    if actual is None:
        return None
    quantiles = [row.get(f"pred_{stat}_{key}") for key in _QUANTILE_KEYS]
    if any(value is None for value in quantiles):
        return None
    return crps_from_quantiles(
        _QUANTILE_LEVELS, [float(value) for value in quantiles], float(actual)
    )


_LOG_CACHE: dict[str, list[dict[str, Any]]] = {}


def _score_unprojected(
    night: NightGrade, settings: Settings, season: str, game_date: str
) -> None:
    """A player who played and was not projected is a point mass at 0."""
    if not night.player_rows:
        return
    game_ids = {str(row["game_id"]) for row in night.player_rows}
    graded = {(str(row["game_id"]), int(row["player_id"])) for row in night.player_rows}
    if season not in _LOG_CACHE:
        try:
            _LOG_CACHE[season] = list(read_rows(settings, "player_game_logs", season))
        except FileNotFoundError:
            _LOG_CACHE[season] = []
    logs = _LOG_CACHE[season]
    for log in logs:
        if str(log.get("game_date"))[:10] != game_date[:10]:
            continue
        if str(log.get("game_id")) not in game_ids:
            continue
        if float(log.get("minutes") or 0.0) <= 0.0:
            continue
        key = (str(log.get("game_id")), int(log.get("player_id") or 0))
        if key in graded:
            continue
        graded.add(key)
        minutes = float(log.get("minutes") or 0.0)
        points = float(log.get("pts") or 0.0)
        night.player_rows.append(
            {
                "game_id": key[0],
                "player_id": key[1],
                "player_name": log.get("player_name") or f"player:{key[1]}",
                "team_abbr": log.get("team_abbr"),
                "unprojected": True,
                "stats": {
                    "min": {
                        "pred": 0.0,
                        "actual": minutes,
                        "abs_err": minutes,
                        "p10": 0.0,
                        "p90": 0.0,
                        "inside_10_90": False,
                    },
                    "pts": {
                        "pred": 0.0,
                        "actual": points,
                        "abs_err": points,
                        "p10": 0.0,
                        "p90": 0.0,
                        "inside_10_90": points == 0.0,
                    },
                },
            }
        )
        night.player_mae.setdefault("min", []).append(minutes)
        night.player_mae.setdefault("pts", []).append(points)
        night.player_crps.setdefault("min", []).append(minutes)
        night.player_crps.setdefault("pts", []).append(points)
        night.coverage_hits.append(0.0)


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
            if stat in {"min", "pts"}:
                score = _published_crps(p, stat)
                if score is not None:
                    night.player_crps.setdefault(stat, []).append(score)
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

    _score_unprojected(night, settings, season, game_date)

    # Prefer logged pick rows from prediction_history (claimed confidence).
    hist_picks = [
        r
        for r in history
        if r["row_kind"] == "pick" and str(r["game_date"]) == game_date
    ]
    if hist_picks:
        graded_picks = _grade_history_picks(hist_picks, name_by_id)
        night.pick_grades = [p for p in graded_picks if not p.stat.upper().startswith("DD")]
        night.dd_grades = [p for p in graded_picks if p.stat.upper().startswith("DD")]
    elif picks:
        night.pick_grades = grade_confident_picks(
            settings, season, picks, game_date=game_date
        )
    return night


def _grade_history_picks(
    rows: Sequence[dict[str, Any]],
    name_by_id: dict[int, str] | None = None,
) -> list[ConfidentPickGrade]:
    out: list[ConfidentPickGrade] = []
    names = name_by_id or {}
    for row in rows:
        stat = str(row.get("pick_stat") or "").lower()
        hit = row.get("actual_pick_hit")
        actual_val = row.get(f"actual_{stat}") if stat else None
        if hit is None and row.get("pick_lo") is not None and actual_val is not None:
            hit = float(row["pick_lo"]) <= float(actual_val) <= float(row["pick_hi"])
        pid = row.get("player_id")
        out.append(
            ConfidentPickGrade(
                player_name=names.get(int(pid), f"player:{pid}") if pid is not None else "player",
                team_abbr=str(row.get("team_abbr") or ""),
                opponent_abbr=str(row.get("opponent_abbr") or ""),
                stat=stat.upper(),
                lo=float(row.get("pick_lo") or 0.0),
                hi=float(row.get("pick_hi") or 0.0),
                median=float(row.get("pick_median") or 0.0),
                confidence=float(row.get("pick_confidence") or 0.0),
                actual=None if actual_val is None else float(actual_val),
                hit=None if hit is None else bool(hit),
            )
        )
    return out


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
        settings.repo_root,
        season=active,
        nights=nights,
        notes=notes,
        pending=_pending_predictions(history),
    )


def _pending_predictions(history: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Simulated games that do not have a final score yet."""
    rows: list[dict[str, Any]] = []
    for row in history:
        if row.get("row_kind") != "game" or row.get("actual_home_pts") is not None:
            continue
        if row.get("pred_total_p50") is None:
            continue
        home_wp = float(row.get("home_win_prob") or 0.5)
        margin = float(row["pred_margin_p50"])
        if home_wp >= 0.5:
            winner, wp = row["home_abbr"], home_wp
        else:
            winner, wp = row["away_abbr"], 1.0 - home_wp
        if margin >= 0:
            spread = f"{row['home_abbr']} by {abs(margin):.0f}"
        else:
            spread = f"{row['away_abbr']} by {abs(margin):.0f}"
        rows.append(
            {
                "game_date": str(row["game_date"]),
                "game_id": str(row["game_id"]),
                "matchup": f"{row['away_abbr']} @ {row['home_abbr']}",
                "winner": winner,
                "wp": wp,
                "score": (
                    f"{row['away_abbr']} {float(row['pred_away_pts_p50']):.0f}–"
                    f"{row['home_abbr']} {float(row['pred_home_pts_p50']):.0f}"
                ),
                "spread": spread,
                "total": float(row["pred_total_p50"]),
            }
        )
    rows.sort(key=lambda item: (item["game_date"], item["game_id"]))
    return rows


def _dunks_fallback_lines(repo_root: Path, season: str) -> list[str]:
    """Live-only grade for players whose minutes were filled from Dunks.

    This block is not part of the season totals above. A row exists only when
    our projection was 0 minutes, the player was not out, and EPM or that
    night's box had a number.
    """
    lines = ["## Dunks minute fallback", ""]
    lines.append(
        "Separate from the season grade. These are healthy players we had at "
        "0 minutes who received an EPM or same-day box minute number. The "
        "check is the next seven live days, not the backtest."
    )
    lines.append("")
    path = repo_root / "results" / "dunks_fallback.jsonl"
    if not path.is_file():
        lines.append("No fallback rows yet.")
        lines.append("")
        return lines
    import json

    events = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        row = json.loads(raw)
        if str(row.get("season") or season) == season:
            events.append(row)
    if not events:
        lines.append("No fallback rows for this season yet.")
        lines.append("")
        return lines
    actuals: dict[tuple[str, int], float] = {}
    try:
        from nba_sim.settings import load_settings
        from nba_sim.storage import read_rows

        settings = load_settings()
        for log in read_rows(settings, "player_game_logs", season):
            actuals[(str(log["game_id"]), int(log["player_id"]))] = float(log["minutes"])
    except Exception:
        actuals = {}
    graded = []
    played = 0
    for event in events:
        actual = actuals.get((str(event.get("game_id")), int(event["player_id"])))
        if actual is None:
            continue
        graded.append(abs(float(event["minutes_after"]) - actual))
        if actual >= 8.0:
            played += 1
    mae = sum(graded) / len(graded) if graded else None
    lines.append("| Rows | Graded | Played 8+ | Minute MAE |")
    lines.append("| ---: | ---: | ---: | ---: |")
    mae_txt = "—" if mae is None else f"{mae:.2f}"
    lines.append(f"| {len(events)} | {len(graded)} | {played} | {mae_txt} |")
    lines.append("")
    return lines


def _dunks_minutes_comparison_lines(repo_root: Path, season: str) -> list[str]:
    """Minutes MAE for the stored sim against the same-day Dunks box.

    The stored sim is the engine when that night's files were archived after
    tip, and the blend when both the EPM snapshot and the minutes file were
    already on disk. Dunks-only is the box minute versus the actual minute.
    """
    lines = ["## Dunks minutes vs the sim", ""]
    try:
        from nba_sim.settings import load_settings

        settings = load_settings()
    except Exception:
        lines.append("Dunks archive could not be read.")
        lines.append("")
        return lines
    dunks = Path(settings.data_dir) / "external" / "dunks"
    if not dunks.is_dir():
        lines.append("No Dunks archive.")
        lines.append("")
        return lines
    box_files = sorted(dunks.glob("box_*.parquet"))
    if not box_files:
        lines.append("No same-day minutes files.")
        lines.append("")
        return lines
    import pyarrow.parquet as pq

    history = {
        (str(row["game_date"])[:10], int(row["player_id"])): row
        for row in read_rows(settings, "prediction_history", season)
        if row["row_kind"] == "player" and row.get("player_id") is not None
    }
    epm_files = []
    for path in dunks.glob("epm_*.parquet"):
        match = re.search(r"_(\d{4}-\d{2}-\d{2})\.parquet$", path.name)
        if match:
            epm_files.append((match.group(1), path.stat().st_mtime))
    epm_files.sort()

    lines.append(
        "Same players, same nights. Engine is the stored sim on nights whose "
        "Dunks files landed after that sim. Blend is the stored sim on nights "
        "that already had both files. Dunks is the same-day minutes file. "
        "A blank cell was not measured."
    )
    lines.append("")
    lines.append("| Date | Players | Engine MAE | Dunks MAE | Blend MAE |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    partial: list[str] = []
    totals = {"engine": [], "dunks": [], "blend": []}
    for path in box_files:
        match = re.search(r"_(\d{4}-\d{2}-\d{2})\.parquet$", path.name)
        if match is None:
            continue
        slate = match.group(1)
        box_mtime = path.stat().st_mtime
        epm_mtime = None
        for stamped, mtime in epm_files:
            if stamped <= slate:
                epm_mtime = mtime
        engine_err: list[float] = []
        dunks_err: list[float] = []
        blend_err: list[float] = []
        published_err: list[float] = []
        sim_times: list[float] = []
        for row in pq.read_table(path).to_pylist():
            pred = history.get((slate, int(row["player_id"])))
            if pred is None or pred.get("actual_min") is None or pred.get("pred_min_mean") is None:
                continue
            actual = float(pred["actual_min"])
            dunks_err.append(abs(float(row["minutes"]) - actual))
            published_err.append(abs(float(pred["pred_min_mean"]) - actual))
            stamped = _epoch(pred.get("simulated_at"))
            if stamped is not None:
                sim_times.append(stamped)
        sim_at = max(sim_times) if sim_times else None
        saw_box = sim_at is not None and sim_at >= box_mtime
        saw_epm = sim_at is not None and epm_mtime is not None and sim_at >= epm_mtime
        if saw_box and saw_epm:
            blend_err = published_err
        elif not saw_box and not saw_epm:
            engine_err = published_err
        elif published_err:
            partial.append(slate)
        if not dunks_err:
            continue
        totals["dunks"].extend(dunks_err)
        totals["engine"].extend(engine_err)
        totals["blend"].extend(blend_err)
        lines.append(
            f"| {slate} | {len(dunks_err)} | {_mae(engine_err)} | {_mae(dunks_err)} | {_mae(blend_err)} |"
        )
    if len(totals["dunks"]) > len(box_files):
        lines.append(
            f"| Compared | {len(totals['dunks'])} | {_mae(totals['engine'])} | "
            f"{_mae(totals['dunks'])} | {_mae(totals['blend'])} |"
        )
    lines.append("")
    if partial:
        days = ", ".join(sorted(set(partial)))
        lines.append(
            f"Published sim on {days} saw the EPM snapshot or the minutes file, but not both, "
            "so it is neither column."
        )
        lines.append("")
    return lines


def _epoch(value: object) -> float | None:
    if value is None:
        return None
    if hasattr(value, "timestamp"):
        return float(value.timestamp())  # type: ignore[no-any-return]
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _mae(errors: list[float]) -> str:
    if not errors:
        return "—"
    return f"{sum(errors) / len(errors):.2f}"


def write_season_scorecard(
    repo_root: Path,
    *,
    season: str,
    nights: Sequence[NightGrade],
    notes: Sequence[str] | None = None,
    pending: Sequence[dict[str, Any]] | None = None,
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
        "Graded from `prediction_history` after finals. No sportsbook lines or odds. "
        "Player CRPS is the score of the published p10/p25/p50/p75/p90 curve "
        "(a player who played and was not projected is a point mass at 0). "
        "MAE is the absolute error of the median, shown beside CRPS."
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
    lines.append(_num_row("Player MIN CRPS", season_tot.get("player_min_crps")))
    lines.append(_num_row("Player PTS CRPS", season_tot.get("player_pts_crps")))
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
    lines.append(
        _pct_row(
            "Top picks avg claimed confidence",
            season_tot.get("top_picks_avg_claimed_conf"),
        )
    )
    if season_tot.get("dd_graded"):
        lines.append(
            _pct_row(
                "Double-double hit rate",
                season_tot.get("dd_hit_rate"),
                extra=f"{season_tot.get('dd_hits', 0)}/{season_tot.get('dd_graded', 0)}",
            )
        )
        lines.append(
            _pct_row(
                "Double-double avg claimed P(DD)",
                season_tot.get("dd_avg_claimed"),
            )
        )
    bias_num = 0.0
    bias_den = 0
    for night in nights:
        if night.games:
            bias_num += sum(float(g["total_err"]) for g in night.games)
            bias_den += len(night.games)
    season_bias = bias_num / bias_den if bias_den else None
    lines.append(_num_row("Total bias (pred − actual)", season_bias))
    lines.append("")
    lines.append("## Per night")
    lines.append("")
    lines.append(
        "| Date | Games | Winner | Spread MAE | Total MAE | Total bias | "
        "MIN CRPS | PTS CRPS | MIN MAE | PTS MAE | REB | AST | STL | BLK | "
        "10–90 | Picks | Claimed | DD | DD claimed |"
    )
    lines.append(
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    )
    for night in nights:
        s = night.summary()
        if not s["games_graded"]:
            continue
        bias = (
            sum(float(g["total_err"]) for g in night.games) / len(night.games)
            if night.games
            else None
        )
        if s.get("top_picks_graded"):
            picks = (
                f"{s['top_picks_hits']}/{s['top_picks_graded']} "
                f"({100.0 * s['top_picks_hit_rate']:.1f}%)"
            )
        else:
            picks = "n/a"
        claimed = (
            f"{100.0 * s['top_picks_avg_claimed_conf']:.1f}%"
            if s.get("top_picks_avg_claimed_conf") is not None and s.get("top_picks_graded")
            else "—"
        )
        if s.get("dd_graded"):
            dd = (
                f"{s['dd_hits']}/{s['dd_graded']} "
                f"({100.0 * s['dd_hit_rate']:.1f}%)"
            )
            dd_claimed = f"{100.0 * s['dd_avg_claimed']:.1f}%"
        else:
            dd, dd_claimed = "n/a", "—"
        lines.append(
            f"| {night.game_date} | {s['games_graded']} | "
            f"{_pct(s.get('winner_accuracy'))} | {_n(s.get('spread_mae'))} | "
            f"{_n(s.get('total_mae'))} | {_n(bias)} | {_n(s.get('player_min_crps'))} | "
            f"{_n(s.get('player_pts_crps'))} | {_n(s.get('player_min_mae'))} | "
            f"{_n(s.get('player_pts_mae'))} | {_n(s.get('player_reb_mae'))} | "
            f"{_n(s.get('player_ast_mae'))} | {_n(s.get('player_stl_mae'))} | "
            f"{_n(s.get('player_blk_mae'))} | {_pct(s.get('coverage_10_90'))} | "
            f"{picks} | {claimed} | {dd} | {dd_claimed} |"
        )
    if season_tot.get("games_graded"):
        lines.append(
            f"| Season | {season_tot['games_graded']} | "
            f"{_pct(season_tot.get('winner_accuracy'))} | {_n(season_tot.get('spread_mae'))} | "
            f"{_n(season_tot.get('total_mae'))} | {_n(season_bias)} | "
            f"{_n(season_tot.get('player_min_crps'))} | {_n(season_tot.get('player_pts_crps'))} | "
            f"{_n(season_tot.get('player_min_mae'))} | {_n(season_tot.get('player_pts_mae'))} | "
            f"{_n(season_tot.get('player_reb_mae'))} | {_n(season_tot.get('player_ast_mae'))} | "
            f"{_n(season_tot.get('player_stl_mae'))} | {_n(season_tot.get('player_blk_mae'))} | "
            f"{_pct(season_tot.get('coverage_10_90'))} | "
            f"{season_tot.get('top_picks_hits', 0)}/{season_tot.get('top_picks_graded', 0)} "
            f"({_pct(season_tot.get('top_picks_hit_rate'))}) | "
            f"{_pct(season_tot.get('top_picks_avg_claimed_conf'))} | "
            f"{season_tot.get('dd_hits', 0)}/{season_tot.get('dd_graded', 0)} "
            f"({_pct(season_tot.get('dd_hit_rate'))}) | "
            f"{_pct(season_tot.get('dd_avg_claimed'))} |"
        )
    lines.append("")

    if pending:
        lines.append("## Pending predictions")
        lines.append("")
        lines.append(
            "Simulated games with no final yet. These rows are not in the graded totals."
        )
        lines.append("")
        lines.append("| Date | Matchup | Winner | Win % | Median score | Spread | Total |")
        lines.append("| --- | --- | --- | ---: | --- | --- | ---: |")
        for row in pending:
            lines.append(
                f"| {row['game_date']} | {row['matchup']} | {row['winner']} | "
                f"{100.0 * row['wp']:.1f}% | {row['score']} | {row['spread']} | "
                f"{row['total']:.1f} |"
            )
        lines.append("")

    if notes:
        lines.append("## Notes")
        lines.append("")
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")

    lines.extend(_dunks_fallback_lines(repo_root, season))
    lines.extend(_dunks_minutes_comparison_lines(repo_root, season))

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
            lines.append(
                _pct_row(
                    "Top picks avg claimed confidence",
                    s.get("top_picks_avg_claimed_conf"),
                )
            )
        if s.get("dd_graded"):
            lines.append(
                _pct_row(
                    "Double-double hit rate",
                    s.get("dd_hit_rate"),
                    extra=f"{s['dd_hits']}/{s['dd_graded']}",
                )
            )
            lines.append(
                _pct_row(
                    "Double-double avg claimed P(DD)",
                    s.get("dd_avg_claimed"),
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

        if night.dd_grades:
            lines.append("### Double-doubles")
            lines.append("")
            lines.append("| Player | Matchup | Pair | Claimed | Hit |")
            lines.append("| --- | --- | --- | ---: | --- |")
            for p in night.dd_grades:
                pair = p.stat.upper().removeprefix("DD_").replace("_", "+")
                hit = "—" if p.hit is None else ("Y" if p.hit else "N")
                lines.append(
                    f"| {p.player_name} | {p.team_abbr} vs {p.opponent_abbr} | "
                    f"{pair} | {100.0 * p.confidence:.1f}% | {hit} |"
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


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{100.0 * value:.1f}%"


def _n(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


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
            "player_min_crps": None,
            "player_pts_crps": None,
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
    conf_num = 0.0
    conf_den = 0.0
    for r in rows:
        c = r.get("top_picks_avg_claimed_conf")
        w = r.get("top_picks_graded") or r.get("top_picks") or 0
        if c is None or not w:
            continue
        conf_num += float(c) * float(w)
        conf_den += float(w)
    return {
        "games_graded": games,
        "winner_accuracy": winner_num / games if games else None,
        "spread_mae": wavg("spread_mae", "games_graded"),
        "total_mae": wavg("total_mae", "games_graded"),
        "player_min_crps": wavg("player_min_crps", "player_rows"),
        "player_pts_crps": wavg("player_pts_crps", "player_rows"),
        "player_min_mae": wavg("player_min_mae", "player_rows"),
        "player_pts_mae": wavg("player_pts_mae", "player_rows"),
        "player_reb_mae": wavg("player_reb_mae", "player_rows"),
        "player_ast_mae": wavg("player_ast_mae", "player_rows"),
        "player_stl_mae": wavg("player_stl_mae", "player_rows"),
        "player_blk_mae": wavg("player_blk_mae", "player_rows"),
        "coverage_10_90": wavg("coverage_10_90", "player_rows"),
        "top_picks_hits": pick_hits,
        "top_picks_graded": pick_graded,
        "top_picks_hit_rate": pick_hits / pick_graded if pick_graded else None,
        "top_picks_avg_claimed_conf": conf_num / conf_den if conf_den else None,
        "dd_hits": sum(int(r.get("dd_hits") or 0) for r in rows),
        "dd_graded": sum(int(r.get("dd_graded") or 0) for r in rows),
        "dd_hit_rate": (
            sum(int(r.get("dd_hits") or 0) for r in rows)
            / sum(int(r.get("dd_graded") or 0) for r in rows)
            if sum(int(r.get("dd_graded") or 0) for r in rows)
            else None
        ),
        "dd_avg_claimed": wavg("dd_avg_claimed", "dd_graded"),
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
