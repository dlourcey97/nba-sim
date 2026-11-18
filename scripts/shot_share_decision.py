"""One change: box usage, shot-share calibration, and star minute protection.

Before is the current engine (play-by-play usage, no shot-share calibration,
lineup scale 1, stars scaled down with the roster). After rebases usage onto
pace × minutes, keeps a player who already projects at the star minute floor
from being cut to make the team sum to 240, and before the scored sims runs
up to three short rounds. Usage moves field goals, a free-throw scale moves
FTA, and a turnover scale moves TOV, each toward his box attempts per minute.
Team pace and shooting percentages are not touched.

Keep only when, on both seasons, star points bias, points CRPS, and the bust
rate improve, and the Brier, spread MAE, and total MAE intervals include zero.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from backtest.bootstrap import paired_bootstrap, paired_player_bootstrap
from nba_sim.settings import load_settings
from scripts.bust_decision import _better, _fmt, _inside, _ratio_boot
from scripts.fringe_decision import SEASONS, _guardrail, _load, _out, _run

SEED = 1
STAR_BITS = ("luka", "gilgeous", "giannis", "cade cunningham", "maxey")


def _config(settings, enabled: bool) -> dict:
    config = copy.deepcopy(settings.config)
    config["blending"]["align_box_usage"] = bool(enabled)
    sim = config["simulation"]
    sim["calibrate_shot_shares"] = bool(enabled)
    sim["usage_calibrate_runs"] = 250
    sim["usage_calibrate_rounds"] = 2
    sim["usage_calibrate_tol"] = 0.03
    sim["star_lineup_scale"] = 1.0
    config.setdefault("minutes", {})["protect_star_minutes"] = bool(enabled)
    config["minutes"]["star_minute_floor"] = 34.0
    config["minutes"]["star_protect_blk_max"] = 0.02
    config.setdefault("context", {})["dunks_fallback_log"] = False
    return config


def _bias(payload: dict) -> float:
    return float(payload.get("star_pred_mean") or 0.0) - float(payload.get("star_act_mean") or 0.0)


def _tier_line(rows: list[dict], prefix: str, count_key: str) -> str:
    total = sum(float(row.get(prefix) or 0.0) for row in rows)
    count = sum(float(row.get(count_key) or 0.0) for row in rows)
    if count <= 0:
        return "n/a"
    return f"{total / count:.3f} n={int(count)}"


def _cond_line(rows: list[dict]) -> str:
    draws = sum(float(row.get("cond_draws") or 0.0) for row in rows)
    wins = sum(float(row.get("cond_wins") or 0.0) for row in rows)
    actual_n = sum(float(row.get("cond_actual_n") or 0.0) for row in rows)
    actual_w = sum(float(row.get("cond_actual_wins") or 0.0) for row in rows)
    sim = wins / draws if draws else float("nan")
    act = actual_w / actual_n if actual_n else float("nan")
    return f"sim {sim:.3f} ({int(wins)}/{int(draws)}) actual {act:.3f} ({int(actual_w)}/{int(actual_n)})"


def _probe() -> None:
    from nba_sim.storage import read_rows
    from projections.blend import available_season_window, load_season_bundle
    from projections.build import ProjectionCache, build_game_projections
    from sim.engine import _target_attempts_per_minute, simulate_game

    settings = load_settings()
    season = "2025-26"
    configs = {
        "before": _config(settings, False),
        "after": _config(settings, True),
    }
    window = available_season_window(settings, season, list(settings.config["blending"]["season_weights"]["seasons_back"]))
    if season not in window:
        window = [season] + window
    bundles = [load_season_bundle(settings, label) for label in window]
    schedule = sorted(
        (row for row in read_rows(settings, "schedule", season) if row.get("status") == "final"),
        key=lambda row: (row["game_date"], row["game_id"]),
    )
    picked = [row for index, row in enumerate(schedule) if index > 400 and index % 80 == 0][:8]
    print(f"PROBE games={len(picked)}", flush=True)
    cache = {name: ProjectionCache() for name in configs}
    for row in picked:
        print(f"GAME {row['game_id']} {row['game_date']}", flush=True)
        sims = {}
        projections = {}
        for name, config in configs.items():
            local = replace(settings, config=config)
            projection = build_game_projections(
                local,
                season=season,
                game_id=str(row["game_id"]),
                as_of=row["game_date"],
                bundles=bundles,
                cache=cache[name],
            )
            projections[name] = projection
            sims[name] = simulate_game(projection, runs=400, seed=SEED, config=config)
        by_name = {name: projections["after"]}
        for player in projections["after"].players:
            folded = player.player_name.lower()
            if "garza" in folded or not any(bit in folded for bit in STAR_BITS):
                continue
            pace = (
                projections["after"].home_possessions
                if player.home_away == "H"
                else projections["after"].away_possessions
            ) / 48.0
            target = _target_attempts_per_minute(player, pace)
            before_player = next(
                (p for p in projections["before"].players if int(p.player_id) == int(player.player_id)),
                None,
            )
            before_pace = pace
            if before_player is not None:
                before_pace = (
                    projections["before"].home_possessions
                    if before_player.home_away == "H"
                    else projections["before"].away_possessions
                ) / 48.0
            before_target = (
                _target_attempts_per_minute(before_player, before_pace) if before_player is not None else target
            )
            parts = [player.player_name]
            for name, tgt in (("before", before_target), ("after", target)):
                sim = sims[name]
                ids = [int(pid) for pid in sim.player_ids]
                if int(player.player_id) not in ids:
                    parts.append(f"{name} missing")
                    continue
                index = ids.index(int(player.player_id))
                played = float(np.asarray(sim.minutes[index]).sum())
                runs = max(played, 1e-9)
                pts = float(np.asarray(sim.pts[index]).sum()) / float(sim.pts.shape[1])
                mean_min = played / float(sim.pts.shape[1])
                fga = float(np.asarray(sim.fga[index]).sum()) / runs
                fta = float(np.asarray(sim.fta[index]).sum()) / runs
                tov = float(np.asarray(sim.tov[index]).sum()) / runs
                parts.append(
                    f"{name} min {mean_min:.1f} pts {pts:.1f} "
                    f"fga {fga:.3f}/{tgt[0]:.3f} fta {fta:.3f}/{tgt[1]:.3f} "
                    f"tov {tov:.3f}/{tgt[2]:.3f}"
                )
            print("  " + " | ".join(parts), flush=True)
        del by_name
    print("PROBE DONE", flush=True)


def main() -> None:
    if "--probe" in sys.argv:
        _probe()
        return
    settings = load_settings()
    before = _config(settings, False)
    after = _config(settings, True)
    print("GUARDRAIL after", flush=True)
    _guardrail(settings, after)
    player: dict[str, dict] = {}
    game: dict[str, dict] = {}
    bust: dict[str, dict] = {}
    bias: dict[str, tuple[float, float]] = {}
    for season in SEASONS:
        base_dir = _out(season, "bust_base")
        var_dir = _out(season, "shot_share")
        if not (base_dir / "metrics.json").exists():
            _run(replace(settings, config=before), before, season, base_dir)
        else:
            print(f"SKIP {base_dir.name}", flush=True)
        _run(replace(settings, config=after), after, season, var_dir)
        left = _load(base_dir / "games.parquet")
        right = _load(var_dir / "games.parquet")
        player[season] = paired_player_bootstrap(left, right, n_boot=2000, seed=SEED)
        game[season] = paired_bootstrap(left, right, n_boot=2000, seed=SEED)
        bust[season] = _ratio_boot(left, right, "star_bust", "star_bust_draws")
        base_metrics = json.loads((base_dir / "metrics.json").read_text(encoding="utf-8"))
        var_metrics = json.loads((var_dir / "metrics.json").read_text(encoding="utf-8"))
        bias[season] = (_bias(base_metrics), _bias(var_metrics))
        print(f"PLAYER {season} variant-minus-base {_fmt(player[season])}", flush=True)
        print(f"BUST {season} variant-minus-base {_fmt({'bust': bust[season]})}", flush=True)
        print(
            f"BIAS {season} before {bias[season][0]:+.2f} after {bias[season][1]:+.2f} "
            f"star_pts {base_metrics.get('star_pred_mean'):.2f}->{var_metrics.get('star_pred_mean'):.2f} "
            f"actual {var_metrics.get('star_act_mean'):.2f}",
            flush=True,
        )
        print(f"GAME {season} variant-minus-base {_fmt(game[season])}", flush=True)
        print(
            f"TIER {season} top {_tier_line(right, 'crps_top', 'crps_top_n')} "
            f"starter {_tier_line(right, 'crps_start', 'crps_start_n')} "
            f"bench {_tier_line(right, 'crps_bench', 'crps_bench_n')}",
            flush=True,
        )
        print(f"COND {season} top scorer under 20 {_cond_line(right)}", flush=True)
        print(f"TOP MEAN {season} pred/act {_tier_line(right, 'pred_top', 'crps_top_n')} / {_tier_line(right, 'act_top', 'crps_top_n')}", flush=True)
        (var_dir / "paired.json").write_text(
            json.dumps(
                {
                    "player": player[season],
                    "bust": bust[season],
                    "game": game[season],
                    "bias_before": bias[season][0],
                    "bias_after": bias[season][1],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        bias_ok = abs(bias[season][1]) < abs(bias[season][0]) - 0.05
        season_ok = (
            bias_ok
            and _better(player[season]["crps_pts"])
            and _better(bust[season])
            and _inside(game[season]["brier"])
            and _inside(game[season]["mae_margin"])
            and _inside(game[season]["mae_total"])
        )
        if not season_ok:
            print(f"CALL shot_share REVERT after {season} bias_ok={bias_ok}", flush=True)
            print("SHOT SHARE DECISION DONE", flush=True)
            return
    print("CALL shot_share KEEP", flush=True)
    print("SHOT SHARE DECISION DONE", flush=True)


if __name__ == "__main__":
    main()
