"""Judge play-probability rotations on 2025-26 and the 2024-25 holdout.

Both sides use this tree. The only switch is minutes.play_prob_rotation.
Tonight's box score is not an input. 1,000 sims, seed 1, four workers.
The difference is rotation-on minus rotation-off. Lower is better.

``explain`` lists the October players the old 11-man cutoff projected under
0.5 minutes who played 8 or more, and what the new rank gives them.
``reference`` regrades the 2026-27 finals. It is not the keep call.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pyarrow.parquet as pq

from backtest.bootstrap import paired_bootstrap
from backtest.evaluate import _minute_miss_counts, _write_game_rows, evaluate_seasons
from nba_sim.settings import load_settings
from nba_sim.storage import read_rows
from projections.blend import available_season_window, load_season_bundle
from projections.build import ProjectionCache, _preseason_mpg, build_game_projections
from projections.dunks import _epm_map
from projections.minutes import appearance_since_arrival, rotation_inputs

RUNS = 1000
SEED = 1
WORKERS = 4
SEASONS = ("2025-26", "2024-25")


def _config(base: dict, enabled: bool) -> dict:
    config = copy.deepcopy(base)
    config["minutes"]["play_prob_rotation"] = enabled
    config.setdefault("context", {})["dunks_fallback_log"] = False
    return config


def _out(season: str, enabled: bool) -> Path:
    label = season.replace("-", "_")
    side = "on" if enabled else "off"
    return ROOT / "results" / "backtest" / f"wf_{label}_rotation_{side}_1000"


def _load(path: Path) -> list[dict]:
    return pq.read_table(path).to_pylist()


def _run(settings, config: dict, season: str, out: Path) -> float:
    out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    report = evaluate_seasons(
        settings,
        [season],
        runs=RUNS,
        seed=SEED,
        workers=WORKERS,
        config_override=config,
        progress_every=100,
    )
    elapsed = time.perf_counter() - started
    payload = report.as_dict()
    payload["elapsed_seconds"] = elapsed
    payload["total_bias"] = _total_bias_from_rows(report.game_rows or [])
    (out / "metrics.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _write_game_rows(out / "games.parquet", report.game_rows or [])
    print(
        f"FINISHED {out.name} games={report.games} seconds={elapsed:.1f} "
        f"zero_played={report.projected_zero_played} "
        f"eight_dnp={report.projected_eight_dnp} "
        f"MIN {report.mae_min:.3f} PTS {report.mae_pts:.3f} "
        f"spread {report.mae_margin:.3f} total {report.mae_total:.3f} "
        f"bias {payload['total_bias']:.2f} brier {report.brier_win:.4f}",
        flush=True,
    )
    return elapsed


def _total_bias_from_rows(rows: list[dict]) -> float:
    if not rows:
        return float("nan")
    diffs = [float(row["pred_total"]) - float(row["act_total"]) for row in rows]
    return float(sum(diffs) / len(diffs))


def _sides(boot: dict) -> tuple[list[str], list[str]]:
    better: list[str] = []
    worse: list[str] = []
    for metric, row in boot.items():
        if float(row["high"]) < 0.0:
            better.append(metric)
        elif float(row["low"]) > 0.0:
            worse.append(metric)
    return better, worse


def _format(boot: dict) -> str:
    parts = []
    for metric, row in boot.items():
        parts.append(
            f"{metric}: {row['diff']:+.4f} [{row['low']:+.4f}, {row['high']:+.4f}] "
            f"{'decisive' if row['decisive'] else 'inside noise'}"
        )
    return "; ".join(parts)


def _why(case: dict) -> str:
    old_rank = case["old_rank"]
    if old_rank is None:
        reason = (
            "he was not on the projected roster. The live-roster guard had "
            "replaced a low-overlap team with last year's list, so the ranker "
            "never saw him"
        )
    elif old_rank >= 11:
        reason = (
            f"the same-team minute sort put him at rank {old_rank}, "
            "outside the 11-man cutoff"
        )
    else:
        reason = (
            f"rank {old_rank} still had a minute prior of {case['old_mean']:.1f}, "
            "which the cutoff treated as a ghost"
        )
    bits = [reason]
    if case["same_n"] == 0 and case["previous"] <= 0:
        if case["preseason_n"] > 0:
            bits.append(
                f"no regular-season minutes; preseason {case['preseason_mean']:.1f} "
                f"over {case['preseason_n']} games is the rookie signal "
                "(draft slot is not in the data)"
            )
        elif case["epm_mpg"] >= 1:
            bits.append(
                f"no regular-season minutes; EPM minutes {case['epm_mpg']:.1f} "
                "are the rookie signal (draft slot is not in the data)"
            )
        else:
            bits.append(
                "no regular-season minutes, no preseason minutes, and no draft slot "
                "in the data, so he stays at the bottom of the curve"
            )
    elif case["previous"] > 0 and case["same_n"] == 0:
        bits.append(
            f"previous-team minutes {case['previous']:.1f} are scaled to the new rank"
        )
    if case["epm_mpg"] >= 1 and case["same_n"] > 0:
        bits.append(f"EPM minutes {case['epm_mpg']:.1f}")
    if case["dnp_window"] and case["appear_rate"] < 0.5:
        bits.append(f"recent appear rate {case['appear_rate']:.2f} lowers P(plays)")
    return ". ".join(bits)


def explain() -> None:
    """The 23 October misses: old rank against the new rank, P(plays), and minutes."""
    settings = load_settings()
    off_settings = replace(settings, config=_config(settings.config, False))
    on_settings = replace(settings, config=_config(settings.config, True))
    season = "2026-27"
    schedule = [
        row
        for row in read_rows(settings, "schedule", season)
        if row.get("status") == "final"
    ]
    schedule.sort(key=lambda row: (row["game_date"], row["game_id"]))
    logs_by_game: dict[object, dict[int, dict]] = {}
    for record in read_rows(settings, "player_game_logs", season):
        logs_by_game.setdefault(record["game_id"], {})[int(record["player_id"])] = record
    seasons_back = list(settings.config["blending"]["season_weights"]["seasons_back"])
    window = available_season_window(settings, season, seasons_back)
    if season not in window:
        window = [season] + window
    bundles = [load_season_bundle(settings, label) for label in window]
    cache = ProjectionCache()
    team_date_index: dict[int, set] = {}
    for bundle in bundles:
        for rows in bundle.logs_by_player.values():
            for log_row in rows:
                team_date_index.setdefault(int(log_row["team_id"]), set()).add(log_row["game_date"])
    dunks_dir = Path(settings.data_dir) / "external" / "dunks"
    cases: list[dict] = []
    off_zero = on_zero = off_dnp = on_dnp = 0
    games = 0
    first_date = schedule[0]["game_date"] if schedule else None
    for row in schedule:
        if row["game_date"] == first_date:
            continue
        try:
            off = build_game_projections(
                off_settings,
                season=season,
                game_id=str(row["game_id"]),
                as_of=row["game_date"],
                bundles=bundles,
                cache=cache,
            )
            on = build_game_projections(
                on_settings,
                season=season,
                game_id=str(row["game_id"]),
                as_of=row["game_date"],
                bundles=bundles,
                cache=cache,
            )
        except ValueError:
            continue
        if sum(1 for p in off.players if p.home_away == "H") < 5:
            continue
        if sum(1 for p in off.players if p.home_away == "A") < 5:
            continue
        games += 1
        logs = logs_by_game.get(row["game_id"], {})
        z0, d0 = _minute_miss_counts(off, logs)
        z1, d1 = _minute_miss_counts(on, logs)
        off_zero += z0
        on_zero += z1
        off_dnp += d0
        on_dnp += d1
        off_by = {int(p.player_id): p for p in off.players}
        on_by = {int(p.player_id): p for p in on.players}
        epm = _epm_map(dunks_dir, row["game_date"]) if dunks_dir.is_dir() else {}
        for pid, log in logs.items():
            actual = float(log.get("minutes") or 0.0)
            if actual < 8.0:
                continue
            old = off_by.get(int(pid))
            old_mean = 0.0 if old is None or old.minutes.out else float(old.minutes.mean)
            if old_mean >= 0.5:
                continue
            new = on_by.get(int(pid))
            team_id = int(log["team_id"])
            same_n, _same_mean, previous = rotation_inputs(
                bundles, player_id=int(pid), team_id=team_id, as_of=row["game_date"]
            )
            preseason_index = cache.preseason_index(settings, season)
            pre_mean, pre_n = _preseason_mpg(
                preseason_index,
                player_id=int(pid),
                team_id=team_id,
                as_of=row["game_date"],
            )
            epm_row = epm.get(int(pid))
            team_abbr = str(log.get("team_abbr") or (new.team_abbr if new else ""))
            epm_mpg = 0.0
            if epm_row is not None and epm_row.team == team_abbr:
                epm_mpg = float(epm_row.mpg)
            _joined = appearance_since_arrival(
                bundles,
                player_id=int(pid),
                team_id=team_id,
                as_of=row["game_date"],
                team_dates=sorted(team_date_index.get(team_id, ())),
            )
            if new is None or new.minutes.out:
                cond = 0.0
                prob = 0.0
                new_rank = None
            else:
                cond = float(new.minutes.mean)
                prob = float(new.minutes.play_prob)
                new_rank = int(new.depth_rank)
            case = {
                "game_id": str(row["game_id"]),
                "game_date": str(row["game_date"]),
                "player_id": int(pid),
                "player_name": str(log.get("player_name") or (new.player_name if new else "")),
                "team_abbr": team_abbr,
                "actual_minutes": actual,
                "old_rank": None if old is None else int(old.depth_rank),
                "old_mean": old_mean,
                "new_rank": new_rank,
                "play_prob": prob,
                "minutes_if_plays": cond,
                "expected_minutes": cond * prob,
                "same_n": same_n,
                "previous": previous,
                "epm_mpg": epm_mpg,
                "preseason_mean": pre_mean,
                "preseason_n": pre_n,
                "appear_rate": _joined[0],
                "dnp_window": _joined[1],
            }
            case["why"] = _why(case)
            cases.append(case)
        if games % 10 == 0:
            print(f"explained {games} games, misses {len(cases)}", flush=True)
    dest = ROOT / "results" / "backtest" / "rotation_misses.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "games": games,
        "misses": len(cases),
        "off_expected_zero_played": off_zero,
        "on_expected_zero_played": on_zero,
        "off_expected_eight_dnp": off_dnp,
        "on_expected_eight_dnp": on_dnp,
        "cases": cases,
    }
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"games={games} old-definition misses={len(cases)} "
        f"expected zero {off_zero}->{on_zero} eight_dnp {off_dnp}->{on_dnp}",
        flush=True,
    )
    print(f"wrote {dest}", flush=True)




def reference() -> None:
    settings = load_settings()
    summary: dict = {}
    for enabled in (False, True):
        out = ROOT / "results" / "backtest" / f"ref_2026_27_rotation_{'on' if enabled else 'off'}_1000"
        if not (out / "metrics.json").is_file():
            print(f"START reference play_prob_rotation={enabled}", flush=True)
            _run(settings, _config(settings.config, enabled), "2026-27", out)
        metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
        summary["on" if enabled else "off"] = metrics
        print(
            f"reference {'on' if enabled else 'off'} "
            f"MIN {metrics['mae_min']:.3f} PTS {metrics['mae_pts']:.3f} "
            f"zero {metrics['projected_zero_played']} dnp {metrics.get('projected_eight_dnp')} "
            f"total {metrics['mae_total']:.3f} bias {metrics.get('total_bias')} "
            f"spread {metrics['mae_margin']:.3f} brier {metrics['brier_win']:.4f}",
            flush=True,
        )
    dest = ROOT / "results" / "backtest" / "rotation_reference.json"
    dest.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {dest}", flush=True)


def main() -> None:
    settings = load_settings()
    summary: dict = {"seasons": {}, "call": "leave"}
    for season in SEASONS:
        for enabled in (False, True):
            out = _out(season, enabled)
            if not (out / "games.parquet").is_file() or not (out / "metrics.json").is_file():
                print(f"START {season} play_prob_rotation={enabled}", flush=True)
                _run(settings, _config(settings.config, enabled), season, out)
        off_games = _load(_out(season, False) / "games.parquet")
        on_games = _load(_out(season, True) / "games.parquet")
        boot = paired_bootstrap(off_games, on_games, n_boot=10000, seed=1)
        better, worse = _sides(boot)
        off_metrics = json.loads((_out(season, False) / "metrics.json").read_text(encoding="utf-8"))
        on_metrics = json.loads((_out(season, True) / "metrics.json").read_text(encoding="utf-8"))
        summary["seasons"][season] = {
            "bootstrap": boot,
            "better": better,
            "worse": worse,
            "off": off_metrics,
            "on": on_metrics,
            "line": _format(boot),
        }
        print(f"{season} {_format(boot)}", flush=True)

    tune = summary["seasons"]["2025-26"]
    hold = summary["seasons"]["2024-25"]
    call = "leave"
    if tune["worse"] and tune["better"]:
        call = "mixed"
    elif tune["worse"]:
        call = "worse"
    elif tune["better"]:
        if hold["worse"]:
            call = "holdout contradicts"
        elif hold["better"]:
            call = "adopt"
        else:
            call = "holdout inside noise"
    elif not hold["worse"]:
        call = "noise, keep for the fringe fix"
    else:
        call = "holdout contradicts"
    summary["call"] = call
    dest = ROOT / "results" / "backtest" / "rotation_decision.json"
    dest.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"CALL {call}", flush=True)
    print(f"wrote {dest}", flush=True)
    reference()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "explain":
        explain()
    elif len(sys.argv) > 1 and sys.argv[1] == "reference":
        reference()
    else:
        main()
