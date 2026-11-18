"""Split the points, rebound, and assist gap into minutes, rate, opportunity, and the bust tail.

The last three weeks use graded live slates. 2025-26 is the walk-forward season.
Both are resimulated with the current engine, as of the game date. Raw draws are
not saved. A component is the mean of (projection minus actual).
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import argparse
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from nba_sim.schema import ZONES
from nba_sim.settings import load_settings
from nba_sim.storage import read_rows
from projections.blend import available_season_window, load_season_bundle
from projections.build import ProjectionCache, build_game_projections
from sim.engine import simulate_game

_THREE = {"left_corner_3", "right_corner_3", "above_break_3"}
# Both teams' missed shots per possession, the rebound pool the rate line assumes.
_MISS_PER_POSS = 0.90
# Made field goals per team possession, the assist pool the rate line assumes.
_FGM_PER_POSS = 0.46
STATS = ("pts", "reb", "ast")
STATE: dict = {}


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _points_per_min(rates) -> float:
    made = 0.0
    fga = float(getattr(rates, "fga_per_min", 0.0))
    for zone in ZONES:
        value = 3.0 if zone in _THREE else 2.0
        made += fga * float(getattr(rates, f"{zone}_share")) * float(getattr(rates, f"{zone}_fg_pct")) * value
    made += float(getattr(rates, "fta_per_min", 0.0)) * float(getattr(rates, "ft_pct", 0.0))
    return made


def _target_per_min(rates, stat: str) -> float:
    if stat == "pts":
        return _points_per_min(rates)
    return float(getattr(rates, f"{stat}_per_min", 0.0))


def _init(seasons: list[str]) -> None:
    settings = load_settings()
    seasons_back = list(settings.config["blending"]["season_weights"]["seasons_back"])
    bundles = {}
    logs_by_game = {}
    logs_by_player = {}
    pace = {}
    for season in seasons:
        window = available_season_window(settings, season, seasons_back)
        if season not in window:
            window = [season] + window
        bundles[season] = [
            load_season_bundle(settings, label) for label in window if True
        ]
        by_game: dict = {}
        by_player: dict = defaultdict(list)
        for row in read_rows(settings, "player_game_logs", season):
            by_game.setdefault(str(row["game_id"]), {})[int(row["player_id"])] = row
            by_player[int(row["player_id"])].append(row)
        for rows in by_player.values():
            rows.sort(key=lambda item: item["game_date"])
        logs_by_game[season] = by_game
        logs_by_player[season] = dict(by_player)
        pace[season] = {
            (str(row["game_id"]), int(row["team_id"])): float(row.get("pace") or 0.0)
            for row in read_rows(settings, "team_game_results", season)
        }
    STATE["settings"] = settings
    STATE["bundles"] = bundles
    STATE["logs_by_game"] = logs_by_game
    STATE["logs_by_player"] = logs_by_player
    STATE["pace"] = pace
    STATE["cache"] = {season: ProjectionCache() for season in seasons}


def _season_line(rows: list[dict], as_of: date, stat: str) -> tuple[float, float, int]:
    minutes = total = 0.0
    games = 0
    for row in rows:
        if _as_date(row["game_date"]) >= as_of:
            break
        played = float(row.get("minutes") or 0.0)
        if played <= 0.0:
            continue
        minutes += played
        total += float(row.get(stat) or 0.0)
        games += 1
    per_min = total / minutes if minutes > 1.0 else 0.0
    per_game = total / games if games else 0.0
    return per_min, per_game, games


def _bust_drag(draws: np.ndarray, threshold: float) -> float:
    """How far the bust sims pull the mean below the other sims."""
    if draws.size == 0 or threshold <= 0.0:
        return 0.0
    keep = draws >= threshold
    if not np.any(keep) or np.all(keep):
        return 0.0
    return float(draws[keep].mean() - draws.mean())


def score_game(job: dict) -> list[dict]:
    season = job["season"]
    game_id = job["game_id"]
    as_of = _as_date(job["as_of"])
    settings = STATE["settings"]
    try:
        projection = build_game_projections(
            settings,
            season=season,
            game_id=game_id,
            as_of=as_of,
            bundles=STATE["bundles"][season],
            cache=STATE["cache"][season],
        )
    except ValueError:
        return []
    sim = simulate_game(
        projection,
        runs=int(job["runs"]),
        seed=int(job["seed"]),
        config=settings.config,
    )
    logs = STATE["logs_by_game"][season].get(game_id, {})
    player_logs = STATE["logs_by_player"][season]
    pace = STATE["pace"][season]
    proj_pace = {
        "H": float(projection.home_possessions),
        "A": float(projection.away_possessions),
    }
    box_by_team: dict[int, dict[str, float]] = defaultdict(lambda: {"fga": 0.0, "fgm": 0.0})
    for row in logs.values():
        bucket = box_by_team[int(row["team_id"])]
        bucket["fga"] += float(row.get("fga") or 0.0)
        bucket["fgm"] += float(row.get("fgm") or 0.0)
    out = []
    id_to_idx = {int(player.player_id): index for index, player in enumerate(projection.players)}
    for player in projection.players:
        pid = int(player.player_id)
        actual = logs.get(pid)
        if actual is None or player.minutes.out:
            continue
        act_min = float(actual.get("minutes") or 0.0)
        proj_min = float(np.mean(sim.minutes[id_to_idx[pid]]))
        if act_min < 8.0 and proj_min < 8.0:
            continue
        side = player.home_away
        team_id = int(player.team_id)
        act_pace = float(pace.get((game_id, team_id)) or 0.0)
        own = box_by_team[team_id]
        opp_id = next((int(row["team_id"]) for row in logs.values() if int(row["team_id"]) != team_id), 0)
        opp = box_by_team.get(opp_id, {"fga": 0.0, "fgm": 0.0})
        missed = (own["fga"] - own["fgm"]) + (opp["fga"] - opp["fgm"])
        teammate_fgm = own["fgm"] - float(actual.get("fgm") or 0.0)
        proj_poss = proj_pace.get(side, 0.0)
        row = {
            "date": as_of.isoformat(),
            "season": season,
            "game_id": game_id,
            "player_id": pid,
            "name": player.player_name,
            "usage": float(player.rates.usage),
            "started": bool(actual.get("started")),
            "proj_min": proj_min,
            "act_min": act_min,
            "season_games": 0,
            "act_pace": act_pace,
            "proj_pace": proj_poss,
            "missed": missed,
            "teammate_fgm": teammate_fgm,
        }
        history = player_logs.get(pid, [])
        for stat in STATS:
            season_pm, season_pg, games = _season_line(history, as_of, stat)
            target = _target_per_min(player.rates, stat)
            draws = getattr(sim, stat)[id_to_idx[pid]]
            pred = float(np.mean(draws))
            act = float(actual.get(stat) or 0.0)
            game_pm = act / act_min if act_min >= 8.0 else 0.0
            threshold = 0.5 * season_pg if games >= 8 and season_pg > 0.0 else 0.5 * max(pred, 0.1)
            row[f"{stat}_pred"] = pred
            row[f"{stat}_act"] = act
            row[f"{stat}_target"] = target
            row[f"{stat}_season"] = season_pm
            row[f"{stat}_game"] = game_pm
            row[f"{stat}_drag"] = _bust_drag(np.asarray(draws, dtype=float), threshold)
            row[f"{stat}_bust_sim"] = float(np.mean(draws < threshold))
            row[f"{stat}_bust_act"] = float(act < threshold)
            row["season_games"] = games
        out.append(row)
    return out


def _env_ratio(row: dict, stat: str) -> float:
    proj = float(row["proj_pace"])
    if proj <= 1.0:
        return 1.0
    if stat == "pts":
        act = float(row["act_pace"])
        return act / proj if act > 1.0 else 1.0
    if stat == "reb":
        return float(row["missed"]) / max(proj * _MISS_PER_POSS, 1.0)
    return float(row["teammate_fgm"]) / max(proj * _FGM_PER_POSS, 1.0)


def _assign_tiers(rows: list[dict]) -> None:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_date[row["date"]].append(row)
    for group in by_date.values():
        ranked = sorted(group, key=lambda item: -float(item["usage"]))
        top_keys = {(item["game_id"], int(item["player_id"])) for item in ranked[:30]}
        for item in group:
            key = (item["game_id"], int(item["player_id"]))
            if key in top_keys:
                item["tier"] = "top30"
            elif item["started"]:
                item["tier"] = "starter"
            else:
                item["tier"] = "bench"


def _components(row: dict, stat: str) -> dict[str, float]:
    """Projection minus actual. Minutes use his actual per-minute rate.

    Rate is the blend versus his current-season per-minute line. Opportunity
    is the pace, rebound-chance, or teammate-make ratio versus the projection.
    """
    pred = float(row[f"{stat}_pred"])
    act = float(row[f"{stat}_act"])
    proj_min = float(row["proj_min"])
    act_min = float(row["act_min"])
    target = float(row[f"{stat}_target"])
    season = float(row[f"{stat}_season"])
    game = float(row[f"{stat}_game"]) if act_min >= 8.0 else season
    rate_base = season if season > 0.0 else game
    minutes = (proj_min - act_min) * (game if act_min >= 8.0 else rate_base)
    rate = proj_min * (target - rate_base) if rate_base > 0.0 else 0.0
    env = _env_ratio(row, stat)
    opportunity = proj_min * rate_base * (env - 1.0) if rate_base > 0.0 else 0.0
    return {
        "gap": pred - act,
        "minutes": minutes,
        "rate": rate,
        "opportunity": opportunity,
        "bust": -float(row[f"{stat}_drag"]),
        "pred": pred,
        "act": act,
    }


def _summarize(rows: list[dict]) -> str:
    lines = []
    flagged = []
    for stat in STATS:
        lines.append(f"\n== {stat.upper()} ==")
        for tier in ("top30", "starter", "bench"):
            group = [row for row in rows if row["tier"] == tier]
            if not group:
                lines.append(f"{tier}: no players")
                continue
            parts = [_components(row, stat) for row in group]
            def mean(key: str) -> float:
                return float(np.mean([part[key] for part in parts]))

            gap = mean("gap")
            minutes = mean("minutes")
            rate = mean("rate")
            opportunity = mean("opportunity")
            # Actual bust drag across the tier, so the sim tail is compared to the games.
            busts = [row for row in group if row[f"{stat}_bust_act"] >= 1.0]
            kept = [row for row in group if row[f"{stat}_bust_act"] < 1.0]
            actual_drag = 0.0
            if busts and kept:
                actual_drag = float(np.mean([row[f"{stat}_act"] for row in kept]) - np.mean([row[f"{stat}_act"] for row in group]))
            sim_drag = float(np.mean([row[f"{stat}_drag"] for row in group]))
            bust_vs_games = -(sim_drag - actual_drag)
            leftover = gap - minutes - rate - opportunity - bust_vs_games
            sim_bust = float(np.mean([row[f"{stat}_bust_sim"] for row in group]))
            act_bust = float(np.mean([row[f"{stat}_bust_act"] for row in group]))
            names = {
                "minutes": minutes,
                "rate": rate,
                "opportunity": opportunity,
                "bust": bust_vs_games,
                "leftover": leftover,
            }
            biggest = max(names, key=lambda name: abs(names[name]))
            lines.append(
                f"{tier} n={len(group)} pred {mean('pred'):.2f} actual {mean('act'):.2f} "
                f"gap {gap:+.2f} | minutes {minutes:+.2f} rate {rate:+.2f} "
                f"opportunity {opportunity:+.2f} bust {bust_vs_games:+.2f} "
                f"(sim drag {sim_drag:.2f} vs games {actual_drag:.2f}) "
                f"leftover {leftover:+.2f} | biggest {biggest} | "
                f"bust rate sim {sim_bust:.3f} actual {act_bust:.3f}"
            )
            hot = [
                row for row in group
                if int(row["season_games"]) >= 15
                and float(row[f"{stat}_season"]) > 0.0
                and float(row[f"{stat}_target"]) > 0.0
                and float(row[f"{stat}_season"]) > 1.15 * float(row[f"{stat}_target"])
            ]
            if hot:
                pull = float(np.mean([
                    float(row["proj_min"]) * (float(row[f"{stat}_season"]) - float(row[f"{stat}_target"]))
                    for row in hot
                ]))
                lines.append(
                    f"  current season above the blend: {len(hot)} players, "
                    f"giving them their season rate would add {pull:+.2f} to the projection"
                )
            order = sorted(
                range(len(group)),
                key=lambda index: abs(parts[index]["gap"]),
                reverse=True,
            )[:5]
            for index in order:
                row = group[index]
                part = parts[index]
                lines.append(
                    f"  {row['name']} {row['date']} gap {part['gap']:+.1f} "
                    f"min {part['minutes']:+.1f} rate {part['rate']:+.1f} "
                    f"opp {part['opportunity']:+.1f} tail {part['bust']:+.1f} "
                    f"pred {part['pred']:.1f} act {part['act']:.1f} "
                    f"season/min {float(row[f'{stat}_season']):.3f} "
                    f"target/min {float(row[f'{stat}_target']):.3f} games {row['season_games']}"
                )
            if tier == "top30":
                flagged.extend(hot[:5])
    if flagged:
        lines.append("\nPlayers whose current-season rate is well above the blend (first few):")
        seen = set()
        for row in flagged:
            key = (row["name"], row["date"])
            if key in seen:
                continue
            seen.add(key)
            lines.append(
                f"  {row['name']} {row['date']} games {row['season_games']} "
                + " ".join(
                    f"{stat} season {float(row[f'{stat}_season']):.3f} target {float(row[f'{stat}_target']):.3f}"
                    for stat in STATS
                )
            )
    return "\n".join(lines)


def _live_games(settings, start: date, end: date) -> list[dict]:
    rows = read_rows(settings, "prediction_history", "2026-27")
    found: dict[str, dict] = {}
    for row in rows:
        if str(row.get("row_kind")) != "player":
            continue
        if row.get("actual_pts") is None:
            continue
        played = _as_date(row["game_date"])
        if played < start or played > end:
            continue
        found[str(row["game_id"])] = {
            "season": "2026-27",
            "game_id": str(row["game_id"]),
            "as_of": played.isoformat(),
        }
    return list(found.values())


def _season_games(settings, season: str) -> list[dict]:
    schedule = [
        row for row in read_rows(settings, "schedule", season) if row.get("status") == "final"
    ]
    schedule.sort(key=lambda row: (row["game_date"], row["game_id"]))
    return [
        {"season": season, "game_id": str(row["game_id"]), "as_of": _as_date(row["game_date"]).isoformat()}
        for row in schedule
    ]


def run(jobs: list[dict], runs: int, seed: int, workers: int) -> list[dict]:
    seasons = sorted({job["season"] for job in jobs})
    for job in jobs:
        job["runs"] = runs
        job["seed"] = seed
    if workers <= 1:
        _init(seasons)
        rows = []
        for index, job in enumerate(jobs, start=1):
            rows.extend(score_game(job))
            if index % 10 == 0:
                print(f"games {index}/{len(jobs)}", flush=True)
        return rows
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(seasons,)) as pool:
        rows = []
        done = 0
        for batch in pool.map(score_game, jobs, chunksize=1):
            rows.extend(batch)
            done += 1
            if done % 10 == 0:
                print(f"games {done}/{len(jobs)}", flush=True)
        return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--which", choices=("live", "backtest", "both"), default="both")
    parser.add_argument("--runs", type=int, default=300)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--live-start", default="2026-10-28")
    parser.add_argument("--live-end", default="2026-11-17")
    args = parser.parse_args()
    settings = load_settings()
    jobs = []
    if args.which in {"live", "both"}:
        jobs.extend(_live_games(settings, _as_date(args.live_start), _as_date(args.live_end)))
    if args.which in {"backtest", "both"}:
        jobs.extend(_season_games(settings, "2025-26"))
    print(f"GAMES {len(jobs)} runs {args.runs} workers {args.workers}", flush=True)
    rows = run(jobs, args.runs, args.seed, args.workers)
    _assign_tiers(rows)
    # The two samples are reported separately when both were requested.
    text = []
    if args.which in {"live", "both"}:
        text.append("LIVE " + _summarize([row for row in rows if row["season"] == "2026-27"]))
    if args.which in {"backtest", "both"}:
        text.append("BACKTEST 2025-26 " + _summarize([row for row in rows if row["season"] == "2025-26"]))
    report = "\n".join(text)
    print(report, flush=True)
    out = ROOT / "results" / "gap_breakdown.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report + "\n", encoding="utf-8")
    print(f"WROTE {out}", flush=True)


if __name__ == "__main__":
    main()
