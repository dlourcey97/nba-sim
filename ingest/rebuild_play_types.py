"""Rebuild play_types from SynergyPlayTypes for selected seasons.

Usage:
  PYTHONPATH=. python -m ingest.rebuild_play_types --seasons 2023-24,2024-25,2025-26,2026-27
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.play_types import refresh_play_types
from nba_sim.settings import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seasons",
        help="Comma-separated seasons. Default: 2023-24 through current.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore the once-per-day freshness skip for the current season.",
    )
    args = parser.parse_args(argv)
    settings = load_settings()
    seasons = None
    if args.seasons:
        seasons = [s.strip() for s in args.seasons.split(",") if s.strip()]
    status = refresh_play_types(
        settings, seasons=seasons, log=print, force=bool(args.force)
    )
    print(
        f"done fetched={status.fetched} skipped_fresh={status.skipped_fresh} "
        f"written={list(status.seasons_written)} warnings={len(status.warnings)}"
    )
    return 0 if not status.warnings or status.fetched else 1


if __name__ == "__main__":
    raise SystemExit(main())
