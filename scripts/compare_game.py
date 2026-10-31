"""Run one game on config.yaml and config_experimental.yaml and compare.

Does not read sportsbook lines. Does not change config.yaml.

  PYTHONPATH=. .venv/bin/python scripts/compare_game.py \\
    --date 2026-10-31 --away OKC --home HOU
"""

from __future__ import annotations

import argparse
import copy
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dataclasses import replace

from backtest.reconcile import check_reconcile_guardrail
from ingest.rosters import _NBA_TEAM_ABBRS
from ingest.source import NbaSource
from nba_sim.settings import load_settings
from nba_sim.storage import read_rows, store_rows
from outputs.pipeline import injuries_for_date, run_game
from outputs.summarize import GameSummary

_ROSTER_COLS = (
    "season",
    "team_id",
    "team_abbr",
    "player_id",
    "player_name",
    "position",
    "jersey",
    "preseason_appeared",
    "refreshed_at",
)
_FEATURES = (
    "referees",
    "play_types",
    "bball_roles",
    "bball_defense",
    "bball_matchups",
    "step_f",
)


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _enable(config: dict, name: str) -> dict:
    cfg = copy.deepcopy(config)
    ctx = cfg["context"]
    if name == "referees":
        ctx["referees_enabled"] = True
    elif name == "play_types":
        ctx["play_types_enabled"] = True
        ctx["play_type_defense_weight"] = 0.15
    elif name == "bball_roles":
        ctx["bball_roles_enabled"] = True
    elif name == "bball_defense":
        ctx["bball_defense_enabled"] = True
    elif name == "bball_matchups":
        ctx["bball_matchups_enabled"] = True
    elif name == "step_f":
        cfg["features"]["minutes_model"] = "engine"
        cfg["features"]["stint_rotations_step_f"] = True
    else:
        raise KeyError(name)
    return cfg


def _stack(config: dict, names: list[str]) -> dict:
    cfg = copy.deepcopy(config)
    for name in names:
        cfg = _enable(cfg, name)
    return cfg


def _flag_line(report) -> str:
    bits = []
    for key in report.team_flags:
        bits.append(f"team {key} {report.team_delta_pct.get(key, 0):+.1f}%")
    for key in report.role_flags:
        bits.append(f"starter {key} {report.role_delta_pct.get(key, 0):+.1f}%")
    return ", ".join(bits) if bits else "none"


def _guardrail(settings):
    print("reconcile guardrail (80 games, skip 400, seed 1, ±3%)", flush=True)
    report = check_reconcile_guardrail(
        settings,
        runs=80,
        max_games=80,
        skip_games=400,
        seed=1,
        threshold_pct=3.0,
    )
    status = "PASS" if report.passed else "FAIL"
    print(
        f"reconcile {status} games={report.games} flags: {_flag_line(report)}",
        flush=True,
    )
    return report


def _isolate(main_settings, names: list[str]) -> list[str]:
    """Name the feature, or the smallest set, that fails the guardrail."""
    base = main_settings.config
    alone = []
    for name in names:
        print(f"isolate feature {name}", flush=True)
        trial = replace(main_settings, config=_enable(base, name))
        report = _guardrail(trial)
        if not report.passed:
            alone.append(name)
    if alone:
        return alone
    # No feature fails by itself. Leave each one out of the full stack.
    necessary = []
    for name in names:
        subset = [item for item in names if item != name]
        print(f"isolate without {name}", flush=True)
        trial = replace(main_settings, config=_stack(base, subset))
        report = _guardrail(trial)
        if report.passed:
            necessary.append(name)
    if necessary:
        return necessary
    return list(names)


def refresh_teams(settings, abbrs: set[str]) -> None:
    id_by_abbr = {abbr: team_id for team_id, abbr in _NBA_TEAM_ABBRS.items()}
    unknown = sorted(abbrs - set(id_by_abbr))
    if unknown:
        raise SystemExit(f"unknown team abbreviations: {unknown}")
    http = settings.config["http"]
    source = NbaSource(
        delay_seconds=float(http["delay_seconds"]),
        max_retries=int(http["max_retries"]),
        backoff_seconds=float(http["backoff_seconds"]),
        timeout_seconds=float(http["timeout_seconds"]),
        log=print,
        current_season=settings.current_season,
    )
    season = settings.current_season
    existing = read_rows(settings, "current_rosters", season)
    keep = [row for row in existing if str(row["team_abbr"]) not in abbrs]
    other_teams = {str(row["team_abbr"]) for row in keep}
    if len(other_teams) < 28:
        raise SystemExit(
            f"refusing roster refresh: only {len(other_teams)} other teams on disk"
        )
    pre_logs = read_rows(
        settings, "player_game_logs", season, season_type="Preseason"
    )
    appeared = {(int(row["team_id"]), int(row["player_id"])) for row in pre_logs}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    fresh: list[dict] = []
    for abbr in sorted(abbrs):
        team_id = id_by_abbr[abbr]
        fetched = source.common_team_roster(team_id, season)
        if not fetched:
            raise SystemExit(f"CommonTeamRoster returned no players for {abbr}")
        print(f"roster {abbr}: {len(fetched)} players", flush=True)
        for player in fetched:
            pid = int(player["player_id"])
            fresh.append(
                {
                    "season": season,
                    "team_id": team_id,
                    "team_abbr": abbr,
                    "player_id": pid,
                    "player_name": str(player.get("player_name") or f"player:{pid}"),
                    "position": None
                    if player.get("position") is None
                    else str(player["position"]),
                    "jersey": None if player.get("jersey") is None else str(player["jersey"]),
                    "preseason_appeared": (team_id, pid) in appeared,
                    "refreshed_at": now,
                }
            )
    old = {
        (str(row["team_abbr"]), int(row["player_id"])): str(row["player_name"])
        for row in existing
        if str(row["team_abbr"]) in abbrs
    }
    new = {
        (str(row["team_abbr"]), int(row["player_id"])): str(row["player_name"])
        for row in fresh
    }
    for key in sorted(set(new) - set(old)):
        print(f"roster added {key[0]} {new[key]}", flush=True)
    for key in sorted(set(old) - set(new)):
        print(f"roster removed {key[0]} {old[key]}", flush=True)
    if not (set(new) - set(old) or set(old) - set(new)):
        print("roster membership unchanged for both teams", flush=True)
    merged = [{col: row[col] for col in _ROSTER_COLS} for row in keep]
    merged.extend(fresh)
    if len(merged) < len(existing) - 20:
        raise SystemExit("refusing roster write that would drop more than 20 players")
    store_rows(settings, "current_rosters", season, merged, allow_historical=True)
    print(f"current_rosters rewritten: {len(merged)} players", flush=True)


def _print_injuries(entries, abbrs: set[str]) -> None:
    wanted = {"out", "doubtful", "questionable"}
    rows = [
        entry
        for entry in entries
        if str(entry.team_abbr or "") in abbrs and entry.status.lower() in wanted
    ]
    print("overrides.yaml: no player overrides (players list is empty)", flush=True)
    override_hits = [entry for entry in entries if entry.source == "override"]
    if override_hits:
        print(f"override rows applied: {len(override_hits)}", flush=True)
        for entry in override_hits:
            print(
                f"  OVERRIDE {entry.team_abbr} {entry.player_name} {entry.status} {entry.reason}",
                flush=True,
            )
    if not rows:
        print("OUT / DOUBTFUL / QUESTIONABLE: none for these teams", flush=True)
        return
    print("OUT / DOUBTFUL / QUESTIONABLE", flush=True)
    print("Doubtful is held out of the sim. Questionable is a minutes haircut.", flush=True)
    for entry in sorted(rows, key=lambda item: (item.team_abbr or "", item.status, item.player_name)):
        print(
            f"  {entry.status.upper():<13} {entry.team_abbr} {entry.player_name} — {entry.reason} [{entry.source}]",
            flush=True,
        )


def _top(summary: GameSummary, abbr: str) -> list:
    players = [player for player in summary.players if player.team_abbr == abbr]
    players.sort(key=lambda player: player.stats["min"].p50, reverse=True)
    return players[:5]


def _fmt_player(player) -> str:
    stats = player.stats
    return (
        f"{player.player_name}  "
        f"{stats['min'].p50:.1f} / {stats['pts'].p50:.1f} / "
        f"{stats['reb'].p50:.1f} / {stats['ast'].p50:.1f}"
    )


def _print_compare(main: GameSummary, exp: GameSummary) -> None:
    away = main.away_abbr
    home = main.home_abbr

    def cells(summary: GameSummary) -> list[str]:
        return [
            f"{away} {100 * (1.0 - summary.home_win_prob):.1f}%   {home} {100 * summary.home_win_prob:.1f}%",
            f"{away} {summary.away_pts.p50:.1f}   {home} {summary.home_pts.p50:.1f}",
            f"{summary.margin.p50:+.1f} ({home} − {away})",
            f"{summary.total.p50:.1f}",
        ]

    labels = ["Win %", "Median score", "Spread", "Total"]
    left = cells(main)
    right = cells(exp)
    print("SIDE_BY_SIDE", flush=True)
    print(f"{'':<16} {'MAIN':<42} EXPERIMENTAL", flush=True)
    for label, a, b in zip(labels, left, right):
        print(f"{label:<16} {a:<42} {b}", flush=True)
    for abbr in (away, home):
        print(f"{abbr} top 5 median MIN / PTS / REB / AST", flush=True)
        print(f"{'MAIN':<44} EXPERIMENTAL", flush=True)
        for main_player, exp_player in zip(_top(main, abbr), _top(exp, abbr)):
            print(f"{_fmt_player(main_player):<44} {_fmt_player(exp_player)}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare main vs experimental for one game.")
    parser.add_argument("--date", required=True, help="Game date YYYY-MM-DD.")
    parser.add_argument("--away", required=True, help="Away abbreviation.")
    parser.add_argument("--home", required=True, help="Home abbreviation.")
    parser.add_argument("--runs", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--skip-guardrail",
        action="store_true",
        help="Skip the reconcile check and feature isolation.",
    )
    args = parser.parse_args(argv)

    slate = date.fromisoformat(args.date)
    away = args.away.upper()
    home = args.home.upper()
    abbrs = {away, home}

    main_settings = load_settings()
    exp_settings = load_settings(config_path=ROOT / "config_experimental.yaml")
    if main_settings.config["features"]["minutes_model"] != "naive_last10":
        raise SystemExit("config.yaml minutes_model changed; refusing to run")
    if exp_settings.config["features"]["minutes_model"] != "engine":
        raise SystemExit("experimental minutes_model is not engine")
    if exp_settings.config["context"]["play_type_defense_weight"] != 0.15:
        raise SystemExit("experimental play-type weight is not 0.15")

    print(f"refresh rosters {away} and {home}", flush=True)
    refresh_teams(main_settings, abbrs)

    print(f"injury report {slate.isoformat()}", flush=True)
    injuries = injuries_for_date(main_settings, slate, fetch_pdf=True)
    _print_injuries(injuries, abbrs)

    schedule = read_rows(main_settings, "schedule", main_settings.current_season)
    game = next(
        (
            row
            for row in schedule
            if _as_date(row["game_date"]) == slate
            and str(row["away_abbr"]) == away
            and str(row["home_abbr"]) == home
        ),
        None,
    )
    if game is None:
        raise SystemExit(f"no scheduled {away}@{home} on {slate.isoformat()}")
    game_id = str(game["game_id"])
    print(f"game {away}@{home} {game_id} seed={args.seed} runs={args.runs}", flush=True)

    if args.skip_guardrail:
        print("experimental reconcile skipped", flush=True)
    else:
        print("experimental reconcile", flush=True)
        report = _guardrail(exp_settings)
        if report.passed:
            print("experimental reconcile passed; no feature isolation", flush=True)
        else:
            print("experimental reconcile failed; isolating features", flush=True)
            caused = _isolate(main_settings, list(_FEATURES))
            print(f"GUARDRAIL_CAUSE {', '.join(caused)}", flush=True)

    print("MAIN sim", flush=True)
    main_result = run_game(
        main_settings,
        season=main_settings.current_season,
        game_id=game_id,
        runs=args.runs,
        seed=args.seed,
        injuries=injuries,
        write_json=False,
        write_history=True,
        write_typical=False,
        write_report=False,
        history_model=None,
    )
    print("EXPERIMENTAL sim", flush=True)
    exp_result = run_game(
        exp_settings,
        season=exp_settings.current_season,
        game_id=game_id,
        runs=args.runs,
        seed=args.seed,
        injuries=injuries,
        write_json=False,
        write_history=True,
        write_typical=True,
        write_report=False,
        history_model="experimental",
    )
    _print_compare(main_result.summaries[0], exp_result.summaries[0])
    print(
        f"history main_rows={main_result.history_rows} experimental_rows={exp_result.history_rows}",
        flush=True,
    )
    htmls = [path for path in exp_result.json_paths if str(path).endswith(".html")]
    if not htmls:
        print("typical-game html was not written", flush=True)
        return 1
    html = htmls[-1]
    print(f"opening {html}", flush=True)
    subprocess.run(["open", str(html)], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
