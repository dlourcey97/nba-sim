"""STEP 2 — Apples-to-apples bakeoff with reconciliation.

Reuses the full-season 1000-run MAE table from minutes_bakeoff when present,
and runs a walk-forward reconcile pass for each variant (league totals +
starter shares).

Variants:
  a. v1.0-opening-night  — requires --v1-root worktree (or skip)
  b. current main        — config as checked in
  c. main Step F off     — engine minutes, stint_rotations_step_f=false
  d. naive_last10        — current code, minutes_model=naive_last10

Usage:
  PYTHONPATH=. .venv/bin/python scripts/stabilize_bakeoff.py \\
    --runs 200 --max-games 0 --seed 1 \\
    --out-dir results/backtest/stabilize_step2
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.reconcile import format_report, run_walkforward_reconcile
from nba_sim.settings import load_settings
from nba_sim.storage import finish_run

# minutes_bakeoff helpers (scripts/ is not a package).
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "minutes_bakeoff", ROOT / "scripts" / "minutes_bakeoff.py"
)
_mb = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mb)
_apply_flags = _mb._apply_flags
evaluate = _mb.evaluate


def _load_prior_mae(bakeoff_dir: Path) -> dict:
    path = bakeoff_dir / "comparison.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _run_variant(
    *,
    label: str,
    settings,
    config: dict,
    runs: int,
    seed: int,
    max_games: int | None,
    out_dir: Path,
    do_mae: bool,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload: dict = {"label": label}
    if do_mae:
        print(f"=== MAE {label} runs={runs} ===", flush=True)
        mae = evaluate(
            settings,
            ["2025-26"],
            runs=runs,
            seed=seed,
            max_games=max_games,
            config=config,
        )
        payload["mae"] = mae
        (out_dir / "metrics.json").write_text(
            json.dumps(mae, indent=2) + "\n", encoding="utf-8"
        )
    print(f"=== Reconcile {label} ===", flush=True)
    # Reconcile uses fewer runs when MAE already burned budget; means stabilize faster.
    rec_runs = min(runs, 200)
    report = run_walkforward_reconcile(
        settings,
        season="2025-26",
        runs=rec_runs,
        seed=seed,
        max_games=max_games,
        config=config,
        threshold_pct=3.0,
    )
    payload["reconcile"] = report.to_dict()
    (out_dir / "reconcile.md").write_text(format_report(report), encoding="utf-8")
    (out_dir / "reconcile.json").write_text(
        json.dumps(report.to_dict(), indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(
        f"  {label}: REB delta={report.team_delta_pct.get('reb', 0):+.1f}% "
        f"starter_reb={report.role_delta_pct.get('reb', 0):+.1f}% "
        f"pass={report.passed}",
        flush=True,
    )
    return payload


def _run_v1_worktree(v1_root: Path, out_dir: Path, runs: int, seed: int, max_games: int) -> dict:
    """Run reconcile inside a v1.0 worktree by invoking its Python with copied harness."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # Copy reconcile harness into worktree temporarily.
    dest = v1_root / "backtest" / "reconcile.py"
    src = ROOT / "backtest" / "reconcile.py"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    diag = v1_root / "scripts" / "reconcile_diagnosis.py"
    diag.parent.mkdir(parents=True, exist_ok=True)
    diag.write_text(
        (ROOT / "scripts" / "reconcile_diagnosis.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    cmd = [
        str(ROOT / ".venv" / "bin" / "python"),
        "scripts/reconcile_diagnosis.py",
        "--seasons",
        "2025-26",
        "--runs",
        str(min(runs, 200)),
        "--seed",
        str(seed),
        "--max-games",
        str(max_games if max_games > 0 else 0),
        "--out-dir",
        str(out_dir),
    ]
    print(f"=== v1.0 worktree reconcile at {v1_root} ===", flush=True)
    env = {**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": str(v1_root)}
    # max-games 0 means all — reconcile_diagnosis uses 0 as all only if we pass high; fix:
    if max_games <= 0:
        cmd[cmd.index("--max-games") + 1] = "0"
    proc = subprocess.run(cmd, cwd=str(v1_root), env=env, check=False)
    rec_path = out_dir / "reconcile.json"
    payload: dict = {"label": "v1_opening_night", "returncode": proc.returncode}
    if rec_path.exists():
        payload["reconcile"] = json.loads(rec_path.read_text(encoding="utf-8"))
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=200)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-games", type=int, default=250, help="0 = all games")
    parser.add_argument("--out-dir", default="results/backtest/stabilize_step2")
    parser.add_argument(
        "--reuse-mae",
        action="store_true",
        help="Reuse results/backtest/minutes_bakeoff/comparison.json for MAE",
    )
    parser.add_argument(
        "--v1-root",
        default="",
        help="Path to git worktree at tag v1.0-opening-night",
    )
    parser.add_argument(
        "--skip-full-mae",
        action="store_true",
        help="Only run reconcile (use with --reuse-mae)",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    max_games = args.max_games if args.max_games > 0 else None
    prior_mae = _load_prior_mae(Path("results/backtest/minutes_bakeoff")) if args.reuse_mae else {}

    results: dict[str, dict] = {}

    # (b) current main
    results["main"] = _run_variant(
        label="main",
        settings=settings,
        config=deepcopy(settings.config),
        runs=args.runs,
        seed=args.seed,
        max_games=max_games,
        out_dir=out_root / "main",
        do_mae=not args.skip_full_mae and not args.reuse_mae,
    )
    if args.reuse_mae and "main_naive" in prior_mae:
        # Current default minutes_model is naive_last10.
        results["main"]["mae"] = prior_mae["main_naive"]

    # (c) Step F off + engine minutes
    cfg_f_off = _apply_flags(
        settings.config, step_f=False, minutes_model="engine", naive_blend=0.5
    )
    results["main_step_f_off"] = _run_variant(
        label="main_step_f_off",
        settings=settings,
        config=cfg_f_off,
        runs=args.runs,
        seed=args.seed,
        max_games=max_games,
        out_dir=out_root / "main_step_f_off",
        do_mae=not args.skip_full_mae and not args.reuse_mae,
    )
    if args.reuse_mae and "main_step_f_off" in prior_mae:
        results["main_step_f_off"]["mae"] = prior_mae["main_step_f_off"]

    # Also report Step F on engine for continuity with prior bakeoff
    cfg_f_on = _apply_flags(
        settings.config, step_f=True, minutes_model="engine", naive_blend=0.5
    )
    results["main_step_f_on"] = _run_variant(
        label="main_step_f_on",
        settings=settings,
        config=cfg_f_on,
        runs=args.runs,
        seed=args.seed,
        max_games=max_games,
        out_dir=out_root / "main_step_f_on",
        do_mae=not args.skip_full_mae and not args.reuse_mae,
    )
    if args.reuse_mae and "main_step_f_on" in prior_mae:
        results["main_step_f_on"]["mae"] = prior_mae["main_step_f_on"]

    # (d) explicit naive_last10
    cfg_naive = _apply_flags(
        settings.config, step_f=True, minutes_model="naive_last10", naive_blend=0.5
    )
    results["main_naive"] = _run_variant(
        label="main_naive",
        settings=settings,
        config=cfg_naive,
        runs=args.runs,
        seed=args.seed,
        max_games=max_games,
        out_dir=out_root / "main_naive",
        do_mae=not args.skip_full_mae and not args.reuse_mae,
    )
    if args.reuse_mae and "main_naive" in prior_mae:
        results["main_naive"]["mae"] = prior_mae["main_naive"]

    # (a) v1.0
    if args.v1_root:
        v1_payload = _run_v1_worktree(
            Path(args.v1_root), out_root / "v1_opening_night", args.runs, args.seed, args.max_games
        )
        if args.reuse_mae and "v1_opening_night" in prior_mae:
            v1_payload["mae"] = prior_mae["v1_opening_night"]
        results["v1_opening_night"] = v1_payload
    elif args.reuse_mae and "v1_opening_night" in prior_mae:
        results["v1_opening_night"] = {
            "label": "v1_opening_night",
            "mae": prior_mae["v1_opening_night"],
            "reconcile": None,
            "note": "MAE from prior bakeoff; reconcile skipped (no --v1-root)",
        }

    # Summary table
    lines = [
        "# Stabilize Step 2 — bakeoff + reconcile",
        "",
        "MAE from full-season 1000-run bakeoff (seed 1) when --reuse-mae; "
        "reconcile from this run.",
        "",
        "| Version | MIN MAE | starters | bench | PTS | REB | AST | 10-90 | Brier | margin | total | REB Δ | starter REB Δ |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    order = [
        "v1_opening_night",
        "main_step_f_off",
        "main_step_f_on",
        "main",
        "main_naive",
    ]
    for key in order:
        if key not in results:
            continue
        row = results[key]
        mae = row.get("mae") or {}
        rec = row.get("reconcile") or {}
        reb_d = (rec.get("team_delta_pct") or {}).get("reb")
        sreb_d = (rec.get("role_delta_pct") or {}).get("reb")

        def fmt(v, nd=3):
            if v is None:
                return "—"
            return f"{float(v):.{nd}f}"

        lines.append(
            f"| {key} | {fmt(mae.get('mae_min'))} | {fmt(mae.get('mae_min_starters'))} | "
            f"{fmt(mae.get('mae_min_bench'))} | {fmt(mae.get('mae_pts'))} | "
            f"{fmt(mae.get('mae_reb'))} | {fmt(mae.get('mae_ast'))} | "
            f"{fmt(mae.get('coverage_10_90'))} | {fmt(mae.get('brier_win'))} | "
            f"{fmt(mae.get('mae_margin'), 2)} | {fmt(mae.get('mae_total'), 2)} | "
            f"{fmt(reb_d, 1)}% | {fmt(sreb_d, 1)}% |"
        )
    summary = "\n".join(lines) + "\n"
    (out_root / "comparison.md").write_text(summary, encoding="utf-8")
    (out_root / "comparison.json").write_text(
        json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(summary, flush=True)
    finish_run(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
