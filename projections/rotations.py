"""Stint-based rotation model: who plays together, by period and score margin.

Learns from compact `lineup_stints` when present, with a box-score margin
fallback so walk-forward backtests work before every season is rebuilt.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Sequence

import numpy as np

from nba_sim.settings import Settings
from nba_sim.storage import read_rows
from projections.blend import SeasonBundle


# Depth-rank multipliers by expected / realized margin bucket.
# close → shorten rotation (stars up, fringe down); blowout → bench up.
_DEFAULT_DEPTH_MULT = {
    # rank 0..10
    "close": (1.08, 1.06, 1.04, 1.02, 1.00, 0.95, 0.85, 0.70, 0.45, 0.20, 0.05),
    "moderate": (1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 0.95, 0.80, 0.50, 0.20),
    "blowout": (0.90, 0.90, 0.88, 0.88, 0.92, 1.05, 1.15, 1.25, 1.40, 1.50, 1.20),
}

# Period share of total minutes by depth tier (starters vs bench) for close games.
# Index: period 1..4. Values are relative weights (normalized later).
_DEFAULT_PERIOD_STARTER = (1.10, 0.95, 1.00, 1.15)  # starters heavier Q1/Q4
_DEFAULT_PERIOD_BENCH = (0.90, 1.10, 1.05, 0.75)


@dataclass
class RotationModel:
    """League + team rotation priors conditioned on margin and period."""

    depth_mult: dict[str, tuple[float, ...]] = field(
        default_factory=lambda: {k: tuple(v) for k, v in _DEFAULT_DEPTH_MULT.items()}
    )
    # (team_id, player_id) -> partner_id -> shared possession weight
    coappear: dict[tuple[int, int], dict[int, float]] = field(default_factory=dict)
    # period (1-4) -> mean stint duration seconds (league)
    mean_stint_sec: dict[int, float] = field(
        default_factory=lambda: {1: 180.0, 2: 160.0, 3: 160.0, 4: 140.0}
    )
    # period × margin_bucket -> rotation size prior
    rotation_size: dict[tuple[int, str], float] = field(default_factory=dict)
    source: str = "defaults"

    def expected_bucket(self, abs_margin: float, config: dict[str, Any]) -> str:
        minutes_cfg = config.get("minutes", {})
        blowout = float(minutes_cfg.get("blowout_margin_threshold", 15.0))
        close = float(minutes_cfg.get("close_margin_threshold", 6.0))
        if abs_margin < close:
            return "close"
        if abs_margin < blowout:
            return "moderate"
        return "blowout"

    def adjust_means(
        self,
        means: Sequence[float],
        depth_ranks: Sequence[int],
        *,
        expected_abs_margin: float,
        config: dict[str, Any],
    ) -> list[float]:
        """Scale projected means by depth × expected margin bucket; renormalize later."""
        bucket = self.expected_bucket(expected_abs_margin, config)
        mults = self.depth_mult.get(bucket, self.depth_mult["moderate"])
        out: list[float] = []
        for mean, rank in zip(means, depth_ranks):
            if mean <= 0:
                out.append(0.0)
                continue
            idx = int(np.clip(rank, 0, len(mults) - 1))
            out.append(float(mean) * float(mults[idx]))
        return out

    def period_weights(
        self,
        depth_rank: int,
        *,
        period: int,
        margin_bucket_name: str,
    ) -> float:
        """Relative minutes weight for a player in a period under a margin state."""
        period = int(np.clip(period, 1, 4))
        starter = depth_rank <= 4
        base = (
            _DEFAULT_PERIOD_STARTER[period - 1]
            if starter
            else _DEFAULT_PERIOD_BENCH[period - 1]
        )
        if margin_bucket_name == "blowout":
            # Flatten: starters down late, bench up.
            if starter and period >= 3:
                base *= 0.75
            if not starter:
                base *= 1.25 if period >= 3 else 1.05
        elif margin_bucket_name == "close":
            if starter and period == 4:
                base *= 1.20
            if not starter and period == 4:
                base *= 0.55
        return float(base)

    def partner_boost(self, team_id: int, player_id: int, partner_id: int) -> float:
        weights = self.coappear.get((team_id, player_id))
        if not weights:
            return 1.0
        total = sum(weights.values()) or 1.0
        share = weights.get(partner_id, 0.0) / total
        return 1.0 + 0.35 * share


def load_rotation_model(
    settings: Settings,
    bundles: Sequence[SeasonBundle],
    *,
    as_of: date,
    config: dict[str, Any],
) -> RotationModel:
    """Build a rotation model from stints as_of date, with box-score fallback."""
    model = RotationModel()
    stint_rows: list[dict] = []
    seasons_seen: list[str] = []
    for bundle in bundles:
        try:
            rows = read_rows(settings, "lineup_stints", bundle.season)
        except Exception:
            rows = []
        if not rows:
            continue
        seasons_seen.append(bundle.season)
        for row in rows:
            game_date = row["game_date"]
            if hasattr(game_date, "isoformat") and game_date >= as_of:
                continue
            stint_rows.append(row)

    if stint_rows:
        _fit_from_stints(model, stint_rows)
        model.source = "stints:" + ",".join(seasons_seen)
    else:
        team_rows: list[dict] = []
        for bundle in bundles:
            try:
                team_rows.extend(read_rows(settings, "team_game_results", bundle.season))
            except Exception:
                continue
        _fit_from_box_scores(
            model, bundles, team_rows, as_of=as_of, config=config
        )
        model.source = "box_scores"
    return model


def expected_abs_margin_from_strength(
    home_ortg: float,
    home_drtg: float,
    away_ortg: float,
    away_drtg: float,
    *,
    possessions: float = 100.0,
) -> float:
    """Crude pregame absolute margin from offensive/defensive ratings."""
    home_exp = possessions * (home_ortg + (200.0 - away_drtg)) / 200.0
    away_exp = possessions * (away_ortg + (200.0 - home_drtg)) / 200.0
    # Ratings are typically ~110; use net rating gap scaled to points.
    home_net = (home_ortg - home_drtg) - (away_ortg - away_drtg)
    return float(abs(home_net) * possessions / 100.0)


def _fit_from_stints(model: RotationModel, rows: list[dict]) -> None:
    # Co-appearance from shared stints.
    pair_sec: dict[tuple[int, int], dict[int, float]] = defaultdict(lambda: defaultdict(float))
    stint_dur: dict[int, list[float]] = defaultdict(list)
    rot_size: dict[tuple[int, str], list[int]] = defaultdict(list)
    # Per game+team+period: set of players who appeared
    game_period_players: dict[tuple[str, int, int, str], set[int]] = defaultdict(set)

    for row in rows:
        team_id = int(row["team_id"])
        period = int(row["period"])
        if period > 4:
            period = 4
        dur = float(row.get("duration_sec") or 0.0)
        bucket = str(row.get("margin_bucket") or "moderate")
        players = [int(row[f"p{i}"]) for i in range(1, 6)]
        stint_dur[period].append(max(dur, 1.0))
        key = (str(row["game_id"]), team_id, period, bucket)
        for pid in players:
            game_period_players[key].add(pid)
        for i, a in enumerate(players):
            for b in players[i + 1 :]:
                pair_sec[(team_id, a)][b] += dur
                pair_sec[(team_id, b)][a] += dur

    for key, players in game_period_players.items():
        _game, _team, period, bucket = key
        rot_size[(period, bucket)].append(len(players))

    model.coappear = {k: dict(v) for k, v in pair_sec.items()}
    for period, durs in stint_dur.items():
        if durs:
            model.mean_stint_sec[period] = float(np.median(durs))
    for key, sizes in rot_size.items():
        if sizes:
            model.rotation_size[key] = float(np.mean(sizes))

    # Depth multipliers from stint seconds by margin × within-game minute rank.
    # Approximate: aggregate player duration by margin, then by rank within team-game.
    by_game: dict[tuple[str, int], dict[int, float]] = defaultdict(lambda: defaultdict(float))
    game_bucket: dict[tuple[str, int], str] = {}
    for row in rows:
        key = (str(row["game_id"]), int(row["team_id"]))
        dur = float(row.get("duration_sec") or 0.0)
        bucket = str(row.get("margin_bucket") or "moderate")
        game_bucket[key] = bucket  # last write; fine for mid-game mix
        for i in range(1, 6):
            by_game[key][int(row[f"p{i}"])] += dur

    # Also track per-bucket totals for rank profiles
    rank_secs: dict[str, list[list[float]]] = {
        "close": [[] for _ in range(11)],
        "moderate": [[] for _ in range(11)],
        "blowout": [[] for _ in range(11)],
    }
    for key, player_secs in by_game.items():
        bucket = game_bucket.get(key, "moderate")
        if bucket not in rank_secs:
            bucket = "moderate"
        ordered = sorted(player_secs.values(), reverse=True)
        for rank, sec in enumerate(ordered[:11]):
            rank_secs[bucket][rank].append(sec / 60.0)  # minutes

    baseline = []
    for rank in range(11):
        vals = rank_secs["moderate"][rank] or rank_secs["close"][rank] or rank_secs["blowout"][rank]
        baseline.append(float(np.mean(vals)) if vals else _depth_prior(rank))

    new_mult: dict[str, list[float]] = {}
    for bucket, ranks in rank_secs.items():
        mults = []
        for rank in range(11):
            vals = ranks[rank]
            mean = float(np.mean(vals)) if vals else baseline[rank]
            base = baseline[rank] if baseline[rank] > 0.5 else 1.0
            mults.append(float(np.clip(mean / base, 0.2, 1.8)))
        new_mult[bucket] = mults
    # Blend with defaults so sparse early-season data does not explode.
    blended = {}
    for bucket, mults in new_mult.items():
        defaults = _DEFAULT_DEPTH_MULT[bucket]
        blended[bucket] = tuple(
            0.55 * m + 0.45 * d for m, d in zip(mults, defaults)
        )
    model.depth_mult = blended


def _fit_from_box_scores(
    model: RotationModel,
    bundles: Sequence[SeasonBundle],
    team_rows: Sequence[dict],
    *,
    as_of: date,
    config: dict[str, Any],
) -> None:
    """Learn depth × margin multipliers from final box scores."""
    minutes_cfg = config.get("minutes", {})
    blowout = float(minutes_cfg.get("blowout_margin_threshold", 15.0))
    close = float(minutes_cfg.get("close_margin_threshold", 6.0))

    # game_id -> team_id -> margin
    margins: dict[str, dict[int, int]] = {}
    for row in team_rows:
        if row["game_date"] >= as_of:
            continue
        gid = str(row["game_id"])
        team_id = int(row["team_id"])
        margin = int(row["pts"]) - int(row["opp_pts"])
        margins.setdefault(gid, {})[team_id] = margin

    rank_mins: dict[str, list[list[float]]] = {
        "close": [[] for _ in range(11)],
        "moderate": [[] for _ in range(11)],
        "blowout": [[] for _ in range(11)],
    }
    # Also co-minutes proxy: players with 10+ min same team-game.
    pair_min: dict[tuple[int, int], dict[int, float]] = defaultdict(lambda: defaultdict(float))

    for bundle in bundles:
        # Group logs by game+team
        by_game_team: dict[tuple[str, int], list[tuple[int, float]]] = defaultdict(list)
        for player_id, rows in bundle.logs_by_player.items():
            for row in rows:
                if row["game_date"] >= as_of:
                    break
                mins = float(row.get("minutes") or 0.0)
                if mins <= 0:
                    continue
                key = (str(row["game_id"]), int(row["team_id"]))
                by_game_team[key].append((int(player_id), mins))

        for (gid, team_id), players in by_game_team.items():
            margin = margins.get(gid, {}).get(team_id)
            if margin is None:
                continue
            abs_m = abs(margin)
            if abs_m < close:
                bucket = "close"
            elif abs_m < blowout:
                bucket = "moderate"
            else:
                bucket = "blowout"
            ordered = sorted(players, key=lambda x: -x[1])
            for rank, (_pid, mins) in enumerate(ordered[:11]):
                rank_mins[bucket][rank].append(mins)
            rotation = [(pid, m) for pid, m in ordered if m >= 10.0]
            for i, (a, ma) in enumerate(rotation):
                for b, mb in rotation[i + 1 :]:
                    shared = min(ma, mb)
                    pair_min[(team_id, a)][b] += shared
                    pair_min[(team_id, b)][a] += shared

    baseline = []
    for rank in range(11):
        vals = rank_mins["moderate"][rank] or rank_mins["close"][rank]
        baseline.append(float(np.mean(vals)) if vals else _depth_prior(rank))

    blended = {}
    for bucket, ranks in rank_mins.items():
        defaults = _DEFAULT_DEPTH_MULT[bucket]
        mults = []
        for rank in range(11):
            vals = ranks[rank]
            mean = float(np.mean(vals)) if vals else baseline[rank]
            base = baseline[rank] if baseline[rank] > 0.5 else 1.0
            learned = float(np.clip(mean / base, 0.25, 1.75))
            mults.append(0.60 * learned + 0.40 * defaults[rank])
        blended[bucket] = tuple(mults)
    model.depth_mult = blended
    model.coappear = {k: dict(v) for k, v in pair_min.items()}


def _depth_prior(rank: int) -> float:
    priors = (34, 32, 30, 28, 26, 22, 18, 14, 10, 6, 3)
    return float(priors[rank] if rank < len(priors) else 0.0)
