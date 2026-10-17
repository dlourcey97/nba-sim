"""Multi-season baseline, recent form, and position regression."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from nba_sim.settings import Settings
from nba_sim.storage import list_seasons, read_rows

from projections.rates import (
    RateVector,
    add_game_to_accumulator,
    blend_vectors,
    empty_accumulator,
    position_bucket,
    vector_from_accumulator,
)


@dataclass
class SeasonBundle:
    season: str
    rates_by_player: dict[int, list[dict]]
    logs_by_player: dict[int, list[dict]]
    # defender_team_id -> opponent player-log rows (for as_of defense scans)
    logs_by_defender: dict[int, list[dict]] | None = None
    # (game_id, player_id) -> rate row
    rates_by_key: dict[tuple[str, int], dict] | None = None
    # all logs sorted by game_date (league-wide defense scans)
    logs_sorted: list[dict] | None = None


def available_season_window(settings: Settings, current: str, seasons_back: list[int]) -> list[str]:
    """Seasons used for blending.

    Prefer the configured seasons_back offsets. When those partitions are missing
    (partial DATA_DIR during backfill), fall back to older available seasons so
    early-season games still get a baseline and roster.
    """
    have = sorted(
        season
        for season in list_seasons(settings.data_dir, "player_game_rates")
        if season <= current
    )
    start = int(current.split("-")[0])
    preferred: list[str] = []
    for back in seasons_back:
        year = start - int(back)
        label = f"{year}-{str(year + 1)[-2:]}"
        if label in have and label not in preferred:
            preferred.append(label)
    if preferred:
        return preferred
    # Partial DATA_DIR: no configured offsets on disk yet — use whatever exists.
    return list(reversed(have))


def load_season_bundle(
    settings: Settings,
    season: str,
    *,
    season_type: str | None = None,
) -> SeasonBundle:
    rates_by_player: dict[int, list[dict]] = defaultdict(list)
    rates_by_key: dict[tuple[str, int], dict] = {}
    for row in read_rows(settings, "player_game_rates", season, season_type=season_type):
        pid = int(row["player_id"])
        rates_by_player[pid].append(row)
        rates_by_key[(str(row["game_id"]), pid)] = row
    logs_by_player: dict[int, list[dict]] = defaultdict(list)
    logs_by_defender: dict[int, list[dict]] = defaultdict(list)
    for row in read_rows(settings, "player_game_logs", season, season_type=season_type):
        logs_by_player[int(row["player_id"])].append(row)
        logs_by_defender[int(row["opponent_team_id"])].append(row)
    for mapping in (rates_by_player, logs_by_player):
        for player_id, rows in mapping.items():
            mapping[player_id] = sorted(rows, key=lambda item: item["game_date"])
    for defender_id, rows in logs_by_defender.items():
        logs_by_defender[defender_id] = sorted(rows, key=lambda item: item["game_date"])
    logs_sorted = sorted(
        (row for rows in logs_by_player.values() for row in rows),
        key=lambda item: item["game_date"],
    )
    return SeasonBundle(
        season,
        dict(rates_by_player),
        dict(logs_by_player),
        dict(logs_by_defender),
        rates_by_key,
        logs_sorted,
    )


def build_position_priors(
    bundles: list[SeasonBundle],
    *,
    as_of: date | None = None,
) -> dict[str, RateVector]:
    buckets: dict[str, dict[str, float]] = defaultdict(empty_accumulator)
    for bundle in bundles:
        log_index = {
            (row["game_id"], row["player_id"]): row
            for rows in bundle.logs_by_player.values()
            for row in rows
            if as_of is None or row["game_date"] < as_of
        }
        for player_id, rates in bundle.rates_by_player.items():
            for rate in rates:
                if as_of is not None and rate["game_date"] >= as_of:
                    continue
                log = log_index.get((rate["game_id"], rate["player_id"]))
                bucket = position_bucket(None if log is None else log.get("position"))
                add_game_to_accumulator(buckets[bucket], rate_row=rate, log_row=log, weight=1.0)
    return {bucket: vector_from_accumulator(acc) for bucket, acc in buckets.items()}


def player_baseline_and_form(
    bundles: list[SeasonBundle],
    *,
    player_id: int,
    as_of: date,
    current_season: str,
    config: dict[str, Any],
    priors: dict[str, RateVector],
    position: str | None,
) -> RateVector:
    blend_cfg = config["blending"]
    seasons_back = list(blend_cfg["season_weights"]["seasons_back"])
    weights = list(blend_cfg["season_weights"]["weights"])
    form_decay = float(blend_cfg["form_decay"])
    regression_strength = float(blend_cfg["regression_strength"])
    min_games_for_form = int(blend_cfg["min_games_for_form"])

    weight_by_season = {}
    start = int(current_season.split("-")[0])
    for back, weight in zip(seasons_back, weights):
        year = start - int(back)
        label = f"{year}-{str(year + 1)[-2:]}"
        weight_by_season[label] = float(weight)
    # Distant fallback seasons (present in DATA_DIR but outside seasons_back) get
    # a small residual weight so they still contribute when recent years are absent.
    fallback_weight = min(weights) * 0.25 if weights else 0.05

    baseline_vectors: list[tuple[RateVector, float]] = []
    form_acc = empty_accumulator()
    form_games = 0

    for bundle in bundles:
        rates = [row for row in bundle.rates_by_player.get(player_id, []) if row["game_date"] < as_of]
        if not rates:
            continue
        logs = {
            (row["game_id"], row["player_id"]): row
            for row in bundle.logs_by_player.get(player_id, [])
            if row["game_date"] < as_of
        }
        season_acc = empty_accumulator()
        ordered = sorted(rates, key=lambda row: row["game_date"], reverse=True)
        for index, rate in enumerate(ordered):
            log = logs.get((rate["game_id"], rate["player_id"]))
            add_game_to_accumulator(season_acc, rate_row=rate, log_row=log, weight=1.0)
            if bundle.season == current_season:
                weight = math.exp(-form_decay * index)
                add_game_to_accumulator(form_acc, rate_row=rate, log_row=log, weight=weight)
                form_games += 1
        season_vector = vector_from_accumulator(season_acc)
        season_weight = weight_by_season.get(bundle.season, fallback_weight)
        baseline_vectors.append((season_vector, season_weight))

    prior = priors.get(position_bucket(position)) or priors.get("G") or RateVector()
    # Season weights sum to ~1. Shrink toward the position prior using
    # regression_strength as pseudo-possessions against the blended sample size
    # (not as a raw weight of 12 next to weights that sum to 1, which flattened
    # every star toward league-average usage).
    if not baseline_vectors:
        baseline = blend_vectors([], prior=prior, prior_strength=1.0)
    else:
        raw = blend_vectors(baseline_vectors)
        data_weight = max(float(raw.sample_possessions), 1.0)
        baseline = blend_vectors(
            [(raw, data_weight)],
            prior=prior,
            prior_strength=regression_strength,
        )
    if form_games < min_games_for_form:
        return baseline
    form = vector_from_accumulator(form_acc)
    form_weight = min(0.75, form_games / (form_games + 10.0))
    return blend_vectors([(baseline, 1.0 - form_weight), (form, form_weight)])


def load_player_meta(
    bundles: list[SeasonBundle],
    *,
    as_of: date | None = None,
) -> dict[int, dict[str, Any]]:
    meta: dict[int, dict[str, Any]] = {}
    for bundle in bundles:
        for player_id, rows in bundle.logs_by_player.items():
            for row in rows:
                if as_of is not None and row["game_date"] >= as_of:
                    continue
                meta[player_id] = {
                    "player_name": row["player_name"],
                    "position": row.get("position"),
                    "team_id": int(row["team_id"]),
                    "team_abbr": row["team_abbr"],
                }
    return meta
