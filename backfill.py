"""One-time historical pull into the compact tables.

Games already present in both player_game_logs and player_game_rates are skipped,
so stopping and rerunning this command continues where it left off. A game
whose box score was stored without possessions is retried on the next run.
A season is marked complete only after a full run with no date filter, no
--max-games limit, no failed games, and no games missing possessions.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.parse import parse_seasons
from ingest.pipeline import run_backfill
from nba_sim.errors import NbaSimError
from nba_sim.settings import assert_outside_repo, load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill compact NBA tables.")
    parser.add_argument(
        "--seasons",
        help="One season (2024-25) or a start-year span (2015-2025).",
    )
    parser.add_argument("--season", help="One season label, such as 2024-25.")
    parser.add_argument("--start-date", help="First game date, YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Last game date, YYYY-MM-DD.")
    parser.add_argument("--max-games", type=int, help="Stop after this many final games.")
    parser.add_argument(
        "--season-types",
        default="Regular Season,Playoffs,PlayIn",
        help="Comma-separated season types.",
    )
    parser.add_argument(
        "--log-file",
        help="Absolute path outside the repo. Lines are also printed.",
    )
    args = parser.parse_args(argv)
    if bool(args.seasons) == bool(args.season):
        parser.error("Pass exactly one of --seasons or --season.")
    if args.max_games is not None and args.max_games < 1:
        parser.error("--max-games must be at least 1.")
    try:
        seasons = parse_seasons(args.seasons or args.season)
        start = _parse_date(args.start_date, "--start-date")
        end = _parse_date(args.end_date, "--end-date")
        if start is not None and end is not None and end < start:
            parser.error("--end-date is before --start-date.")
        settings = load_settings()
        log = _logger(args.log_file, settings.repo_root)
        result = run_backfill(
            settings,
            seasons,
            season_types=_season_types(args.season_types),
            start_date=start,
            end_date=end,
            max_games=args.max_games,
            log=log,
        )
    except NbaSimError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 1 if result.failed_games or result.possessions_missing else 0


def _parse_date(value: str | None, flag: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"{flag} must be YYYY-MM-DD.") from exc


def _season_types(value: str) -> list[str]:
    types = [part.strip() for part in value.split(",") if part.strip()]
    allowed = {"Regular Season", "Playoffs", "PlayIn"}
    unknown = [item for item in types if item not in allowed]
    if not types or unknown:
        raise SystemExit(
            "season types must be Regular Season, Playoffs, and/or PlayIn. "
            f"Unknown: {', '.join(unknown) or '(none)'}."
        )
    return types


def _logger(path: str | None, repo_root: Path):
    if not path:
        return print
    target = Path(path)
    if not target.is_absolute():
        raise SystemExit("--log-file must be an absolute path outside the repository.")
    assert_outside_repo(target.parent, repo_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = target.open("a", encoding="utf-8")

    def log(message: str) -> None:
        print(message)
        handle.write(message + "\n")
        handle.flush()

    return log


if __name__ == "__main__":
    sys.exit(main())
