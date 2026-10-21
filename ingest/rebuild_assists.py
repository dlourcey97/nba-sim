"""Rebuild compact assist_edges from PlayByPlayV3 for selected seasons.

Usage:
  PYTHONPATH=. python -m ingest.rebuild_assists --seasons 2024-25,2025-26
"""

from __future__ import annotations

import argparse
import time

from ingest.assists import assist_edges_from_possessions
from ingest.pbp import views_from_playbyplay_v3
from ingest.source import NbaSource, NonJsonResponse, PossessionsMissing, SourceUnavailable
from nba_sim.settings import load_settings
from nba_sim.storage import read_rows, store_rows, stored_game_ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seasons",
        required=True,
        help="Comma-separated seasons, e.g. 2024-25,2025-26",
    )
    parser.add_argument("--max-games", type=int, default=0, help="Cap games per season (0=all).")
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args(argv)
    settings = load_settings()
    seasons = [s.strip() for s in args.seasons.split(",") if s.strip()]
    http = settings.config["http"]
    source = NbaSource(
        delay_seconds=float(http["delay_seconds"]),
        max_retries=int(http["max_retries"]),
        backoff_seconds=float(http["backoff_seconds"]),
        timeout_seconds=float(http["timeout_seconds"]),
        log=print,
        current_season=settings.current_season,
    )
    for season in seasons:
        existing = stored_game_ids(settings, "assist_edges", season)
        if args.skip_existing and existing:
            print(f"{season}: already has {len(existing)} assist games; skip.", flush=True)
            continue
        schedule = [
            row
            for row in read_rows(settings, "schedule", season)
            if str(row.get("status") or "") == "final"
        ]
        schedule.sort(key=lambda r: (r["game_date"], r["game_id"]))
        if args.max_games > 0:
            schedule = schedule[: args.max_games]
        logs_by_game: dict[str, list[dict]] = {}
        for row in read_rows(settings, "player_game_logs", season):
            logs_by_game.setdefault(str(row["game_id"]), []).append(row)

        all_rows: list[dict] = []
        failures = 0
        t0 = time.time()
        for i, row in enumerate(schedule, start=1):
            game_id = str(row["game_id"])
            players = _box_players(logs_by_game.get(game_id, []))
            if len(players) < 10:
                failures += 1
                continue
            try:
                actions = source._playbyplay_v3(game_id)  # noqa: SLF001
            except (SourceUnavailable, NonJsonResponse, PossessionsMissing, Exception) as exc:
                failures += 1
                if failures <= 5 or failures % 50 == 0:
                    print(f"  fail {game_id}: {exc}", flush=True)
                continue
            views = views_from_playbyplay_v3(actions, players)
            edges = assist_edges_from_possessions(
                season=season,
                game_id=game_id,
                game_date=row["game_date"],
                possessions=views,
            )
            all_rows.extend(edges)
            if i % 25 == 0 or i == len(schedule):
                elapsed = time.time() - t0
                print(
                    f"{season}: {i}/{len(schedule)} games, "
                    f"{len(all_rows)} edges, failures {failures}, {elapsed:.0f}s",
                    flush=True,
                )
        store_rows(settings, "assist_edges", season, all_rows, allow_historical=True)
        print(f"{season}: wrote {len(all_rows)} assist edge rows.", flush=True)
    return 0


def _box_players(logs: list[dict]) -> list[dict]:
    players = []
    for row in logs:
        players.append(
            {
                "player_id": int(row["player_id"]),
                "team_id": int(row["team_id"]),
                "name": str(row.get("player_name") or ""),
                "starter": bool(row.get("started")),
            }
        )
    return players


if __name__ == "__main__":
    raise SystemExit(main())
