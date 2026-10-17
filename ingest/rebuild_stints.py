"""Rebuild compact lineup_stints from PlayByPlayV3 for selected seasons.

Usage:
  PYTHONPATH=. python -m ingest.rebuild_stints --seasons 2023-24,2024-25,2025-26
"""

from __future__ import annotations

import argparse
import time

from ingest.source import NbaSource, NonJsonResponse, PossessionsMissing, SourceUnavailable
from ingest.stints import stint_rows, stints_from_actions
from nba_sim.settings import load_settings
from nba_sim.storage import read_rows, store_rows, stored_game_ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seasons",
        required=True,
        help="Comma-separated seasons, e.g. 2023-24,2024-25",
    )
    parser.add_argument("--max-games", type=int, default=0, help="Cap games per season (0=all).")
    parser.add_argument("--skip-existing", action="store_true", help="Skip seasons with stints.")
    args = parser.parse_args(argv)
    settings = load_settings()
    seasons = [s.strip() for s in args.seasons.split(",") if s.strip()]
    source = NbaSource(
        delay_seconds=float(settings.config["http"]["delay_seconds"]),
        max_retries=int(settings.config["http"]["max_retries"]),
        backoff_seconds=float(settings.config["http"]["backoff_seconds"]),
        timeout_seconds=float(settings.config["http"]["timeout_seconds"]),
        log=print,
        current_season=settings.current_season,
    )
    for season in seasons:
        existing = stored_game_ids(settings, "lineup_stints", season)
        if args.skip_existing and existing:
            print(f"{season}: already has {len(existing)} stint games; skip.")
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
                actions = source._playbyplay_v3(game_id)  # noqa: SLF001 — rebuild path
            except (SourceUnavailable, NonJsonResponse, PossessionsMissing, Exception) as exc:
                failures += 1
                if failures <= 5 or failures % 50 == 0:
                    print(f"  fail {game_id}: {exc}")
                continue
            home_id = int(row["home_team_id"])
            away_id = int(row["away_team_id"])
            stints = stints_from_actions(actions, players, home_team_id=home_id)
            all_rows.extend(
                stint_rows(
                    season=season,
                    game_id=game_id,
                    game_date=row["game_date"],
                    home_team_id=home_id,
                    away_team_id=away_id,
                    stints=stints,
                )
            )
            if i % 25 == 0 or i == len(schedule):
                elapsed = time.time() - t0
                print(
                    f"{season}: {i}/{len(schedule)} games, "
                    f"{len(all_rows)} stints, failures {failures}, {elapsed:.0f}s"
                )
        store_rows(
            settings,
            "lineup_stints",
            season,
            all_rows,
            allow_historical=True,
        )
        print(f"{season}: wrote {len(all_rows)} stint rows.")
    return 0


def _box_players(logs: list[dict]) -> list[dict]:
    """Map stored logs into the player dict shape pbp/stint parsers expect."""
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
