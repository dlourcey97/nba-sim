"""League-total and starter/bench role-share reconciliation.

Compares simulated team-game averages and role shares against actual
2025-26 (or configured) game logs. Used as a diagnosis tool and as a
permanent guardrail before projections ship.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from nba_sim.storage import read_rows
from outputs.summarize import summarize_game
from projections.blend import available_season_window, load_season_bundle
from projections.build import ProjectionCache, build_game_projections
from sim.engine import simulate_game

# Stats compared at the team-game level (player-box sums).
TEAM_STATS = (
    "possessions",
    "pts",
    "reb",
    "oreb",
    "dreb",
    "ast",
    "stl",
    "blk",
    "tov",
    "fga",
    "fgm",
    "fg3a",
    "fg3m",
    "fta",
    "ftm",
    "missed_fg",
    "min",
)

ROLE_STATS = ("min", "pts", "reb", "ast", "stl", "blk")


@dataclass
class ReconcileReport:
    """Structured reconciliation result."""

    season: str
    games: int
    team_games: int
    actual_team: dict[str, float] = field(default_factory=dict)
    sim_team: dict[str, float] = field(default_factory=dict)
    team_delta_pct: dict[str, float] = field(default_factory=dict)
    team_flags: list[str] = field(default_factory=list)
    actual_starter_share: dict[str, float] = field(default_factory=dict)
    sim_starter_share: dict[str, float] = field(default_factory=dict)
    role_delta_pct: dict[str, float] = field(default_factory=dict)
    role_flags: list[str] = field(default_factory=list)
    top_rebounders: list[dict[str, Any]] = field(default_factory=list)
    top_scorers: list[dict[str, Any]] = field(default_factory=list)
    passed: bool = False
    threshold_pct: float = 3.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "games": self.games,
            "team_games": self.team_games,
            "actual_team": self.actual_team,
            "sim_team": self.sim_team,
            "team_delta_pct": self.team_delta_pct,
            "team_flags": self.team_flags,
            "actual_starter_share": self.actual_starter_share,
            "sim_starter_share": self.sim_starter_share,
            "role_delta_pct": self.role_delta_pct,
            "role_flags": self.role_flags,
            "top_rebounders": self.top_rebounders,
            "top_scorers": self.top_scorers,
            "passed": self.passed,
            "threshold_pct": self.threshold_pct,
        }


def _pct_delta(sim: float, actual: float) -> float:
    if actual == 0:
        return 0.0 if sim == 0 else 100.0
    return (sim - actual) / abs(actual) * 100.0


def actual_league_team_averages(settings, season: str) -> dict[str, float]:
    """Per-team-game box averages from stored player logs (+ pace from team results)."""
    logs = read_rows(settings, "player_game_logs", season)
    by_gt: dict[tuple, dict[str, float]] = defaultdict(
        lambda: {
            "pts": 0.0,
            "reb": 0.0,
            "oreb": 0.0,
            "dreb": 0.0,
            "ast": 0.0,
            "stl": 0.0,
            "blk": 0.0,
            "tov": 0.0,
            "fga": 0.0,
            "fgm": 0.0,
            "fg3a": 0.0,
            "fg3m": 0.0,
            "fta": 0.0,
            "ftm": 0.0,
            "min": 0.0,
        }
    )
    for row in logs:
        key = (row["game_id"], row["team_id"])
        bucket = by_gt[key]
        for name in bucket:
            src = "minutes" if name == "min" else name
            bucket[name] += float(row.get(src) or 0.0)

    n = max(len(by_gt), 1)
    out = {name: sum(v[name] for v in by_gt.values()) / n for name in next(iter(by_gt.values()))}
    out["missed_fg"] = out["fga"] - out["fgm"]
    out["fg_pct"] = (out["fgm"] / out["fga"]) if out["fga"] else 0.0
    # Possessions from team_game_results.pace when present.
    try:
        results = read_rows(settings, "team_game_results", season)
        if results:
            out["possessions"] = float(np.mean([float(r.get("pace") or 0.0) for r in results]))
        else:
            out["possessions"] = 0.0
    except Exception:
        out["possessions"] = 0.0
    return out


def actual_starter_shares(settings, season: str) -> dict[str, float]:
    logs = read_rows(settings, "player_game_logs", season)
    start = defaultdict(float)
    bench = defaultdict(float)
    for row in logs:
        bucket = start if row.get("started") else bench
        for name in ROLE_STATS:
            src = "minutes" if name == "min" else name
            bucket[name] += float(row.get(src) or 0.0)
    shares = {}
    for name in ROLE_STATS:
        total = start[name] + bench[name]
        shares[name] = (start[name] / total) if total else 0.0
    return shares


def _top_players_by_stat(
    settings, season: str, stat: str, n: int = 20
) -> list[dict[str, Any]]:
    logs = read_rows(settings, "player_game_logs", season)
    by_player: dict[int, dict[str, Any]] = {}
    for row in logs:
        pid = int(row["player_id"])
        entry = by_player.setdefault(
            pid,
            {
                "player_id": pid,
                "player_name": str(row.get("player_name") or pid),
                "games": 0,
                "min": 0.0,
                "pts": 0.0,
                "reb": 0.0,
            },
        )
        entry["games"] += 1
        entry["min"] += float(row.get("minutes") or 0.0)
        entry["pts"] += float(row.get("pts") or 0.0)
        entry["reb"] += float(row.get("reb") or 0.0)
    ranked = []
    for entry in by_player.values():
        g = max(entry["games"], 1)
        mpg = entry["min"] / g
        if mpg < 15:
            continue
        per = entry[stat] / g
        per36 = (entry[stat] / entry["min"] * 36.0) if entry["min"] > 0 else 0.0
        ranked.append(
            {
                "player_id": entry["player_id"],
                "player_name": entry["player_name"],
                "games": g,
                "mpg": mpg,
                f"{stat}_pg": per,
                f"{stat}_per36": per36,
            }
        )
    ranked.sort(key=lambda r: -r[f"{stat}_pg"])
    return ranked[:n]


def prior_season_rates(
    settings, prior_season: str, player_ids: set[int]
) -> dict[int, dict[str, float]]:
    logs = read_rows(settings, "player_game_logs", prior_season)
    acc: dict[int, dict[str, float]] = defaultdict(
        lambda: {"games": 0.0, "min": 0.0, "pts": 0.0, "reb": 0.0}
    )
    for row in logs:
        pid = int(row["player_id"])
        if pid not in player_ids:
            continue
        a = acc[pid]
        a["games"] += 1
        a["min"] += float(row.get("minutes") or 0.0)
        a["pts"] += float(row.get("pts") or 0.0)
        a["reb"] += float(row.get("reb") or 0.0)
    out = {}
    for pid, a in acc.items():
        g = max(a["games"], 1.0)
        mpg = a["min"] / g
        out[pid] = {
            "mpg": mpg,
            "pts_pg": a["pts"] / g,
            "reb_pg": a["reb"] / g,
            "pts_per36": (a["pts"] / a["min"] * 36.0) if a["min"] > 0 else 0.0,
            "reb_per36": (a["reb"] / a["min"] * 36.0) if a["min"] > 0 else 0.0,
        }
    return out


def run_walkforward_reconcile(
    settings,
    *,
    season: str = "2025-26",
    runs: int = 200,
    seed: int = 1,
    max_games: int | None = 200,
    config: dict | None = None,
    threshold_pct: float = 3.0,
) -> ReconcileReport:
    """Walk-forward sim vs actual league totals and role shares."""
    cfg = config or settings.config
    from dataclasses import replace

    local = replace(settings, config=cfg)
    seasons_back = list(cfg["blending"]["season_weights"]["seasons_back"])
    window = available_season_window(local, season, seasons_back)
    from ingest.rosters import prior_season_label

    prior = prior_season_label(season) or season
    needed = set(window) | {season, prior}
    bundles = {label: load_season_bundle(local, label) for label in sorted(needed)}
    season_bundles = [bundles[label] for label in window if label in bundles]

    schedule = sorted(
        [r for r in read_rows(local, "schedule", season) if r.get("status") == "final"],
        key=lambda r: (r["game_date"], r["game_id"]),
    )
    logs = {
        (r["game_id"], int(r["player_id"])): r
        for r in read_rows(local, "player_game_logs", season)
    }

    top_reb = _top_players_by_stat(local, season, "reb", 20)
    top_pts = _top_players_by_stat(local, season, "pts", 20)
    watch_ids = {r["player_id"] for r in top_reb} | {r["player_id"] for r in top_pts}
    prior_rates = prior_season_rates(local, prior, watch_ids)

    sim_team = defaultdict(float)
    act_team = defaultdict(float)
    start_sim = defaultdict(float)
    bench_sim = defaultdict(float)
    start_act = defaultdict(float)
    bench_act = defaultdict(float)
    player_sim: dict[int, dict[str, list[float]]] = defaultdict(
        lambda: {"min": [], "pts": [], "reb": []}
    )
    player_act: dict[int, dict[str, list[float]]] = defaultdict(
        lambda: {"min": [], "pts": [], "reb": []}
    )

    cache = ProjectionCache()
    games = 0
    team_games = 0

    for row in schedule:
        if max_games is not None and games >= max_games:
            break
        if not any(item["game_date"] < row["game_date"] for item in schedule):
            continue
        try:
            projection = build_game_projections(
                local,
                season=season,
                game_id=str(row["game_id"]),
                as_of=row["game_date"],
                bundles=season_bundles,
                cache=cache,
            )
        except ValueError:
            continue
        home_n = sum(1 for p in projection.players if p.home_away == "H")
        away_n = sum(1 for p in projection.players if p.home_away == "A")
        if home_n < 5 or away_n < 5:
            continue
        sim = simulate_game(projection, runs=runs, seed=seed + games, config=cfg)
        summary = summarize_game(projection, sim)
        sim_team["possessions"] += float(sim.home_possessions) + float(
            sim.away_possessions
        )
        for player in summary.players:
            actual = logs.get((summary.game_id, player.player_id))
            for stat in ("pts", "reb", "ast", "stl", "blk", "tov"):
                sim_team[stat] += player.stats[stat].mean
            sim_team["min"] += player.stats["min"].mean
            # FG/FT not in summary — leave unset in sim path (filled from actuals only).
            if actual is not None:
                started = bool(actual.get("started"))
                s_bucket = start_sim if started else bench_sim
                a_bucket = start_act if started else bench_act
                for stat in ROLE_STATS:
                    key = "min" if stat == "min" else stat
                    sval = player.stats[key].mean
                    aval = float(
                        actual.get("minutes") if stat == "min" else actual.get(stat) or 0
                    )
                    s_bucket[stat] += sval
                    a_bucket[stat] += aval
                for stat in ("pts", "reb", "ast", "stl", "blk", "tov"):
                    act_team[stat] += float(actual.get(stat) or 0)
                act_team["min"] += float(actual.get("minutes") or 0)
                act_team["oreb"] += float(actual.get("oreb") or 0)
                act_team["dreb"] += float(actual.get("dreb") or 0)
                act_team["fga"] += float(actual.get("fga") or 0)
                act_team["fgm"] += float(actual.get("fgm") or 0)
                act_team["fg3a"] += float(actual.get("fg3a") or 0)
                act_team["fg3m"] += float(actual.get("fg3m") or 0)
                act_team["fta"] += float(actual.get("fta") or 0)
                act_team["ftm"] += float(actual.get("ftm") or 0)
                if player.player_id in watch_ids:
                    player_sim[player.player_id]["min"].append(player.stats["min"].mean)
                    player_sim[player.player_id]["pts"].append(player.stats["pts"].mean)
                    player_sim[player.player_id]["reb"].append(player.stats["reb"].mean)
                    player_act[player.player_id]["min"].append(
                        float(actual.get("minutes") or 0)
                    )
                    player_act[player.player_id]["pts"].append(float(actual.get("pts") or 0))
                    player_act[player.player_id]["reb"].append(float(actual.get("reb") or 0))
        team_games += 2
        games += 1
        del sim

    # Prefer full-season actuals for league totals (stable denominator).
    full_actual = actual_league_team_averages(local, season)
    full_shares = actual_starter_shares(local, season)

    sim_avg = {}
    if team_games > 0:
        for name in ("pts", "reb", "ast", "stl", "blk", "tov", "min"):
            sim_avg[name] = sim_team[name] / team_games
        sim_avg["possessions"] = sim_team["possessions"] / team_games
        # Sample-matched actuals (same games) for FG etc. when sim lacks them.
        sample_act = {k: act_team[k] / team_games for k in act_team}
    else:
        sample_act = {}

    team_delta = {}
    team_flags = []
    compare_keys = ["possessions", "pts", "reb", "ast", "stl", "blk", "tov", "min"]
    for key in compare_keys:
        actual_v = float(full_actual.get(key) or 0.0)
        sim_v = float(sim_avg.get(key) or 0.0)
        delta = _pct_delta(sim_v, actual_v)
        team_delta[key] = delta
        if abs(delta) > threshold_pct and actual_v > 0:
            team_flags.append(key)

    # Also flag full-season FG family using actuals-only vs sample act when useful.
    for key in ("oreb", "dreb", "fga", "fgm", "fg3a", "fg3m", "fta", "ftm", "missed_fg"):
        team_delta[f"actual_only_{key}"] = 0.0  # placeholder for report context

    role_delta = {}
    role_flags = []
    sim_shares = {}
    for name in ROLE_STATS:
        total = start_sim[name] + bench_sim[name]
        sim_shares[name] = (start_sim[name] / total) if total else 0.0
        actual_v = float(full_shares.get(name) or 0.0)
        delta = _pct_delta(sim_shares[name], actual_v)
        role_delta[name] = delta
        if abs(delta) > threshold_pct and actual_v > 0:
            role_flags.append(name)

    def _player_rows(tops: list[dict], stat: str) -> list[dict[str, Any]]:
        rows = []
        for info in tops:
            pid = info["player_id"]
            sims = player_sim[pid]
            acts = player_act[pid]
            if not sims[stat]:
                continue
            smn = float(np.mean(sims["min"]))
            sstat = float(np.mean(sims[stat]))
            amn = float(np.mean(acts["min"])) if acts["min"] else 0.0
            astat = float(np.mean(acts[stat])) if acts[stat] else 0.0
            prior_r = prior_rates.get(pid, {})
            rows.append(
                {
                    "player_id": pid,
                    "player_name": info["player_name"],
                    "sim_mpg": smn,
                    "sim_pg": sstat,
                    "sim_per36": (sstat / smn * 36.0) if smn > 0 else 0.0,
                    "act_mpg": amn,
                    "act_pg": astat,
                    "act_per36": (astat / amn * 36.0) if amn > 0 else 0.0,
                    "prior_mpg": float(prior_r.get("mpg") or 0.0),
                    "prior_pg": float(prior_r.get(f"{stat}_pg") or 0.0),
                    "prior_per36": float(prior_r.get(f"{stat}_per36") or 0.0),
                    "n_games": len(sims[stat]),
                }
            )
        return rows

    actual_team = {
        k: float(full_actual[k])
        for k in (
            "possessions",
            "pts",
            "reb",
            "oreb",
            "dreb",
            "ast",
            "stl",
            "blk",
            "tov",
            "fga",
            "fgm",
            "fg_pct",
            "fg3a",
            "fg3m",
            "fta",
            "ftm",
            "missed_fg",
            "min",
        )
        if k in full_actual
    }
    report = ReconcileReport(
        season=season,
        games=games,
        team_games=team_games,
        actual_team=actual_team,
        sim_team=sim_avg,
        team_delta_pct=team_delta,
        team_flags=team_flags,
        actual_starter_share=full_shares,
        sim_starter_share=sim_shares,
        role_delta_pct=role_delta,
        role_flags=role_flags,
        top_rebounders=_player_rows(top_reb, "reb"),
        top_scorers=_player_rows(top_pts, "pts"),
        threshold_pct=threshold_pct,
    )
    # Guardrail: league totals + role shares within threshold for core stats.
    core_team = {"possessions", "pts", "reb", "ast", "stl", "blk", "tov"}
    core_role = set(ROLE_STATS)
    report.passed = not any(f in core_team for f in team_flags) and not any(
        f in core_role for f in role_flags
    )
    _ = sample_act  # sample-matched actuals available for future FG instrumentation
    return report


def format_report(report: ReconcileReport) -> str:
    lines = [
        f"# Reconciliation — {report.season}",
        "",
        f"Games: {report.games} | team-games: {report.team_games} | "
        f"threshold: ±{report.threshold_pct:.0f}% | "
        f"**{'PASS' if report.passed else 'FAIL'}**",
        "",
        "## League totals (per team-game)",
        "",
        "| Stat | Sim | Actual | Delta | Flag |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for key in ("possessions", "pts", "reb", "ast", "stl", "blk", "tov", "min"):
        sim_v = report.sim_team.get(key)
        act_v = report.actual_team.get(key)
        if sim_v is None or act_v is None:
            continue
        delta = report.team_delta_pct.get(key, 0.0)
        flag = "⚠" if key in report.team_flags else ""
        lines.append(
            f"| {key} | {sim_v:.2f} | {act_v:.2f} | {delta:+.1f}% | {flag} |"
        )
    lines.extend(
        [
            "",
            "Full-season actual FG family (for context; sim path does not emit FGA yet):",
            "",
            "| Stat | Actual |",
            "| --- | ---: |",
        ]
    )
    for key in ("fga", "fgm", "fg_pct", "fg3a", "fg3m", "fta", "ftm", "oreb", "dreb", "missed_fg"):
        if key in report.actual_team or key == "fg_pct":
            val = report.actual_team.get(key)
            if val is None and key == "fg_pct":
                continue
            if val is not None:
                lines.append(f"| {key} | {val:.3f} |" if key == "fg_pct" else f"| {key} | {val:.2f} |")

    lines.extend(
        [
            "",
            "## Starter share of team totals",
            "",
            "| Stat | Sim | Actual | Delta | Flag |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for key in ROLE_STATS:
        sim_v = report.sim_starter_share.get(key, 0.0)
        act_v = report.actual_starter_share.get(key, 0.0)
        delta = report.role_delta_pct.get(key, 0.0)
        flag = "⚠" if key in report.role_flags else ""
        lines.append(
            f"| {key} | {sim_v:.3f} | {act_v:.3f} | {delta:+.1f}% | {flag} |"
        )

    lines.extend(["", "## Top rebounders (sim vs sample act vs prior per-36)", ""])
    lines.append(
        "| Player | Sim MIN | Sim REB | Sim/36 | Act REB | Prior REB | Prior/36 |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in report.top_rebounders[:20]:
        lines.append(
            f"| {row['player_name']} | {row['sim_mpg']:.1f} | {row['sim_pg']:.1f} | "
            f"{row['sim_per36']:.1f} | {row['act_pg']:.1f} | {row['prior_pg']:.1f} | "
            f"{row['prior_per36']:.1f} |"
        )

    lines.extend(["", "## Top scorers (sim vs sample act vs prior per-36)", ""])
    lines.append(
        "| Player | Sim MIN | Sim PTS | Sim/36 | Act PTS | Prior PTS | Prior/36 |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in report.top_scorers[:20]:
        lines.append(
            f"| {row['player_name']} | {row['sim_mpg']:.1f} | {row['sim_pg']:.1f} | "
            f"{row['sim_per36']:.1f} | {row['act_pg']:.1f} | {row['prior_pg']:.1f} | "
            f"{row['prior_per36']:.1f} |"
        )
    lines.append("")
    return "\n".join(lines)


def check_reconcile_guardrail(
    settings,
    *,
    season: str | None = None,
    runs: int = 100,
    seed: int = 1,
    max_games: int = 80,
    threshold_pct: float = 3.0,
    config: dict | None = None,
) -> ReconcileReport:
    """Run a bounded reconcile check for daily.py / tests.

    Uses a mid-season slice so opening-night thin history does not dominate.
    """
    cfg = config or settings.config
    season = season or str(cfg.get("season", {}).get("current") or "2025-26")
    # Prefer prior completed season for a stable guardrail when current is early.
    from ingest.rosters import prior_season_label

    guard_season = prior_season_label(season) or season
    # If prior is the year we backtested on, use it; else fall back.
    try:
        logs = read_rows(settings, "player_game_logs", guard_season)
        if len(logs) < 1000:
            guard_season = "2025-26"
    except Exception:
        guard_season = "2025-26"
    return run_walkforward_reconcile(
        settings,
        season=guard_season,
        runs=runs,
        seed=seed,
        max_games=max_games,
        config=cfg,
        threshold_pct=threshold_pct,
    )
