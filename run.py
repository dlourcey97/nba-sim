"""CLI for simulating a single game or a full slate date."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nba_sim.errors import NbaSimError
from nba_sim.settings import load_settings
from nba_sim.storage import finish_run, read_rows
from outputs.pipeline import injuries_for_date, run_slate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulate NBA games.")
    parser.add_argument("--date", required=True, help="Game date YYYY-MM-DD.")
    parser.add_argument(
        "--game",
        help="Matchup like BOS-NYK (away-home) or a game_id.",
    )
    parser.add_argument("--all", action="store_true", help="Simulate every game on --date.")
    parser.add_argument("--season", help="Season label. Default: season.current.")
    parser.add_argument("--runs", type=int, help="Override simulation.runs.")
    parser.add_argument("--seed", type=int, help="Override simulation.seed.")
    parser.add_argument("--skip-injury-pdf", action="store_true")
    parser.add_argument(
        "--threshold",
        action="append",
        default=[],
        help="Stat threshold like pts=20. Repeatable.",
    )
    args = parser.parse_args(argv)
    if bool(args.game) == bool(args.all):
        parser.error("Pass exactly one of --game or --all.")
    try:
        settings = load_settings()
        season = args.season or settings.current_season
        game_date = date.fromisoformat(args.date)
        thresholds = [_parse_threshold(item) for item in args.threshold]
        injuries = injuries_for_date(
            settings,
            game_date,
            fetch_pdf=not args.skip_injury_pdf,
        )
        game_ids = None
        if args.game:
            game_ids = [_resolve_game_id(settings, season, game_date, args.game)]
        result = run_slate(
            settings,
            season=season,
            game_ids=game_ids,
            game_date=game_date,
            runs=args.runs,
            seed=args.seed,
            injuries=injuries,
            thresholds=thresholds,
            write_json=True,
            write_history=True,
            allow_historical=season != settings.current_season,
            clear_json_first=bool(args.all),
            finish=True,
        )
        for summary in result.summaries:
            print(
                f"{summary.away_abbr}@{summary.home_abbr} "
                f"home_win={summary.home_win_prob:.3f} "
                f"home={summary.home_pts.mean:.1f} away={summary.away_pts.mean:.1f} "
                f"ot={summary.overtime_prob:.3f} runs={summary.runs}"
            )
        for path in result.json_paths:
            print(f"wrote {path}")
    except NbaSimError as exc:
        print(exc, file=sys.stderr)
        return 1
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def _parse_threshold(value: str) -> tuple[str, float]:
    if "=" not in value:
        raise SystemExit(f"threshold must look like pts=20, got {value!r}")
    name, raw = value.split("=", 1)
    return name.strip().lower(), float(raw)


def _resolve_game_id(settings, season: str, game_date: date, token: str) -> str:
    token = token.strip().upper()
    schedule = [
        row
        for row in read_rows(settings, "schedule", season)
        if row["game_date"] == game_date
    ]
    if token.isdigit() or token.startswith("002") or token.startswith("004"):
        for row in schedule:
            if str(row["game_id"]) == token:
                return str(row["game_id"])
        # Allow direct id even if date filter missed.
        for row in read_rows(settings, "schedule", season):
            if str(row["game_id"]) == token:
                return str(row["game_id"])
        raise ValueError(f"game_id {token} not found in {season} schedule")
    # away-home
    if "-" not in token:
        raise ValueError(f"game must be AWAY-HOME or a game_id, got {token}")
    away, home = token.split("-", 1)
    matches = [
        row
        for row in schedule
        if str(row["away_abbr"]).upper() == away and str(row["home_abbr"]).upper() == home
    ]
    if not matches:
        raise ValueError(f"no game {away}-{home} on {game_date.isoformat()} in {season}")
    if len(matches) > 1:
        raise ValueError(f"multiple games matched {away}-{home} on {game_date.isoformat()}")
    return str(matches[0]["game_id"])


if __name__ == "__main__":
    sys.exit(main())
