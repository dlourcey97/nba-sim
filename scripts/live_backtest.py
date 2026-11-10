"""Grade remaining-game re-sims on 2025-26 from halftime and from the end of Q3.

Uses play-by-play only through the checkpoint, then the stored final box.
The baseline is the pregame rate projection scaled by the fraction of the
game still left. Live command runs stay at 10,000; this grade uses fewer
runs so the full season can finish on one machine.

    PYTHONPATH=. python scripts/live_backtest.py --season 2025-26 --runs 400
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from math import erf, sqrt
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.injury_archive import load_injury_index
from nba_sim.settings import load_settings
from nba_sim.storage import read_rows
from projections.blend import available_season_window, load_season_bundle
from projections.build import ProjectionCache, build_game_projections
from sim.engine import simulate_game
from sim.live_state import state_at_period_end
from sim.resume import pregame_counting

_BOX = (
    "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/"
    "NBA/liveData/boxscore/boxscore_{game_id}.json"
)
_PBP = (
    "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/"
    "NBA/liveData/playbyplay/playbyplay_{game_id}.json"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest live re-sims from historical play-by-play.")
    parser.add_argument("--season", default="2025-26")
    parser.add_argument("--runs", type=int, default=400)
    parser.add_argument("--max-games", type=int)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)
    settings = load_settings()
    season = args.season
    schedule = [
        row
        for row in read_rows(settings, "schedule", season)
        if row.get("status") == "final"
    ]
    schedule.sort(key=lambda row: (row["game_date"], row["game_id"]))
    logs: dict[str, dict[int, dict]] = {}
    for record in read_rows(settings, "player_game_logs", season):
        logs.setdefault(str(record["game_id"]), {})[int(record["player_id"])] = record
    teams = {
        (str(row["game_id"]), int(row["team_id"])): row
        for row in read_rows(settings, "team_game_results", season)
    }
    config = settings.config
    seasons_back = list(config["blending"]["season_weights"]["seasons_back"])
    window = available_season_window(settings, season, seasons_back)
    if season not in window:
        window = [season] + window
    bundles = [load_season_bundle(settings, label) for label in window]
    injury_index = (
        load_injury_index(settings)
        if bool((config.get("context") or {}).get("injury_archive_enabled", False))
        else None
    )
    cache = ProjectionCache()
    session = requests.Session()
    buckets = {
        "halftime": _Bucket(),
        "end_q3": _Bucket(),
    }
    started = time.perf_counter()
    done = 0
    skipped = 0
    for row in schedule:
        if args.max_games is not None and done >= args.max_games:
            break
        if not any(item["game_date"] < row["game_date"] for item in schedule):
            continue
        game_id = str(row["game_id"])
        try:
            box = _get(session, _BOX.format(game_id=game_id))
            pbp = _get(session, _PBP.format(game_id=game_id))
            actions = (pbp.get("game") or {}).get("actions") or []
            if len(actions) < 200:
                skipped += 1
                continue
            injuries = []
            if injury_index is not None:
                when = row["game_date"]
                when_key = when.isoformat() if hasattr(when, "isoformat") else str(when)[:10]
                injuries = injury_index.get((when_key, f"{row['away_abbr']}@{row['home_abbr']}"), [])
            projection = build_game_projections(
                settings,
                season=season,
                game_id=game_id,
                as_of=row["game_date"],
                bundles=bundles,
                cache=cache,
                injuries=injuries,
            )
        except Exception as exc:
            skipped += 1
            print(f"skip {game_id}: {exc}", flush=True)
            continue
        final_players = logs.get(game_id, {})
        home_final = teams.get((game_id, int(projection.home_team_id)))
        away_final = teams.get((game_id, int(projection.away_team_id)))
        if home_final is None or away_final is None:
            skipped += 1
            continue
        pregame = {int(player.player_id): pregame_counting(player) for player in projection.players}
        for label, period in (("halftime", 2), ("end_q3", 3)):
            try:
                resume = state_at_period_end(box, actions, period)
            except Exception as exc:
                print(f"skip {game_id} {label}: {exc}", flush=True)
                continue
            if resume.home.score == 0 and resume.away.score == 0:
                continue
            sim = simulate_game(
                projection,
                runs=args.runs,
                seed=args.seed,
                config=settings.config,
                resume=resume,
            )
            _grade(
                buckets[label],
                projection,
                sim,
                resume,
                final_players,
                int(home_final["pts"]),
                int(away_final["pts"]),
                pregame,
            )
        done += 1
        if done % 25 == 0:
            elapsed = time.perf_counter() - started
            print(
                f"games={done} skipped={skipped} elapsed={elapsed:.0f}s "
                f"per_game={elapsed / done:.1f}s",
                flush=True,
            )
            print(_format(buckets), flush=True)
            _write(buckets)
    print(f"DONE games={done} skipped={skipped} elapsed={time.perf_counter() - started:.0f}s runs={args.runs}")
    text = _format(buckets)
    print(text)
    path = _write(buckets)
    print(f"wrote {path}")
    return 0


def _write(buckets: dict[str, _Bucket]) -> Path:
    out = ROOT / "results" / "live_backtest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({name: bucket.as_dict() for name, bucket in buckets.items()}, indent=2))
    return out


class _Bucket:
    def __init__(self) -> None:
        self.n = 0
        self.brier = 0.0
        self.base_brier = 0.0
        self.margin_abs = 0.0
        self.base_margin_abs = 0.0
        self.total_abs = 0.0
        self.base_total_abs = 0.0
        self.crps = {"pts": 0.0, "reb": 0.0, "ast": 0.0}
        self.base_mae = {"pts": 0.0, "reb": 0.0, "ast": 0.0}
        self.sim_mae = {"pts": 0.0, "reb": 0.0, "ast": 0.0}
        self.cover = {"pts": 0.0, "reb": 0.0, "ast": 0.0}
        self.players = 0

    def as_dict(self) -> dict:
        n = max(self.n, 1)
        p = max(self.players, 1)
        return {
            "games": self.n,
            "players": self.players,
            "brier": self.brier / n,
            "baseline_brier": self.base_brier / n,
            "remaining_margin_mae": self.margin_abs / n,
            "baseline_margin_mae": self.base_margin_abs / n,
            "remaining_total_mae": self.total_abs / n,
            "baseline_total_mae": self.base_total_abs / n,
            "crps": {key: value / p for key, value in self.crps.items()},
            "sim_mae": {key: value / p for key, value in self.sim_mae.items()},
            "baseline_mae": {key: value / p for key, value in self.base_mae.items()},
            "coverage_10_90": {key: value / p for key, value in self.cover.items()},
        }


def _grade(bucket, projection, sim, resume, final_players, home_final, away_final, pregame) -> None:
    start_home = float(resume.home.score)
    start_away = float(resume.away.score)
    remain_home = sim.home_pts - start_home
    remain_away = sim.away_pts - start_away
    pred_margin = float(np.mean(remain_home - remain_away))
    pred_total = float(np.mean(remain_home + remain_away))
    act_margin = (home_final - start_home) - (away_final - start_away)
    act_total = (home_final - start_home) + (away_final - start_away)
    home_win_p = float(np.mean(sim.home_pts > sim.away_pts))
    if home_final > away_final:
        actual_home = 1.0
    elif home_final < away_final:
        actual_home = 0.0
    else:
        actual_home = 0.5
    frac = max(0.0, 1.0 - resume.elapsed_fraction)
    base_home = sum(pregame[int(p.player_id)][0] for p in projection.players if p.home_away == "H") * frac
    base_away = sum(pregame[int(p.player_id)][0] for p in projection.players if p.home_away == "A") * frac
    mu = (start_home + base_home) - (start_away + base_away)
    sd = 11.5 * sqrt(max(frac, 0.05))
    base_p = _phi(mu / sd)
    bucket.n += 1
    bucket.brier += (home_win_p - actual_home) ** 2
    bucket.base_brier += (base_p - actual_home) ** 2
    bucket.margin_abs += abs(pred_margin - act_margin)
    bucket.base_margin_abs += abs((base_home - base_away) - act_margin)
    bucket.total_abs += abs(pred_total - act_total)
    bucket.base_total_abs += abs((base_home + base_away) - act_total)
    index = {int(player.player_id): i for i, player in enumerate(projection.players)}
    for player_id, final in final_players.items():
        slot = index.get(int(player_id))
        if slot is None:
            continue
        if float(final.get("minutes") or 0) < 1.0:
            continue
        prior = resume.players.get(int(player_id))
        already = (
            (float(prior.pts), float(prior.reb), float(prior.ast))
            if prior is not None
            else (0.0, 0.0, 0.0)
        )
        actuals = (
            max(0.0, float(final["pts"]) - already[0]),
            max(0.0, float(final["reb"]) - already[1]),
            max(0.0, float(final["ast"]) - already[2]),
        )
        draws = (
            sim.pts[slot] - already[0],
            sim.reb[slot] - already[1],
            sim.ast[slot] - already[2],
        )
        base = pregame.get(int(player_id), (0.0, 0.0, 0.0))
        bucket.players += 1
        for key, draw, actual, base_full in zip(("pts", "reb", "ast"), draws, actuals, base):
            bucket.crps[key] += _crps(draw, actual)
            bucket.sim_mae[key] += abs(float(np.mean(draw)) - actual)
            bucket.base_mae[key] += abs(base_full * frac - actual)
            low, high = np.percentile(draw, [10, 90])
            bucket.cover[key] += 1.0 if low <= actual <= high else 0.0


def _crps(samples: np.ndarray, actual: float) -> float:
    ordered = np.sort(np.asarray(samples, dtype=float))
    n = ordered.size
    if n == 0:
        return 0.0
    index = np.arange(1, n + 1)
    return float(np.mean(np.abs(ordered - actual)) - np.sum((2 * index - n - 1) * ordered) / (n * n))


def _phi(z: float) -> float:
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def _format(buckets: dict[str, _Bucket]) -> str:
    lines = []
    for name, bucket in buckets.items():
        if bucket.n == 0:
            lines.append(f"{name}: no games")
            continue
        item = bucket.as_dict()
        lines.append(
            f"{name} games={item['games']} brier={item['brier']:.3f} "
            f"(baseline {item['baseline_brier']:.3f}) "
            f"margin MAE={item['remaining_margin_mae']:.2f} "
            f"(baseline {item['baseline_margin_mae']:.2f}) "
            f"total MAE={item['remaining_total_mae']:.2f} "
            f"(baseline {item['baseline_total_mae']:.2f})"
        )
        lines.append(
            "  CRPS pts/reb/ast "
            f"{item['crps']['pts']:.2f} / {item['crps']['reb']:.2f} / {item['crps']['ast']:.2f}  "
            f"sim MAE {item['sim_mae']['pts']:.2f} / {item['sim_mae']['reb']:.2f} / {item['sim_mae']['ast']:.2f}  "
            f"baseline MAE {item['baseline_mae']['pts']:.2f} / {item['baseline_mae']['reb']:.2f} / {item['baseline_mae']['ast']:.2f}  "
            f"cover {item['coverage_10_90']['pts']:.1%} / {item['coverage_10_90']['reb']:.1%} / {item['coverage_10_90']['ast']:.1%}"
        )
    return "\n".join(lines)


def _get(session: requests.Session, url: str) -> dict:
    last: Exception | None = None
    for attempt in range(4):
        try:
            response = session.get(url, timeout=30, headers={"User-Agent": "nba-sim"})
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last = exc
            time.sleep(1.0 * (attempt + 1))
    assert last is not None
    raise last


if __name__ == "__main__":
    sys.exit(main())
