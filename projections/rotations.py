"""Stint-based rotation model (Step F).

Learns from compact `lineup_stints` plus box-score absence history:

- depth × margin multipliers (close games shorten rotations; blowouts bench early)
- co-appearance and substitution edges (who checks in for whom)
- closing-lineup shares (Q4 close games)
- typical stint length by period × starter/bench

When a player is OUT, freed minutes go to historical replacements first
(not evenly across the roster). Minutes caps from overrides still bind.
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
    "close": (1.08, 1.06, 1.04, 1.02, 1.00, 0.95, 0.85, 0.70, 0.45, 0.20, 0.05),
    "moderate": (1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 0.95, 0.80, 0.50, 0.20),
    "blowout": (0.90, 0.90, 0.88, 0.88, 0.92, 1.05, 1.15, 1.25, 1.40, 1.50, 1.20),
}

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
    # (team_id, out_player_id) -> in_player_id -> replacement weight
    replacements: dict[tuple[int, int], dict[int, float]] = field(default_factory=dict)
    # (team_id, player_id) -> closing (Q4 close) seconds
    closing_sec: dict[tuple[int, int], float] = field(default_factory=dict)
    # period (1-4) -> mean stint duration seconds (league)
    mean_stint_sec: dict[int, float] = field(
        default_factory=lambda: {1: 180.0, 2: 160.0, 3: 160.0, 4: 140.0}
    )
    # (period, is_starter) -> mean stint seconds
    role_stint_sec: dict[tuple[int, bool], float] = field(default_factory=dict)
    # period × margin_bucket -> rotation size prior
    rotation_size: dict[tuple[int, str], float] = field(default_factory=dict)
    source: str = "defaults"
    step_f: bool = False

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
        player_ids: Sequence[int] | None = None,
        team_id: int | None = None,
    ) -> list[float]:
        """Scale projected means by depth × expected margin bucket; renormalize later."""
        bucket = self.expected_bucket(expected_abs_margin, config)
        mults = self.depth_mult.get(bucket, self.depth_mult["moderate"])
        out: list[float] = []
        for i, (mean, rank) in enumerate(zip(means, depth_ranks)):
            if mean <= 0:
                out.append(0.0)
                continue
            idx = int(np.clip(rank, 0, len(mults) - 1))
            scaled = float(mean) * float(mults[idx])
            # Step F: closing-lineup boost in expected close games for players
            # who historically close; soft haircut for non-closers among stars.
            if (
                self.step_f
                and bucket == "close"
                and player_ids is not None
                and team_id is not None
                and rank <= 6
            ):
                pid = int(player_ids[i])
                close_share = self.closing_share(team_id, pid)
                if close_share > 0:
                    scaled *= 1.0 + 0.12 * min(close_share, 1.0)
                elif rank <= 4:
                    scaled *= 0.97
            out.append(scaled)
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
        # Blend in learned stint-length prior when Step F is on.
        if self.step_f:
            learned = self.role_stint_sec.get((period, starter))
            if learned is not None and learned > 0:
                league = self.mean_stint_sec.get(period, 160.0) or 160.0
                base *= float(np.clip(learned / league, 0.75, 1.35))
        if margin_bucket_name == "blowout":
            # Blowouts: bench earlier (Q2+) and more; starters sit late.
            if starter and period >= 2:
                base *= 0.82 if period >= 3 else 0.92
            if not starter:
                base *= 1.30 if period >= 3 else 1.12
        elif margin_bucket_name == "close":
            if starter and period == 4:
                base *= 1.25
            if not starter and period == 4:
                base *= 0.50
            if starter and period == 1:
                base *= 1.05
        return float(base)

    def partner_boost(self, team_id: int, player_id: int, partner_id: int) -> float:
        weights = self.coappear.get((team_id, player_id))
        if not weights:
            return 1.0
        total = sum(weights.values()) or 1.0
        share = weights.get(partner_id, 0.0) / total
        return 1.0 + 0.35 * share

    def closing_share(self, team_id: int, player_id: int) -> float:
        """Share of this team's Q4-close seconds that belong to the player."""
        key = (int(team_id), int(player_id))
        own = self.closing_sec.get(key, 0.0)
        if own <= 0:
            return 0.0
        team_total = sum(
            sec for (tid, _pid), sec in self.closing_sec.items() if tid == int(team_id)
        )
        if team_total <= 0:
            return 0.0
        return float(own / team_total)

    def replacement_weights(
        self,
        team_id: int,
        out_player_id: int,
        active_ids: Sequence[int],
    ) -> dict[int, float]:
        """Normalized weights over active teammates who replace ``out_player_id``."""
        raw = self.replacements.get((int(team_id), int(out_player_id)), {})
        active = {int(pid) for pid in active_ids}
        weights = {pid: float(w) for pid, w in raw.items() if pid in active and w > 0}
        if weights:
            total = sum(weights.values()) or 1.0
            return {pid: w / total for pid, w in weights.items()}
        return {}


def redistribute_minutes_for_absences(
    player_ids: Sequence[int],
    means: Sequence[float],
    *,
    team_id: int,
    out_ids: set[int],
    caps: dict[int, float] | None,
    model: RotationModel,
    config: dict[str, Any],
) -> list[float]:
    """Move OUT players' minutes onto historical replacements, then leftovers by share.

    Respects minutes_cap overrides. Does not re-normalize to 240 (caller allocates).
    """
    if not out_ids or not model.step_f:
        return list(means)
    minutes_cfg = config.get("minutes", {})
    share = float(minutes_cfg.get("replacement_share", 0.85))
    out = [float(m) for m in means]
    id_list = [int(pid) for pid in player_ids]
    index = {pid: i for i, pid in enumerate(id_list)}
    caps = caps or {}

    active = [pid for pid in id_list if pid not in out_ids and out[index[pid]] >= 0]
    for out_pid in list(out_ids):
        if out_pid not in index:
            continue
        oi = index[out_pid]
        freed = out[oi]
        if freed <= 0:
            out[oi] = 0.0
            continue
        out[oi] = 0.0
        via_graph = freed * share
        via_usage = freed - via_graph
        weights = model.replacement_weights(team_id, out_pid, active)
        if weights:
            for pid, w in weights.items():
                j = index[pid]
                out[j] += via_graph * w
        else:
            via_usage += via_graph
            via_graph = 0.0
        active_means = sum(max(out[index[pid]], 0.0) for pid in active) or 1.0
        for pid in active:
            j = index[pid]
            out[j] += via_usage * (max(out[j], 0.0) / active_means)

    # Re-apply caps after redistribution.
    for pid, cap in caps.items():
        if pid in index:
            out[index[pid]] = min(out[index[pid]], float(cap))
    # Zero any still-marked OUT (cap path should not revive them).
    for out_pid in out_ids:
        if out_pid in index:
            out[index[out_pid]] = 0.0
    return out


def load_rotation_model(
    settings: Settings,
    bundles: Sequence[SeasonBundle],
    *,
    as_of: date,
    config: dict[str, Any],
    stint_cache: dict[str, list] | None = None,
) -> RotationModel:
    """Build a rotation model from stints as_of date, with box-score fallback."""
    features = config.get("features") or {}
    step_f = bool(features.get("stint_rotations_step_f", True))
    model = RotationModel(step_f=step_f)
    stint_rows: list[dict] = []
    seasons_seen: list[str] = []
    half_life = float(
        (config.get("minutes") or {}).get("stint_recency_half_life_days", 60.0)
    )

    # Prefer 2025-26 + current season when present (Step F training window).
    preferred = []
    other = []
    current = str(settings.current_season)
    for bundle in bundles:
        if bundle.season in {"2025-26", current} or bundle.season >= "2025-26":
            preferred.append(bundle)
        else:
            other.append(bundle)
    ordered_bundles = preferred + other

    for bundle in ordered_bundles:
        if stint_cache is not None and bundle.season in stint_cache:
            rows = stint_cache[bundle.season]
        else:
            try:
                rows = read_rows(settings, "lineup_stints", bundle.season)
            except Exception:
                rows = []
            if stint_cache is not None:
                stint_cache[bundle.season] = rows
        if not rows:
            continue
        seasons_seen.append(bundle.season)
        for row in rows:
            game_date = row["game_date"]
            if hasattr(game_date, "isoformat") and game_date >= as_of:
                continue
            stint_rows.append(row)

    if stint_rows:
        # Soft cap sample size but keep recent games: sort by date, keep tail.
        if len(stint_rows) > 45000:
            stint_rows = sorted(
                stint_rows,
                key=lambda r: r["game_date"],
            )[-45000:]
        _fit_from_stints(model, stint_rows, as_of=as_of, half_life_days=half_life)
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

    if step_f:
        _fit_replacements_from_logs(
            model, bundles, as_of=as_of, half_life_days=half_life
        )
        if "absence_logs" not in model.source:
            model.source = model.source + "+absence_logs"
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
    home_net = (home_ortg - home_drtg) - (away_ortg - away_drtg)
    return float(abs(home_net) * possessions / 100.0)


def _recency_weight(game_date: date, as_of: date, half_life_days: float) -> float:
    if half_life_days <= 0:
        return 1.0
    try:
        age = max(0, (as_of - game_date).days)
    except Exception:
        return 1.0
    return float(np.exp(-np.log(2.0) * age / half_life_days))


def _fit_from_stints(
    model: RotationModel,
    rows: list[dict],
    *,
    as_of: date,
    half_life_days: float,
) -> None:
    pair_sec: dict[tuple[int, int], dict[int, float]] = defaultdict(lambda: defaultdict(float))
    stint_dur: dict[int, list[float]] = defaultdict(list)
    role_dur: dict[tuple[int, bool], list[float]] = defaultdict(list)
    rot_size: dict[tuple[int, str], list[int]] = defaultdict(list)
    game_period_players: dict[tuple[str, int, int, str], set[int]] = defaultdict(set)
    closing: dict[tuple[int, int], float] = defaultdict(float)
    # Substitution edges from one-player lineup swaps within a game/team/period.
    sub_w: dict[tuple[int, int], dict[int, float]] = defaultdict(lambda: defaultdict(float))

    # Group stints for substitution diffs.
    by_gtp: dict[tuple[str, int, int], list[tuple[float, frozenset[int], str]]] = defaultdict(
        list
    )

    # Per-game minutes for starter labeling (top-5 by duration).
    by_game_team_sec: dict[tuple[str, int], dict[int, float]] = defaultdict(
        lambda: defaultdict(float)
    )

    for row in rows:
        team_id = int(row["team_id"])
        period = int(row["period"])
        if period > 4:
            period = 4
        dur = float(row.get("duration_sec") or 0.0)
        bucket = str(row.get("margin_bucket") or "moderate")
        players = [int(row[f"p{i}"]) for i in range(1, 6)]
        w = _recency_weight(row["game_date"], as_of, half_life_days)
        weighted_dur = max(dur, 1.0) * w
        stint_dur[period].append(max(dur, 1.0))
        key = (str(row["game_id"]), team_id, period, bucket)
        for pid in players:
            game_period_players[key].add(pid)
            by_game_team_sec[(str(row["game_id"]), team_id)][pid] += dur
        for i, a in enumerate(players):
            for b in players[i + 1 :]:
                pair_sec[(team_id, a)][b] += weighted_dur
                pair_sec[(team_id, b)][a] += weighted_dur
        # Closing: Q4 + close margin.
        if period == 4 and bucket == "close":
            for pid in players:
                closing[(team_id, pid)] += weighted_dur
        by_gtp[(str(row["game_id"]), team_id, period)].append(
            (weighted_dur, frozenset(players), bucket)
        )

    # Starter labels per game-team = top 5 by total stint seconds.
    starters_by_game: dict[tuple[str, int], set[int]] = {}
    for key, secs in by_game_team_sec.items():
        ordered = sorted(secs, key=lambda pid: -secs[pid])[:5]
        starters_by_game[key] = set(ordered)

    for row in rows:
        team_id = int(row["team_id"])
        period = min(4, int(row["period"]))
        dur = float(row.get("duration_sec") or 0.0)
        players = [int(row[f"p{i}"]) for i in range(1, 6)]
        starters = starters_by_game.get((str(row["game_id"]), team_id), set())
        for pid in players:
            role_dur[(period, pid in starters)].append(max(dur, 1.0))

    # Substitution edges: within each game/team/period, any two lineups that
    # differ by exactly one player contribute out→in weight.
    for (game_id, team_id, period), stints in by_gtp.items():
        if len(stints) < 2:
            continue
        # Sort by duration descending as a weak proxy when clock is absent;
        # also compare all pairs (soft counts).
        for i in range(len(stints)):
            for j in range(i + 1, len(stints)):
                _d1, a, _b1 = stints[i]
                _d2, b, _b2 = stints[j]
                if len(a) != 5 or len(b) != 5:
                    continue
                only_a = a - b
                only_b = b - a
                if len(only_a) == 1 and len(only_b) == 1:
                    out_pid = next(iter(only_a))
                    in_pid = next(iter(only_b))
                    w = 0.5 * (_d1 + _d2)
                    sub_w[(team_id, out_pid)][in_pid] += w
                    # Symmetric: the reverse swap is also observed.
                    sub_w[(team_id, in_pid)][out_pid] += 0.25 * w

    for key, players in game_period_players.items():
        _game, _team, period, bucket = key
        rot_size[(period, bucket)].append(len(players))

    model.coappear = {k: dict(v) for k, v in pair_sec.items()}
    model.closing_sec = dict(closing)
    for (team_id, out_pid), inbound in sub_w.items():
        model.replacements.setdefault((team_id, out_pid), {})
        for in_pid, w in inbound.items():
            model.replacements[(team_id, out_pid)][in_pid] = (
                model.replacements[(team_id, out_pid)].get(in_pid, 0.0) + float(w)
            )

    for period, durs in stint_dur.items():
        if durs:
            model.mean_stint_sec[period] = float(np.median(durs))
    for key, durs in role_dur.items():
        if durs:
            model.role_stint_sec[key] = float(np.median(durs))
    for key, sizes in rot_size.items():
        if sizes:
            model.rotation_size[key] = float(np.mean(sizes))

    # Depth multipliers from stint seconds by margin × within-game minute rank.
    by_game: dict[tuple[str, int], dict[int, float]] = defaultdict(lambda: defaultdict(float))
    game_bucket: dict[tuple[str, int], str] = {}
    game_weight: dict[tuple[str, int], float] = {}
    for row in rows:
        key = (str(row["game_id"]), int(row["team_id"]))
        dur = float(row.get("duration_sec") or 0.0)
        bucket = str(row.get("margin_bucket") or "moderate")
        w = _recency_weight(row["game_date"], as_of, half_life_days)
        game_bucket[key] = bucket
        game_weight[key] = max(game_weight.get(key, 0.0), w)
        for i in range(1, 6):
            by_game[key][int(row[f"p{i}"])] += dur

    rank_secs: dict[str, list[list[float]]] = {
        "close": [[] for _ in range(11)],
        "moderate": [[] for _ in range(11)],
        "blowout": [[] for _ in range(11)],
    }
    for key, player_secs in by_game.items():
        bucket = game_bucket.get(key, "moderate")
        if bucket not in rank_secs:
            bucket = "moderate"
        w = game_weight.get(key, 1.0)
        ordered = sorted(player_secs.values(), reverse=True)
        for rank, sec in enumerate(ordered[:11]):
            # Repeat soft-weighted samples (1–3) instead of fractional lists.
            reps = max(1, int(round(w * 2)))
            for _ in range(min(reps, 3)):
                rank_secs[bucket][rank].append(sec / 60.0)

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
    blended = {}
    for bucket, mults in new_mult.items():
        defaults = _DEFAULT_DEPTH_MULT[bucket]
        # Step F leans a bit more on learned multipliers than U2.
        alpha = 0.62 if model.step_f else 0.55
        blended[bucket] = tuple(
            alpha * m + (1.0 - alpha) * d for m, d in zip(mults, defaults)
        )
    model.depth_mult = blended


def _fit_replacements_from_logs(
    model: RotationModel,
    bundles: Sequence[SeasonBundle],
    *,
    as_of: date,
    half_life_days: float,
) -> None:
    """When a usual rotation player sits (0 MIN), who gains minutes that night."""
    # First pass: player+team mean minutes before as_of.
    sum_min: dict[tuple[int, int], float] = defaultdict(float)
    count: dict[tuple[int, int], float] = defaultdict(float)
    games: list[tuple[date, int, str, dict[int, float]]] = []

    for bundle in bundles:
        by_game: dict[tuple[str, int], dict[int, float]] = defaultdict(dict)
        dates: dict[tuple[str, int], date] = {}
        for player_id, rows in bundle.logs_by_player.items():
            for row in rows:
                if row["game_date"] >= as_of:
                    break
                mins = float(row.get("minutes") or 0.0)
                team_id = int(row["team_id"])
                key = (str(row["game_id"]), team_id)
                by_game[key][int(player_id)] = mins
                dates[key] = row["game_date"]
                sum_min[(team_id, int(player_id))] += mins
                count[(team_id, int(player_id))] += 1.0
        for key, players in by_game.items():
            games.append((dates[key], key[1], key[0], players))

    avg: dict[tuple[int, int], float] = {
        k: sum_min[k] / count[k] for k in sum_min if count[k] >= 3
    }

    for game_date, team_id, _gid, players in games:
        w = _recency_weight(game_date, as_of, half_life_days)
        # Usual rotation players who sat this game.
        out_candidates = [
            pid
            for (tid, pid), mean_m in avg.items()
            if tid == team_id and mean_m >= 12.0 and players.get(pid, 0.0) <= 0.5
        ]
        if not out_candidates:
            continue
        gainers = []
        for pid, mins in players.items():
            mean_m = avg.get((team_id, pid), 0.0)
            delta = mins - mean_m
            if delta > 2.0 and mins >= 8.0:
                gainers.append((pid, delta))
        if not gainers:
            continue
        for out_pid in out_candidates:
            # Skip if out player never co-appeared historically with team (avg exists).
            bucket = model.replacements.setdefault((team_id, out_pid), {})
            for in_pid, delta in gainers:
                if in_pid == out_pid:
                    continue
                bucket[in_pid] = bucket.get(in_pid, 0.0) + float(delta * w)


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
    pair_min: dict[tuple[int, int], dict[int, float]] = defaultdict(lambda: defaultdict(float))

    for bundle in bundles:
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
