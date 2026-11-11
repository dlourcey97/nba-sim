"""Out-of-sample star check on graded slates.

Stars are the top projected-usage players in each window, chosen from the
pregame projection for that game. The gap is their published mean points
against the points they actually scored. Entering season averages are not
the benchmark.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from nba_sim.storage import read_rows
from projections.blend import available_season_window, load_season_bundle
from projections.build import ProjectionCache, build_game_projections


@dataclass
class StarGapReport:
    season: str
    days: int
    start_date: str
    end_date: str
    games: int
    players: int
    player_games: int
    pred_mean: float
    pred_median: float
    actual_mean: float
    gap_pct: float
    threshold_pct: float
    passed: bool


def aggregate_star_gap(
    rows: list[dict[str, Any]],
    *,
    top_n: int = 30,
    min_games: int = 3,
    threshold_pct: float = 5.0,
) -> tuple[float, float, float, float, int, int, bool]:
    """Return pred mean, pred median, actual mean, gap %, players, player-games, passed.

    ``rows`` are one player-game each: player_id, usage, pred_pts, pred_p50, actual_pts.
    """
    by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_player[int(row["player_id"])].append(row)
    ranked = []
    for pid, obs in by_player.items():
        if len(obs) < min_games:
            continue
        usage = sum(float(item["usage"]) for item in obs) / len(obs)
        ranked.append((usage, pid, obs))
    ranked.sort(key=lambda item: -item[0])
    chosen = ranked[:top_n]
    flat = [item for _usage, _pid, obs in chosen for item in obs]
    if len(chosen) < 15 or not flat:
        return 0.0, 0.0, 0.0, 0.0, len(chosen), len(flat), True
    pred = sum(float(item["pred_pts"]) for item in flat) / len(flat)
    pred_med = sum(float(item["pred_p50"]) for item in flat) / len(flat)
    actual = sum(float(item["actual_pts"]) for item in flat) / len(flat)
    gap = 0.0 if actual == 0 else (pred - actual) / abs(actual) * 100.0
    passed = abs(gap) <= threshold_pct
    return pred, pred_med, actual, gap, len(chosen), len(flat), passed


def _as_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def check_graded_star_gap(
    settings,
    *,
    season: str | None = None,
    days: int = 21,
    top_n: int = 30,
    min_games: int = 3,
    threshold_pct: float = 5.0,
    log=None,
) -> StarGapReport:
    """Last ``days`` of graded slates. Block when the points gap exceeds 5%."""
    season = season or settings.current_season
    history = [
        row
        for row in read_rows(settings, "prediction_history", season)
        if str(row.get("row_kind") or "") == "player"
        and row.get("player_id") is not None
        and row.get("actual_pts") is not None
        and row.get("pred_pts_mean") is not None
    ]
    if not history:
        return StarGapReport(
            season=season,
            days=days,
            start_date="",
            end_date="",
            games=0,
            players=0,
            player_games=0,
            pred_mean=0.0,
            pred_median=0.0,
            actual_mean=0.0,
            gap_pct=0.0,
            threshold_pct=threshold_pct,
            passed=True,
        )
    latest = max(_as_date(row["game_date"]) for row in history)
    start = latest - timedelta(days=days - 1)
    newest: dict[tuple[str, int], dict] = {}
    for row in history:
        when = _as_date(row["game_date"])
        if when < start or when > latest:
            continue
        if float(row.get("pred_min_mean") or 0.0) < 1.0:
            continue
        key = (str(row["game_id"]), int(row["player_id"]))
        prev = newest.get(key)
        if prev is None or str(row.get("simulated_at") or "") >= str(prev.get("simulated_at") or ""):
            newest[key] = row
    by_game: dict[str, list[dict]] = defaultdict(list)
    for (game_id, _pid), row in newest.items():
        by_game[game_id].append(row)

    config = settings.config
    seasons_back = list(config["blending"]["season_weights"]["seasons_back"])
    window = available_season_window(settings, season, seasons_back)
    bundles = [load_season_bundle(settings, label) for label in window]
    cache = ProjectionCache()
    observations: list[dict[str, Any]] = []
    graded_games = 0
    for game_id, rows in sorted(by_game.items(), key=lambda item: (_as_date(item[1][0]["game_date"]), item[0])):
        game_date = _as_date(rows[0]["game_date"])
        try:
            projection = build_game_projections(
                settings,
                season=season,
                game_id=game_id,
                as_of=game_date,
                bundles=bundles,
                cache=cache,
            )
        except ValueError:
            continue
        usage = {int(player.player_id): float(player.rates.usage) for player in projection.players}
        used = False
        for row in rows:
            pid = int(row["player_id"])
            if pid not in usage:
                continue
            observations.append(
                {
                    "player_id": pid,
                    "usage": usage[pid],
                    "pred_pts": float(row["pred_pts_mean"]),
                    "pred_p50": float(row.get("pred_pts_p50") or row["pred_pts_mean"]),
                    "actual_pts": float(row["actual_pts"]),
                }
            )
            used = True
        if used:
            graded_games += 1
            if log is not None and graded_games % 20 == 0:
                log(f"star gap projected {graded_games} games")

    pred, pred_med, actual, gap, players, player_games, passed = aggregate_star_gap(
        observations,
        top_n=top_n,
        min_games=min_games,
        threshold_pct=threshold_pct,
    )
    return StarGapReport(
        season=season,
        days=days,
        start_date=start.isoformat(),
        end_date=latest.isoformat(),
        games=graded_games,
        players=players,
        player_games=player_games,
        pred_mean=pred,
        pred_median=pred_med,
        actual_mean=actual,
        gap_pct=gap,
        threshold_pct=threshold_pct,
        passed=passed,
    )
