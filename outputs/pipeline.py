"""Run projections + simulations + outputs for one or more games."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Sequence

from ingest.injuries import InjuryEntry, fetch_injuries_for_date, load_overrides, merge_injuries
from nba_sim.settings import Settings
from nba_sim.storage import finish_run, read_rows
from outputs.history import fill_actuals_for_season, write_prediction_history
from outputs.json_writer import clear_latest, write_game_json
from outputs.summarize import GameSummary, summarize_game
from projections.build import build_game_projections
from sim.engine import simulate_game


@dataclass
class SlateResult:
    summaries: list[GameSummary] = field(default_factory=list)
    json_paths: list[Path] = field(default_factory=list)
    history_rows: int = 0
    actuals_rows: int = 0


def run_game(
    settings: Settings,
    *,
    season: str,
    game_id: str,
    runs: int | None = None,
    seed: int | None = None,
    injuries: Sequence[InjuryEntry] | None = None,
    thresholds: Sequence[tuple[str, float]] | None = None,
    write_json: bool = True,
    write_history: bool = True,
    allow_historical: bool = False,
    clear_json_first: bool = False,
) -> SlateResult:
    return run_slate(
        settings,
        season=season,
        game_ids=[game_id],
        runs=runs,
        seed=seed,
        injuries=injuries,
        thresholds=thresholds,
        write_json=write_json,
        write_history=write_history,
        allow_historical=allow_historical,
        clear_json_first=clear_json_first,
    )


def run_slate(
    settings: Settings,
    *,
    season: str,
    game_ids: Sequence[str] | None = None,
    game_date: date | None = None,
    runs: int | None = None,
    seed: int | None = None,
    injuries: Sequence[InjuryEntry] | None = None,
    thresholds: Sequence[tuple[str, float]] | None = None,
    write_json: bool = True,
    write_history: bool = True,
    allow_historical: bool = False,
    clear_json_first: bool = False,
    finish: bool = False,
    season_type: str | None = None,
    minutes_bundles: list | None = None,
    minutes_recent_decay: float | None = None,
) -> SlateResult:
    schedule = read_rows(settings, "schedule", season, season_type=season_type)
    selected = []
    for row in schedule:
        if game_ids is not None and str(row["game_id"]) not in set(game_ids):
            continue
        if game_date is not None and row["game_date"] != game_date:
            continue
        selected.append(row)
    if not selected:
        raise ValueError("no schedule games matched the request")

    injury_rows = list(injuries) if injuries is not None else []
    result = SlateResult()
    if clear_json_first and write_json:
        clear_latest(settings.repo_root)

    for row in sorted(selected, key=lambda item: item["game_id"]):
        projection = build_game_projections(
            settings,
            season=season,
            game_id=str(row["game_id"]),
            injuries=injury_rows,
            as_of=row["game_date"],
            season_type=season_type,
            minutes_bundles=minutes_bundles,
            minutes_recent_decay=minutes_recent_decay,
        )
        sim = simulate_game(
            projection,
            runs=runs,
            seed=seed,
            config=settings.config,
        )
        summary = summarize_game(projection, sim, thresholds=thresholds)
        # Typical-game narrative: persist one possession log + WP chart only.
        # WP grid is computed from the full sim cloud in memory, then discarded.
        try:
            from outputs.typical_game import (
                build_typical_game,
                write_typical_game_artifacts,
            )

            _idx, typical_log = build_typical_game(
                projection, sim, config=settings.config
            )
            chart_dir = settings.repo_root / "results" / "typical"
            paths = write_typical_game_artifacts(
                projection=projection,
                result=sim,
                log=typical_log,
                out_dir=chart_dir,
            )
            result.json_paths.append(paths["html"])
        except Exception as exc:
            print(f"typical-game skipped for {projection.game_id}: {exc}")
        # Drop raw runs immediately (typical log already extracted).
        del sim
        result.summaries.append(summary)
        if write_json:
            result.json_paths.append(write_game_json(settings.repo_root, summary))
        if write_history:
            result.history_rows += write_prediction_history(
                settings,
                summary,
                allow_historical=allow_historical,
            )

    if write_history:
        result.actuals_rows = fill_actuals_for_season(
            settings,
            season,
            allow_historical=allow_historical,
        )
    if finish:
        finish_run(settings)
    return result


def injuries_for_date(settings: Settings, game_date: date, *, fetch_pdf: bool = True) -> list[InjuryEntry]:
    overrides_path = settings.repo_root / "overrides.yaml"
    http = settings.config["http"]
    if fetch_pdf:
        return fetch_injuries_for_date(
            game_date,
            overrides_path=overrides_path,
            delay_seconds=float(http["delay_seconds"]),
            max_retries=int(http["max_retries"]),
            backoff_seconds=float(http["backoff_seconds"]),
            timeout_seconds=float(http["timeout_seconds"]),
        )
    overrides = load_overrides(overrides_path)
    return merge_injuries([], overrides, game_date=game_date)
