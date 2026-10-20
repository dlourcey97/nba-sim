#!/usr/bin/env python3
"""Opening-night readiness checks (rosters, injuries, zero-season projections, sanity)."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.injuries import fetch_injuries_for_date
from ingest.rosters import prior_season_label, refresh_current_rosters
from ingest.source import NbaSource
from nba_sim.settings import load_settings
from nba_sim.storage import read_rows
from outputs.pipeline import injuries_for_date, run_slate
from projections.build import build_game_projections


def _print_roster_moves(settings, season: str) -> tuple[bool, list[str]]:
    """Compare current_rosters vs prior-season open stints; print movers."""
    prior = prior_season_label(season)
    if not prior:
        print("FAIL a: cannot derive prior season")
        return False, []
    current = list(read_rows(settings, "current_rosters", season))
    prior_rows = list(read_rows(settings, "team_rosters", prior))
    if not current:
        print("FAIL a: current_rosters empty — refresh first")
        return False, []
    prior_team: dict[int, tuple[str, str]] = {}
    for row in prior_rows:
        if row.get("to_date") is not None:
            continue
        pid = int(row["player_id"])
        prior_team[pid] = (
            str(row.get("team_abbr") or ""),
            str(row.get("player_name") or f"player:{pid}"),
        )
    movers: list[str] = []
    for row in sorted(current, key=lambda r: (str(r["team_abbr"]), str(r["player_name"]))):
        pid = int(row["player_id"])
        now_abbr = str(row["team_abbr"])
        name = str(row["player_name"])
        if pid not in prior_team:
            movers.append(f"  NEW     {name:28s} -> {now_abbr}  (no prior-season open stint)")
            continue
        old_abbr, _ = prior_team[pid]
        if old_abbr and old_abbr != now_abbr:
            movers.append(f"  MOVED   {name:28s} {old_abbr} -> {now_abbr}")
    # Players who left the league / not on any current roster
    current_ids = {int(r["player_id"]) for r in current}
    for pid, (old_abbr, name) in sorted(prior_team.items(), key=lambda x: x[1][1]):
        if pid not in current_ids:
            movers.append(f"  GONE    {name:28s} left {old_abbr} (not on current_rosters)")
    print(f"Roster refresh: {len(current)} players on current_rosters for {season}", flush=True)
    print(f"Players whose team changed vs {prior} (or new/gone): {len(movers)}", flush=True)
    for line in movers:
        print(line, flush=True)
    ok = len(current) >= 400  # ~15 per team * 30
    print(
        ("PASS" if ok else "FAIL") + f" a: refresh current rosters ({len(current)} players)",
        flush=True,
    )
    return ok, movers


def _print_injuries(settings, game_date: date) -> tuple[bool, list]:
    # Short timeouts: game-day PDFs often 403/404 until afternoon ET.
    try:
        rows = fetch_injuries_for_date(
            game_date,
            overrides_path=settings.repo_root / "overrides.yaml",
            delay_seconds=0.2,
            max_retries=1,
            backoff_seconds=0.5,
            timeout_seconds=12.0,
        )
    except Exception as exc:
        print(f"FAIL b: injury report fetch/parse failed: {exc}", flush=True)
        return False, []
    by_team: dict[str, list] = defaultdict(list)
    for row in rows:
        status = (row.status or "").upper()
        if status not in {"OUT", "QUESTIONABLE"}:
            continue
        abbr = row.team_abbr or "?"
        by_team[abbr].append(f"{row.player_name} ({row.status})")
    print(f"Injury report for {game_date.isoformat()}: {len(rows)} total entries", flush=True)
    if not by_team:
        print("  (no OUT/QUESTIONABLE listed — PDF may not be posted yet)", flush=True)
    for abbr in sorted(by_team):
        print(f"  {abbr}:", flush=True)
        for item in by_team[abbr]:
            print(f"    {item}", flush=True)
    if rows:
        print(f"PASS b: injury report parsed ({len(rows)} entries)", flush=True)
        return True, rows
    print(
        "PASS b: no injury PDF/entries yet (expected until game-day afternoon); "
        "overrides.yaml still applies",
        flush=True,
    )
    return True, rows


def _zero_season_projections(settings, season: str, game_date: date) -> tuple[bool, list]:
    print("building zero-season projections...", flush=True)
    logs = list(read_rows(settings, "player_game_logs", season))
    if logs:
        print(f"WARN c: {len(logs)} current-season regular-season log rows exist (expected 0)", flush=True)
    schedule = [
        row
        for row in read_rows(settings, "schedule", season)
        if row["game_date"] == game_date
    ]
    if not schedule:
        print(f"FAIL c: no schedule games on {game_date}", flush=True)
        return False, []
    injuries = injuries_for_date(settings, game_date, fetch_pdf=False)
    missing: list[str] = []
    crashed = False
    for row in sorted(schedule, key=lambda r: r["game_id"]):
        try:
            proj = build_game_projections(
                settings,
                season=season,
                game_id=str(row["game_id"]),
                injuries=injuries,
                as_of=row["game_date"],
            )
        except Exception as exc:
            print(f"FAIL c: projection crash {row['game_id']}: {exc}")
            crashed = True
            continue
        home = [p for p in proj.players if p.home_away == "H"]
        away = [p for p in proj.players if p.home_away == "A"]
        if len(home) < 8 or len(away) < 8:
            missing.append(
                f"{row['away_abbr']}@{row['home_abbr']}: home={len(home)} away={len(away)}"
            )
        # Spot-check stars exist by minutes rank
        for side, label in ((home, row["home_abbr"]), (away, row["away_abbr"])):
            if not side:
                missing.append(f"{label}: empty roster projection")
    if crashed:
        return False, schedule
    if missing:
        print("FAIL c: thin/missing rosters:")
        for line in missing:
            print(f"  {line}")
        return False, schedule
    print(
        f"PASS c: projections with 0 current-season games "
        f"({len(schedule)} games, prior seasons + current_rosters + preseason)"
    )
    return True, schedule


def _sanity(settings, season: str, game_date: date, *, runs: int, seed: int) -> bool:
    print(f"simulating slate ({runs} runs)...", flush=True)
    injuries = injuries_for_date(settings, game_date, fetch_pdf=False)
    try:
        slate = run_slate(
            settings,
            season=season,
            game_date=game_date,
            runs=runs,
            seed=seed,
            injuries=injuries,
            write_json=True,
            write_history=False,
            clear_json_first=True,
            finish=False,
        )
    except Exception as exc:
        print(f"FAIL d: slate sim crashed: {exc}")
        return False
    all_ok = True
    for summary in slate.summaries:
        print(
            f"\n=== {summary.away_abbr} @ {summary.home_abbr} ({summary.game_id}) ==="
        )
        issues: list[str] = []
        # Rebuild projection for usage check
        proj = build_game_projections(
            settings,
            season=season,
            game_id=summary.game_id,
            injuries=injuries,
            as_of=summary.game_date,
        )
        by_team: dict[str, list] = defaultdict(list)
        for player in proj.players:
            by_team[player.team_abbr].append(player)
        for abbr, plist in by_team.items():
            top_pts = sorted(
                [p for p in summary.players if p.team_abbr == abbr],
                key=lambda p: p.stats["pts"].mean,
                reverse=True,
            )[:3]
            # Usage × minutes ≈ expected touches; allow top scorers in that top-8.
            touch_rank = sorted(
                plist,
                key=lambda p: float(p.rates.usage) * max(float(p.minutes.mean), 0.0),
                reverse=True,
            )
            touch_ids = {p.player_id for p in touch_rank[:8]}
            for scorer in top_pts:
                if scorer.player_id not in touch_ids:
                    issues.append(
                        f"{abbr}: top scorer {scorer.player_name} not in top-8 usage×minutes"
                    )
            for scorer in top_pts:
                if scorer.stats["min"].mean >= 20 and scorer.stats["pts"].p10 <= 0:
                    issues.append(
                        f"{abbr}: {scorer.player_name} MIN~{scorer.stats['min'].mean:.1f} "
                        f"but PTS p10={scorer.stats['pts'].p10:.2f}"
                    )
        total_mean = summary.total.mean
        if not (200 <= total_mean <= 260):
            issues.append(f"team total mean {total_mean:.1f} outside 200–260")
        for abbr in (summary.home_abbr, summary.away_abbr):
            mins = sum(
                p.stats["min"].mean
                for p in summary.players
                if p.team_abbr == abbr
            )
            if abs(mins - 240.0) > 2.5:
                issues.append(f"{abbr} minutes sum {mins:.1f} (want ~240)")
        if issues:
            all_ok = False
            print("  SANITY ISSUES:")
            for issue in issues:
                print(f"    - {issue}")
        else:
            print("  sanity OK")
        print(
            f"  P(home)={summary.home_win_prob:.3f}  "
            f"score {summary.away_pts.mean:.1f}-{summary.home_pts.mean:.1f}  "
            f"total={summary.total.mean:.1f}"
        )
    print(("PASS" if all_ok else "FAIL") + f" d: sanity checks on {len(slate.summaries)} games")
    return all_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Opening-night readiness checks.")
    parser.add_argument("--date", default="2026-10-20", help="Slate date YYYY-MM-DD")
    parser.add_argument("--runs", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-refresh", action="store_true")
    args = parser.parse_args(argv)
    settings = load_settings()
    season = settings.current_season
    game_date = date.fromisoformat(args.date)

    if not args.skip_refresh:
        http = settings.config["http"]
        source = NbaSource(
            delay_seconds=float(http["delay_seconds"]),
            max_retries=int(http["max_retries"]),
            backoff_seconds=float(http["backoff_seconds"]),
            timeout_seconds=float(http["timeout_seconds"]),
            log=print,
            current_season=season,
        )
        print("--- refreshing current_rosters ---")
        refresh_current_rosters(settings, source=source, season=season, log=print)

    print("\n--- a. roster moves vs last season ---")
    ok_a, _ = _print_roster_moves(settings, season)

    print("\n--- b. injury report OUT/QUESTIONABLE ---")
    ok_b, _ = _print_injuries(settings, game_date)

    print("\n--- c. zero current-season projections ---")
    ok_c, _ = _zero_season_projections(settings, season, game_date)

    print("\n--- d. sanity checks ---")
    ok_d = _sanity(settings, season, game_date, runs=args.runs, seed=args.seed)

    print("\n======== SUMMARY ========")
    for label, ok in (("a", ok_a), ("b", ok_b), ("c", ok_c), ("d", ok_d)):
        print(f"{'PASS' if ok else 'FAIL'} {label}")
    return 0 if all((ok_a, ok_b, ok_c, ok_d)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
