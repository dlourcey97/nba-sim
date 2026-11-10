"""Re-sim the rest of a live game from the current box and play-by-play.

Separate from the pregame slate. Does not write prediction history.

    python live.py --game MIA-SAC
    python live.py --game 0022600202
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from multiprocessing import get_context
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import requests

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nba_sim.errors import NbaSimError
from nba_sim.settings import load_settings
from nba_sim.storage import read_rows
from outputs.live_report import render_live_report
from outputs.pipeline import injuries_for_date
from projections.build import build_game_projections
from sim.engine import simulate_game
from sim.live_state import state_now

_BOX = (
    "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/"
    "NBA/liveData/boxscore/boxscore_{game_id}.json"
)
_PBP = (
    "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/"
    "NBA/liveData/playbyplay/playbyplay_{game_id}.json"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-sim the rest of a live NBA game.")
    parser.add_argument("--game", required=True, help="AWAY-HOME, one team (MIA or MIA-XXX), or a game id.")
    parser.add_argument("--date", help="Slate date YYYY-MM-DD. Default: today.")
    parser.add_argument("--runs", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)
    started = time.perf_counter()
    try:
        settings = load_settings()
        game_date = date.fromisoformat(args.date) if args.date else datetime.now().astimezone().date()
        game_id = _resolve_game_id(settings, settings.current_season, game_date, args.game)
        pool = ThreadPoolExecutor(max_workers=1)
        injury_job = pool.submit(injuries_for_date, settings, game_date, fetch_pdf=True)
        box, actions = _live_feed(game_id)
        status = int((box.get("game") or {}).get("gameStatus") or 0)
        if status == 1:
            pool.shutdown(wait=False, cancel_futures=True)
            print(f"{game_id} has not started. The pregame sim is run.py.")
            return 0
        if status == 3:
            pool.shutdown(wait=False, cancel_futures=True)
            game = box["game"]
            print(
                f"{game_id} is final. "
                f"{game['awayTeam'].get('teamTricode')} {game['awayTeam'].get('score')}, "
                f"{game['homeTeam'].get('teamTricode')} {game['homeTeam'].get('score')}."
            )
            return 0
        resume = state_now(box, actions)
        if resume.elapsed_fraction >= 0.995 and resume.home.score != resume.away.score:
            pool.shutdown(wait=False, cancel_futures=True)
            print(f"{game_id} is at the end of regulation.")
            return 0
        injuries = injury_job.result()
        pool.shutdown(wait=False)
        projection = build_game_projections(
            settings,
            season=settings.current_season,
            game_id=game_id,
            injuries=injuries,
            as_of=game_date,
        )
        sim = simulate_remaining(
            projection,
            runs=args.runs,
            seed=args.seed,
            config=settings.config,
            resume=resume,
        )
        print(render_live_report(projection, sim, resume, elapsed_seconds=time.perf_counter() - started))
    except (NbaSimError, requests.RequestException, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def simulate_remaining(projection, *, runs: int, seed: int, config: dict, resume):
    """10,000 remaining-game runs, split across cores. Pregame stays one process."""
    workers = min(4, os.cpu_count() or 1)
    if runs < 2000 or workers < 2:
        return simulate_game(projection, runs=runs, seed=seed, config=config, resume=resume)
    chunks = [runs // workers] * workers
    for extra in range(runs % workers):
        chunks[extra] += 1
    ctx = get_context("fork")
    queue = ctx.Queue()
    processes = [
        ctx.Process(
            target=_sim_chunk,
            args=(projection, chunk, seed + index * 100003, config, resume, queue, index),
        )
        for index, chunk in enumerate(chunks)
        if chunk > 0
    ]
    for process in processes:
        process.start()
    parts = [None] * len(processes)
    try:
        for _ in processes:
            index, result = queue.get(timeout=180)
            parts[index] = result
        for process in processes:
            process.join(timeout=30)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
    failed = [process.exitcode for process in processes if process.exitcode]
    if failed or any(part is None for part in parts):
        raise RuntimeError(f"remaining-game sim failed: {failed}")
    return _concat(parts)


def _sim_chunk(projection, runs, seed, config, resume, queue, index) -> None:
    result = simulate_game(projection, runs=runs, seed=seed, config=config, resume=resume)
    queue.put((index, result))


def _concat(parts: list) -> object:
    import numpy as np

    first = parts[0]
    runs = sum(part.runs for part in parts)

    def player(name: str):
        value = getattr(first, name)
        if value is None:
            return None
        return np.concatenate([getattr(part, name) for part in parts], axis=1)

    def runs_axis(name: str):
        value = getattr(first, name)
        if value is None:
            return None
        return np.concatenate([getattr(part, name) for part in parts], axis=0)

    return type(first)(
        game_id=first.game_id,
        runs=runs,
        seed=first.seed,
        player_ids=first.player_ids,
        player_names=first.player_names,
        team_abbrs=first.team_abbrs,
        home_away=first.home_away,
        pts=player("pts"),
        reb=player("reb"),
        ast=player("ast"),
        fg3m=player("fg3m"),
        stl=player("stl"),
        blk=player("blk"),
        tov=player("tov"),
        minutes=player("minutes"),
        home_pts=runs_axis("home_pts"),
        away_pts=runs_axis("away_pts"),
        overtime=runs_axis("overtime"),
        home_possessions=sum(part.home_possessions * part.runs for part in parts) / runs,
        away_possessions=sum(part.away_possessions * part.runs for part in parts) / runs,
        clock_remaining=runs_axis("clock_remaining"),
        home_period_pts=runs_axis("home_period_pts"),
        away_period_pts=runs_axis("away_period_pts"),
        second_pts=player("second_pts"),
        second_reb=player("second_reb"),
        second_ast=player("second_ast"),
        possession_log=None,
    )


def _live_feed(game_id: str) -> tuple[dict, list[dict]]:
    """Box score and play-by-play. A missing play-by-play still leaves the box usable."""
    session = requests.Session()
    box = _get(session, _BOX.format(game_id=game_id))
    try:
        payload = _get(session, _PBP.format(game_id=game_id))
    except requests.RequestException:
        return box, []
    actions = (payload.get("game") or {}).get("actions")
    return box, actions if isinstance(actions, list) else []


def _get(session: requests.Session, url: str) -> dict:
    response = session.get(url, timeout=30, headers={"User-Agent": "nba-sim"})
    response.raise_for_status()
    return response.json()


def _resolve_game_id(settings, season: str, game_date: date, token: str) -> str:
    token = token.strip().upper().replace("@", "-")
    schedule = [row for row in read_rows(settings, "schedule", season) if row["game_date"] == game_date]
    if token.isdigit() or token.startswith("002") or token.startswith("004"):
        for row in read_rows(settings, "schedule", season):
            if str(row["game_id"]) == token:
                return str(row["game_id"])
        raise ValueError(f"game_id {token} not found in {season}")
    if "-" not in token:
        return _one_team(schedule, token, game_date)
    away, home = token.split("-", 1)
    if away == "XXX":
        return _one_team(schedule, home, game_date)
    if home == "XXX":
        return _one_team(schedule, away, game_date)
    matches = [
        row
        for row in schedule
        if str(row["away_abbr"]).upper() == away and str(row["home_abbr"]).upper() == home
    ]
    if not matches:
        raise ValueError(f"no game {away}-{home} on {game_date.isoformat()}")
    if len(matches) > 1:
        raise ValueError(f"multiple games matched {away}-{home}")
    return str(matches[0]["game_id"])


def _one_team(schedule: list[dict], abbr: str, game_date: date) -> str:
    matches = [
        row
        for row in schedule
        if str(row["away_abbr"]).upper() == abbr or str(row["home_abbr"]).upper() == abbr
    ]
    if not matches:
        raise ValueError(f"no game for {abbr} on {game_date.isoformat()}")
    if len(matches) > 1:
        raise ValueError(f"multiple games for {abbr} on {game_date.isoformat()}")
    return str(matches[0]["game_id"])


if __name__ == "__main__":
    sys.exit(main())
