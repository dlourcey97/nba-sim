"""STEP 1 — Reconciliation diagnosis for league totals and role shares.

Usage:
  PYTHONPATH=. .venv/bin/python scripts/reconcile_diagnosis.py \\
    --seasons 2025-26 --runs 200 --max-games 250 --seed 1 \\
    --out-dir results/backtest/reconcile_step1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.reconcile import (
    actual_league_team_averages,
    actual_starter_shares,
    format_report,
    run_walkforward_reconcile,
)
from ingest.parse import parse_seasons
from nba_sim.settings import load_settings
from nba_sim.storage import finish_run


def _slate_center_rebounds(latest_dir: Path) -> list[dict]:
    rows = []
    if not latest_dir.is_dir():
        return rows
    for path in sorted(latest_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for player in data.get("players") or []:
            stats = player.get("stats") or {}
            reb = stats.get("reb") or {}
            mean_reb = float(reb.get("mean") or 0.0)
            if mean_reb < 10:
                continue
            mn = stats.get("min") or {}
            pts = stats.get("pts") or {}
            rows.append(
                {
                    "game": path.stem,
                    "player_name": player.get("player_name"),
                    "team": player.get("team_abbr"),
                    "min_mean": float(mn.get("mean") or 0.0),
                    "pts_mean": float(pts.get("mean") or 0.0),
                    "reb_mean": mean_reb,
                    "reb_median": float(reb.get("p50") or reb.get("median") or 0.0),
                }
            )
    rows.sort(key=lambda r: -r["reb_mean"])
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", default="2025-26")
    parser.add_argument("--runs", type=int, default=200)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-games", type=int, default=250)
    parser.add_argument("--threshold", type=float, default=3.0)
    parser.add_argument("--out-dir", default="results/backtest/reconcile_step1")
    args = parser.parse_args(argv)

    settings = load_settings()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seasons = parse_seasons(args.seasons)
    season = seasons[0]

    print(f"=== Full-season actuals {season} ===", flush=True)
    actual = actual_league_team_averages(settings, season)
    shares = actual_starter_shares(settings, season)
    print(json.dumps({"team": actual, "starter_share": shares}, indent=2), flush=True)

    print(
        f"\n=== Walk-forward reconcile runs={args.runs} max_games={args.max_games} ===",
        flush=True,
    )
    report = run_walkforward_reconcile(
        settings,
        season=season,
        runs=args.runs,
        seed=args.seed,
        max_games=args.max_games if args.max_games > 0 else None,
        threshold_pct=args.threshold,
    )
    text = format_report(report)
    (out_dir / "reconcile.md").write_text(text, encoding="utf-8")
    payload = report.to_dict()
    # dataclasses may contain non-JSON bits
    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items() if k != "sample_matched"}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        if isinstance(obj, (float, int, str, bool)) or obj is None:
            return obj
        return str(obj)

    (out_dir / "reconcile.json").write_text(
        json.dumps(_clean(payload), indent=2) + "\n", encoding="utf-8"
    )
    print(text, flush=True)

    slate = _slate_center_rebounds(Path("results/latest"))
    slate_path = out_dir / "tonight_big_boards.json"
    slate_path.write_text(json.dumps(slate, indent=2) + "\n", encoding="utf-8")
    print("\n=== Tonight's slate players with REB mean >= 10 ===", flush=True)
    for row in slate:
        print(
            f"  {row['game']}: {row['player_name']} ({row['team']}) "
            f"MIN={row['min_mean']:.1f} PTS={row['pts_mean']:.1f} "
            f"REB mean={row['reb_mean']:.1f} med={row['reb_median']:.1f}",
            flush=True,
        )

    print(f"\nwrote {out_dir / 'reconcile.md'}", flush=True)
    finish_run(settings)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
