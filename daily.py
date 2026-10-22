"""Nightly pipeline: ingest -> injuries -> projections -> sims -> outputs -> cleanup.

Run manually each night. Logs to --log-file when provided (must be outside the repo).
Does not store raw API responses or individual simulation runs.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.pipeline import run_backfill
from ingest.rosters import refresh_current_rosters
from ingest.source import NbaSource
from nba_sim.errors import NbaSimError
from nba_sim.settings import assert_outside_repo, load_settings
from nba_sim.storage import finish_run
from outputs.pipeline import injuries_for_date, run_slate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nightly NBA sim pipeline.")
    parser.add_argument("--date", help="Slate date YYYY-MM-DD. Default: today UTC.")
    parser.add_argument("--runs", type=int, help="Override simulation.runs from config.yaml.")
    parser.add_argument("--seed", type=int, help="Override simulation.seed.")
    parser.add_argument("--skip-ingest", action="store_true", help="Skip the incremental ingest step.")
    parser.add_argument("--skip-injury-pdf", action="store_true", help="Use overrides.yaml only.")
    parser.add_argument(
        "--log-file",
        help="Absolute path outside the repo. Lines are also printed.",
    )
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        log = _logger(args.log_file, settings.repo_root)
        slate_date = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
        season = settings.current_season
        log(f"daily start season={season} date={slate_date.isoformat()}")

        if not args.skip_ingest:
            log("ingest current season")
            ingest = run_backfill(
                settings,
                [season],
                season_types=["Regular Season", "Playoffs", "PlayIn"],
                log=log,
            )
            log(
                f"ingest done stored={ingest.stored_games} skipped={ingest.skipped_games} "
                f"failed={len(ingest.failed_games)} missing_pbp={len(ingest.possessions_missing)}"
            )

        http = settings.config["http"]
        source = NbaSource(
            delay_seconds=float(http["delay_seconds"]),
            max_retries=int(http["max_retries"]),
            backoff_seconds=float(http["backoff_seconds"]),
            timeout_seconds=float(http["timeout_seconds"]),
            log=log,
            current_season=season,
        )
        log("refresh current_rosters from CommonTeamRoster")
        refresh_current_rosters(settings, source=source, season=season, log=log)

        injuries = injuries_for_date(
            settings,
            slate_date,
            fetch_pdf=not args.skip_injury_pdf,
        )
        log(f"injuries={len(injuries)}")
        overrides = [e for e in injuries if e.source == "override"]
        if overrides:
            log("overrides applied:")
            for entry in overrides:
                cap = f" cap={entry.minutes_cap}" if entry.minutes_cap is not None else ""
                log(
                    f"  {entry.team_abbr} {entry.player_name}: {entry.status}{cap} — {entry.reason}"
                )

        report_notes = [
            "Official NBA injury PDF (newest available) merged with overrides.yaml.",
            "OUT and Doubtful players removed; minutes/usage redistributed via absence model.",
        ]
        report_assumptions = [
            f"{e.player_name} ({e.team_abbr}): {e.reason}"
            for e in overrides
            if "assume" in (e.reason or "").lower()
            or e.minutes_cap is not None
            or "late scratch" in (e.reason or "").lower()
        ]
        for entry in overrides:
            if entry.minutes_cap is not None:
                report_assumptions.append(
                    f"{entry.player_name} ({entry.team_abbr}) minutes_cap={entry.minutes_cap}"
                )
        # Dedupe while preserving order.
        report_assumptions = list(dict.fromkeys(report_assumptions))

        slate = run_slate(
            settings,
            season=season,
            game_date=slate_date,
            runs=args.runs,
            seed=args.seed,
            injuries=injuries,
            write_json=True,
            write_history=True,
            clear_json_first=True,
            finish=False,
            write_report=True,
            report_notes=report_notes
            + [
                f"{e.team_abbr} {e.player_name} → {e.status}: {e.reason}"
                for e in overrides
            ],
            report_assumptions=report_assumptions
            or ["No questionable overrides beyond the official report."],
        )
        log(
            f"simulated games={len(slate.summaries)} json={len(slate.json_paths)} "
            f"history_rows={slate.history_rows} actuals_rows={slate.actuals_rows} "
            f"confident_picks={len(slate.confident_picks)} report={slate.report_path}"
        )
        from outputs.grade import refresh_season_scorecard

        scorecard = refresh_season_scorecard(settings, season=season)
        if scorecard is not None:
            log(f"season_scorecard={scorecard}")
        finish_run(settings)
        log("daily done")
    except NbaSimError as exc:
        print(exc, file=sys.stderr)
        return 1
    except ValueError as exc:
        # No games on the slate is a soft failure for nights without NBA games.
        print(exc, file=sys.stderr)
        try:
            finish_run(load_settings())
        except Exception:
            pass
        return 1
    return 0


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
