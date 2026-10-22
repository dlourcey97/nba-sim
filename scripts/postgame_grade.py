"""Grade completed nights and refresh results/season_scorecard.md.

Usage:
  PYTHONPATH=. python scripts/postgame_grade.py --dates 2026-10-20,2026-10-21
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nba_sim.settings import load_settings
from nba_sim.storage import finish_run, print_storage_report, collect_storage_report
from outputs.grade import grade_night, refresh_season_scorecard
from outputs.history import fill_actuals_for_season


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dates",
        help="Comma-separated slate dates YYYY-MM-DD. Default: all dates with actuals.",
    )
    parser.add_argument(
        "--slate-report",
        default=str(ROOT / "results" / "latest" / "slate_report.md"),
        help="Path to slate_report.md for confident-pick grading (latest night).",
    )
    parser.add_argument(
        "--skip-fill",
        action="store_true",
        help="Skip fill_actuals_for_season.",
    )
    args = parser.parse_args(argv)
    settings = load_settings()
    season = settings.current_season

    if not args.skip_fill:
        n = fill_actuals_for_season(settings, season)
        print(f"filled actuals rows={n}")

    if args.dates:
        from outputs.grade import (
            parse_confident_picks_from_slate_report,
            write_season_scorecard,
        )

        dates = [d.strip() for d in args.dates.split(",") if d.strip()]
        slate_path = Path(args.slate_report)
        slate_picks = parse_confident_picks_from_slate_report(slate_path)
        slate_date = None
        if slate_path.exists():
            text = slate_path.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("# NBA Sim Slate Report — "):
                    slate_date = line.split("—", 1)[1].strip()
                    break
        notes = []
        nights = []
        for d in dates:
            picks = slate_picks if slate_date == d else []
            if d == "2026-10-20" and not picks:
                notes.append(
                    "2026-10-20: no Top confident picks were produced that night "
                    "(feature landed with the 2026-10-21 slate)."
                )
            night = grade_night(settings, season, d, picks=picks or None)
            nights.append(night)
            s = night.summary()
            print(
                f"{d}: games={s['games_graded']} winner="
                f"{None if s['winner_accuracy'] is None else round(100 * s['winner_accuracy'], 1)}% "
                f"spread_mae={s['spread_mae']} total_mae={s['total_mae']} "
                f"min_mae={s['player_min_mae']} pts_mae={s['player_pts_mae']} "
                f"cov={s['coverage_10_90']} picks="
                f"{s['top_picks_hits']}/{s['top_picks_graded']}"
            )
        path = write_season_scorecard(
            settings.repo_root, season=season, nights=nights, notes=notes
        )
    else:
        path = refresh_season_scorecard(
            settings, season=season, slate_report=Path(args.slate_report)
        )
    print(f"scorecard={path}")
    report = collect_storage_report(settings)
    print_storage_report(report)
    finish_run(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
