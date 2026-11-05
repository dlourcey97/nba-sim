"""Rebuild defender_impact from LeagueSeasonMatchups for selected seasons.

Usage:
  PYTHONPATH=. python -m ingest.rebuild_matchups --seasons 2023-24,2024-25
"""

from __future__ import annotations

import argparse
import time

from ingest.matchups import (
    buckets_from_logs,
    defender_impact_from_league_matchups,
    matchup_shares_from_league_matchups,
)
from ingest.rosters import prior_season_label
from nba_sim.settings import load_settings
from nba_sim.storage import read_rows, store_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", required=True, help="Comma-separated seasons.")
    args = parser.parse_args(argv)
    settings = load_settings()
    seasons = [s.strip() for s in args.seasons.split(",") if s.strip()]
    delay = float(settings.config["http"]["delay_seconds"])
    for season in seasons:
        print(f"Fetching LeagueSeasonMatchups for {season}...", flush=True)
        t0 = time.time()
        rows = _fetch_league_matchups(season)
        print(f"  raw pairs {len(rows)} in {time.time()-t0:.1f}s", flush=True)
        compact = defender_impact_from_league_matchups(season, rows)
        store_rows(settings, "defender_impact", season, compact, allow_historical=True)
        print(f"  wrote {len(compact)} defender_impact rows.", flush=True)
        label = prior_season_label(season)
        logs = read_rows(settings, "player_game_logs", label) if label else []
        shares = matchup_shares_from_league_matchups(
            season, rows, buckets_by_offense_id=buckets_from_logs(logs)
        )
        store_rows(settings, "matchup_shares", season, shares, allow_historical=True)
        print(f"  wrote {len(shares)} matchup_shares rows.", flush=True)
        time.sleep(delay)
    return 0


def _fetch_league_matchups(season: str) -> list[dict]:
    from nba_api.stats.endpoints import LeagueSeasonMatchups

    ep = LeagueSeasonMatchups(
        league_id="00",
        season=season,
        season_type_playoffs="Regular Season",
        per_mode_simple="Totals",
    )
    frames = ep.get_data_frames()
    if not frames:
        return []
    return frames[0].to_dict("records")


if __name__ == "__main__":
    raise SystemExit(main())
