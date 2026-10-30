"""Tune blend parameters against walk-forward prediction-vs-actual results."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.evaluate import evaluate_seasons
from ingest.parse import parse_seasons
from nba_sim.errors import NbaSimError
from nba_sim.settings import load_settings
from nba_sim.storage import finish_run

HOLDOUT_SEASON = "2024-25"


def score_report(report) -> float:
    """Lower is better. Optimize calibration, not MAE alone.

    Primary: log loss (win prob), CRPS (PTS distributions), 10–90 coverage
    near 80%, PIT mean near 0.5. MAE is a light tiebreaker only.
    """
    log_loss_win = getattr(report, "log_loss_win", float("nan"))
    crps_pts = getattr(report, "crps_pts", float("nan"))
    pit_mean = getattr(report, "pit_pts_mean", float("nan"))
    parts = [
        1.50 * float(log_loss_win),
        0.10 * float(crps_pts),
        2.00 * abs(float(report.coverage_10_90) - 0.80),
        1.00 * abs(float(pit_mean) - 0.50),
        0.50 * float(report.brier_win),
        0.01 * float(report.mae_pts),
    ]
    if any(value != value for value in parts):  # NaN check
        return 1e9
    return float(sum(parts))


def candidate_configs(base: dict) -> list[dict]:
    """Small grid around the current blending knobs."""
    form_values = [0.04, 0.08, 0.12]
    reg_values = [6.0, 12.0, 20.0]
    weight_sets = [
        [0.50, 0.25, 0.15, 0.10],
        [0.60, 0.25, 0.10, 0.05],
        [0.40, 0.30, 0.20, 0.10],
    ]
    out: list[dict] = []
    for form in form_values:
        for reg in reg_values:
            for weights in weight_sets:
                cfg = copy.deepcopy(base)
                cfg["blending"]["form_decay"] = form
                cfg["blending"]["regression_strength"] = reg
                cfg["blending"]["season_weights"]["weights"] = list(weights)
                out.append(cfg)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tune config.yaml blend parameters.")
    parser.add_argument("--seasons", required=True)
    parser.add_argument("--runs", type=int, default=300)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-games", type=int, default=12)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Overwrite config.yaml blending section with the best candidate.",
    )
    parser.add_argument(
        "--out",
        help="JSON path for the tuning report. Default: results/backtest/tune.json",
    )
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        seasons = parse_seasons(args.seasons)
        if HOLDOUT_SEASON in seasons:
            print(
                f"{HOLDOUT_SEASON} is the holdout season and cannot be used for tuning.",
                file=sys.stderr,
            )
            return 2
        base = copy.deepcopy(settings.config)
        trials = []
        best_score = 1e9
        best_cfg = base
        for index, cfg in enumerate(candidate_configs(base)):
            report = evaluate_seasons(
                settings,
                seasons,
                runs=args.runs,
                seed=args.seed,
                max_games=args.max_games,
                config_override=cfg,
            )
            value = score_report(report)
            trial = {
                "index": index,
                "score": value,
                "form_decay": cfg["blending"]["form_decay"],
                "regression_strength": cfg["blending"]["regression_strength"],
                "weights": cfg["blending"]["season_weights"]["weights"],
                "metrics": report.as_dict(),
            }
            trials.append(trial)
            print(
                f"trial {index}: score={value:.4f} form={trial['form_decay']} "
                f"reg={trial['regression_strength']} "
                f"logloss={getattr(report, 'log_loss_win', float('nan')):.4f} "
                f"crps_pts={getattr(report, 'crps_pts', float('nan')):.3f} "
                f"cov={report.coverage_10_90:.3f}"
            )
            if value < best_score:
                best_score = value
                best_cfg = cfg

        payload = {
            "best_score": best_score,
            "best_blending": best_cfg["blending"],
            "trials": trials,
        }
        out_path = Path(args.out) if args.out else settings.repo_root / "results" / "backtest" / "tune.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_path}")
        if args.write:
            config_path = settings.repo_root / "config.yaml"
            with config_path.open(encoding="utf-8") as handle:
                current = yaml.safe_load(handle)
            current["blending"] = best_cfg["blending"]
            config_path.write_text(yaml.safe_dump(current, sort_keys=False), encoding="utf-8")
            print(f"updated {config_path}")
        finish_run(settings)
    except NbaSimError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
