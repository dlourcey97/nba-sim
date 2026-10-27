"""Append/upsert prediction history rows; fill actuals after finals."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from nba_sim.schema import GAME_DISTRIBUTIONS, PLAYER_STATS, PERCENTILES
from nba_sim.settings import Settings
from nba_sim.storage import read_rows, store_rows
from outputs.confidence import ConfidentPick
from outputs.summarize import GameSummary, StatSummary


def _empty_pick_fields() -> dict[str, Any]:
    return {
        "pick_stat": "",
        "pick_lo": None,
        "pick_hi": None,
        "pick_median": None,
        "pick_confidence": None,
        "pick_proj_min": None,
        "actual_pick_hit": None,
    }


def history_rows_from_summary(summary: GameSummary) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    game_row: dict[str, Any] = {
        "season": summary.season,
        "game_id": summary.game_id,
        "game_date": summary.game_date,
        "row_kind": "game",
        "player_id": None,
        "team_abbr": None,
        "opponent_abbr": None,
        "home_abbr": summary.home_abbr,
        "away_abbr": summary.away_abbr,
        "simulated_at": summary.simulated_at,
        "runs": summary.runs,
        "seed": summary.seed,
        "home_win_prob": summary.home_win_prob,
        "overtime_prob": summary.overtime_prob,
        "actual_home_pts": None,
        "actual_away_pts": None,
        "actual_overtime": None,
        **_empty_pick_fields(),
    }
    for stat in PLAYER_STATS:
        for percentile in PERCENTILES:
            game_row[f"pred_{stat}_{percentile}"] = None
        game_row[f"actual_{stat}"] = None
    _write_game_dist(game_row, "home_pts", summary.home_pts)
    _write_game_dist(game_row, "away_pts", summary.away_pts)
    _write_game_dist(game_row, "margin", summary.margin)
    _write_game_dist(game_row, "total", summary.total)
    rows.append(game_row)

    for player in summary.players:
        row: dict[str, Any] = {
            "season": summary.season,
            "game_id": summary.game_id,
            "game_date": summary.game_date,
            "row_kind": "player",
            "player_id": player.player_id,
            "team_abbr": player.team_abbr,
            "opponent_abbr": player.opponent_abbr,
            "home_abbr": None,
            "away_abbr": None,
            "simulated_at": summary.simulated_at,
            "runs": summary.runs,
            "seed": summary.seed,
            "home_win_prob": None,
            "overtime_prob": None,
            "actual_home_pts": None,
            "actual_away_pts": None,
            "actual_overtime": None,
            **_empty_pick_fields(),
        }
        for stat in PLAYER_STATS:
            summary_stat = player.stats[stat]
            for percentile in PERCENTILES:
                row[f"pred_{stat}_{percentile}"] = getattr(summary_stat, percentile)
            row[f"actual_{stat}"] = None
        for dist in GAME_DISTRIBUTIONS:
            for percentile in PERCENTILES:
                row[f"pred_{dist}_{percentile}"] = None
        rows.append(row)
    return rows


def pick_history_rows(
    picks: Sequence[ConfidentPick],
    *,
    season: str,
    game_date,
    runs: int,
    seed: int | None,
    simulated_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Rows for top confident picks (claimed confidence logged for grading)."""
    now = simulated_at or datetime.now(timezone.utc).replace(tzinfo=None)
    rows: list[dict[str, Any]] = []
    for pick in picks:
        row: dict[str, Any] = {
            "season": season,
            "game_id": pick.game_id,
            "game_date": game_date,
            "row_kind": "pick",
            "player_id": int(pick.player_id),
            "team_abbr": pick.team_abbr,
            "opponent_abbr": pick.opponent_abbr,
            "home_abbr": None,
            "away_abbr": None,
            "simulated_at": now,
            "runs": runs,
            "seed": seed,
            "home_win_prob": None,
            "overtime_prob": None,
            "actual_home_pts": None,
            "actual_away_pts": None,
            "actual_overtime": None,
            "pick_stat": str(pick.stat).lower(),
            "pick_lo": float(pick.lo),
            "pick_hi": float(pick.hi),
            "pick_median": float(pick.median),
            "pick_confidence": float(pick.confidence),
            "pick_proj_min": float(pick.proj_minutes),
            "actual_pick_hit": None,
        }
        for stat in PLAYER_STATS:
            for percentile in PERCENTILES:
                row[f"pred_{stat}_{percentile}"] = None
            row[f"actual_{stat}"] = None
        for dist in GAME_DISTRIBUTIONS:
            for percentile in PERCENTILES:
                row[f"pred_{dist}_{percentile}"] = None
        rows.append(row)
    return rows


def write_prediction_history(
    settings: Settings,
    summary: GameSummary,
    *,
    allow_historical: bool = False,
) -> int:
    rows = history_rows_from_summary(summary)
    result = store_rows(
        settings,
        "prediction_history",
        summary.season,
        rows,
        allow_historical=allow_historical,
    )
    return result.rows_written


def write_pick_history(
    settings: Settings,
    picks: Sequence[ConfidentPick],
    *,
    season: str,
    game_date,
    runs: int,
    seed: int | None = None,
    allow_historical: bool = False,
) -> int:
    if not picks:
        return 0
    rows = pick_history_rows(
        picks, season=season, game_date=game_date, runs=runs, seed=seed
    )
    result = store_rows(
        settings,
        "prediction_history",
        season,
        rows,
        allow_historical=allow_historical,
    )
    return result.rows_written


def fill_actuals_for_season(
    settings: Settings,
    season: str,
    *,
    allow_historical: bool = False,
) -> int:
    """Upsert actual columns onto existing prediction_history rows for finals."""
    history = read_rows(settings, "prediction_history", season)
    if not history:
        return 0
    logs = read_rows(settings, "player_game_logs", season)
    teams = read_rows(settings, "team_game_results", season)
    schedule = {
        row["game_id"]: row
        for row in read_rows(settings, "schedule", season)
        if row.get("status") == "final"
    }
    log_by_key = {(row["game_id"], int(row["player_id"])): row for row in logs}
    team_by_key = {(row["game_id"], row["team_abbr"]): row for row in teams}

    updated: list[dict[str, Any]] = []
    for row in history:
        game_id = str(row["game_id"])
        sched = schedule.get(game_id)
        if sched is None:
            continue
        new_row = dict(row)
        new_row["pick_stat"] = str(row.get("pick_stat") or "")
        if row["row_kind"] == "game":
            home = team_by_key.get((game_id, sched["home_abbr"]))
            away = team_by_key.get((game_id, sched["away_abbr"]))
            new_row["actual_home_pts"] = sched.get("home_pts")
            new_row["actual_away_pts"] = sched.get("away_pts")
            ot = 0
            if home is not None:
                ot = max(ot, int(home.get("overtime_periods") or 0))
            if away is not None:
                ot = max(ot, int(away.get("overtime_periods") or 0))
            new_row["actual_overtime"] = ot > 0
            updated.append(new_row)
            continue
        player_id = row.get("player_id")
        if player_id is None:
            continue
        log = log_by_key.get((game_id, int(player_id)))
        if row["row_kind"] == "pick":
            stat = str(row.get("pick_stat") or "").lower()
            if stat.startswith("dd"):
                if log is None:
                    hit = False
                else:
                    categories = sum(
                        float(log.get(col) or 0.0) >= 10.0
                        for col in ("pts", "reb", "ast", "stl", "blk")
                    )
                    hit = categories >= 2
                new_row["actual_pick_hit"] = hit
                updated.append(new_row)
                continue
            if log is None:
                # DNP / inactive → miss unless range includes 0 and we treat as 0.
                actual = 0.0
            else:
                col = "minutes" if stat == "min" else stat
                actual = float(log.get(col) or 0.0)
            lo = row.get("pick_lo")
            hi = row.get("pick_hi")
            if lo is not None and hi is not None:
                new_row["actual_pick_hit"] = float(lo) <= actual <= float(hi)
                # Also stamp the matching actual_* for audit.
                if stat in PLAYER_STATS:
                    new_row[f"actual_{stat}"] = actual
            updated.append(new_row)
            continue
        if log is None:
            continue
        new_row["actual_pts"] = float(log["pts"])
        new_row["actual_reb"] = float(log["reb"])
        new_row["actual_ast"] = float(log["ast"])
        new_row["actual_fg3m"] = float(log["fg3m"])
        new_row["actual_stl"] = float(log["stl"])
        new_row["actual_blk"] = float(log["blk"])
        new_row["actual_tov"] = float(log["tov"])
        new_row["actual_min"] = float(log["minutes"])
        new_row["actual_pra"] = float(log["pts"] + log["reb"] + log["ast"])
        new_row["actual_pr"] = float(log["pts"] + log["reb"])
        new_row["actual_pa"] = float(log["pts"] + log["ast"])
        new_row["actual_ra"] = float(log["reb"] + log["ast"])
        updated.append(new_row)

    if not updated:
        return 0
    result = store_rows(
        settings,
        "prediction_history",
        season,
        updated,
        allow_historical=allow_historical,
    )
    return result.rows_written


def _write_game_dist(row: dict[str, Any], name: str, summary: StatSummary) -> None:
    for percentile in PERCENTILES:
        row[f"pred_{name}_{percentile}"] = getattr(summary, percentile)
