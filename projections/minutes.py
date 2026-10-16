"""Minutes projection with rotation priors, team totals of 240, and sim draws."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence

import numpy as np

from projections.blend import SeasonBundle

# Default depth-chart minutes when a rostered player has little/no same-team history.
# Index 0 ≈ primary starter slot; deeper indexes get fewer minutes.
_DEFAULT_DEPTH_MINUTES = (
    34.0,
    32.0,
    30.0,
    28.0,
    26.0,
    22.0,
    18.0,
    14.0,
    10.0,
    6.0,
    3.0,
    0.0,
    0.0,
    0.0,
    0.0,
)


@dataclass(frozen=True)
class MinutesProjection:
    mean: float
    sd: float
    min_minutes: float
    max_minutes: float
    out: bool

    def sample(self, rng: np.random.Generator, size: int = 1) -> np.ndarray:
        if self.out or self.mean <= 0:
            return np.zeros(size, dtype=float)
        draws = rng.normal(self.mean, self.sd, size=size)
        return np.clip(draws, self.min_minutes, self.max_minutes)


def recent_minutes(
    bundles: Sequence[SeasonBundle],
    *,
    player_id: int,
    team_id: int,
    as_of: date,
    current_season: str,
    window: int = 10,
) -> tuple[float, float, list[date]]:
    """Return mean minutes, sample sd, and prior game dates for rest calc."""
    mean, sd, dates, _n = recent_minutes_detail(
        bundles,
        player_id=player_id,
        team_id=team_id,
        as_of=as_of,
        current_season=current_season,
        window=window,
    )
    return mean, sd, dates


def recent_minutes_detail(
    bundles: Sequence[SeasonBundle],
    *,
    player_id: int,
    team_id: int,
    as_of: date,
    current_season: str,
    window: int = 10,
    recent_decay: float = 0.0,
) -> tuple[float, float, list[date], int]:
    """Same as recent_minutes plus the number of same-team samples used.

    When ``recent_decay`` > 0, the mean weights newer games more
    (weight for age k is exp(-recent_decay * k), k=0 most recent).
    """
    values: list[float] = []
    dates: list[date] = []
    same_team = True
    for bundle in bundles:
        if bundle.season != current_season and values:
            continue
        rows = [
            row
            for row in bundle.logs_by_player.get(player_id, [])
            if row["game_date"] < as_of and int(row["team_id"]) == team_id
        ]
        for row in rows:
            values.append(float(row["minutes"] or 0.0))
            dates.append(row["game_date"])
    if not values:
        same_team = False
        # Fall back to any team in the window.
        for bundle in bundles:
            rows = [
                row
                for row in bundle.logs_by_player.get(player_id, [])
                if row["game_date"] < as_of
            ]
            for row in rows:
                values.append(float(row["minutes"] or 0.0))
                dates.append(row["game_date"])
    if not values:
        return 0.0, 0.0, [], 0
    # Keep chronological order, then take the last `window` games.
    paired = sorted(zip(dates, values), key=lambda item: item[0])
    paired = paired[-window:]
    recent_dates = [item[0] for item in paired]
    recent = [item[1] for item in paired]
    if recent_decay > 0 and len(recent) > 1:
        weights = [
            float(np.exp(-recent_decay * (len(recent) - 1 - index)))
            for index in range(len(recent))
        ]
        mean = float(sum(value * weight for value, weight in zip(recent, weights)) / sum(weights))
    else:
        mean = float(sum(recent) / len(recent))
    if len(recent) == 1:
        sd = 4.0
    else:
        sd = float(np.std(recent, ddof=1))
    # Off-team fallback is a weaker signal for this roster slot.
    n = len(recent) if same_team else max(1, len(recent) // 2)
    return mean, sd, recent_dates, n


def depth_prior_minutes(depth_rank: int, config: dict[str, Any]) -> float:
    """Minutes prior from as-of roster depth (0 = most used / highest priority)."""
    minutes_cfg = config.get("minutes", {})
    priors = minutes_cfg.get("depth_minutes") or _DEFAULT_DEPTH_MINUTES
    if depth_rank < 0:
        return 0.0
    if depth_rank >= len(priors):
        return 0.0
    return float(priors[depth_rank])


def rotation_base_minutes(
    *,
    recent_mean: float,
    recent_n: int,
    depth_rank: int,
    started: bool,
    config: dict[str, Any],
) -> float:
    """Blend recent same-team minutes with roster depth prior."""
    minutes_cfg = config["minutes"]
    depth = depth_prior_minutes(depth_rank, config)
    min_rotation = int(minutes_cfg.get("min_rotation_size", 9))
    # Players outside the intended rotation need real minutes history to crack in.
    if recent_n <= 0 and depth_rank >= min_rotation:
        return 0.0
    if recent_n <= 0:
        base = depth
    elif recent_n < 3:
        # Sparse sample: blend toward depth chart.
        w = recent_n / 3.0
        base = w * recent_mean + (1.0 - w) * max(depth, recent_mean * 0.5)
    else:
        # Strong recent signal, but keep a light depth pull so benches do not vanish.
        base = 0.85 * recent_mean + 0.15 * depth
    if started:
        starter_floor = float(minutes_cfg.get("starter_floor", 24.0))
        base = max(base, starter_floor)
    elif depth_rank < min_rotation and base > 0:
        # Soft bench floor so rotation players keep non-trivial minutes.
        bench_floor = float(minutes_cfg.get("bench_floor", 6.0))
        if depth_rank >= 5:
            base = max(base, bench_floor)
    return float(max(0.0, base))


def project_minutes(
    *,
    base_mean: float,
    base_sd: float,
    config: dict[str, Any],
    status: str | None,
    minutes_cap: float | None,
    started: bool,
) -> MinutesProjection:
    """Per-player injury/status adjustment before team allocation."""
    minutes_cfg = config["minutes"]
    min_minutes = float(minutes_cfg["min_minutes"])
    max_minutes = float(minutes_cfg["max_minutes"])
    variance = float(minutes_cfg["minutes_variance"])
    foul_prior = float(minutes_cfg["foul_trouble_rate_prior"])

    status_norm = (status or "available").lower()
    if status_norm in {"out", "doubtful"}:
        return MinutesProjection(0.0, 0.0, 0.0, 0.0, True)

    mean = base_mean
    if status_norm == "questionable":
        mean *= 0.85
    elif status_norm == "probable":
        mean *= 0.95
    # Light starter/bench tilt only — team allocation owns the hard redistribution.
    if started and mean > 0:
        mean = max(mean, float(minutes_cfg.get("starter_floor", 24.0)) * 0.9)
    elif not started and mean > 28.0:
        mean = 28.0

    mean *= 1.0 - 0.5 * foul_prior
    if minutes_cap is not None:
        mean = min(mean, float(minutes_cap))
        max_minutes = min(max_minutes, float(minutes_cap))
    mean = float(np.clip(mean, min_minutes, max_minutes))
    sd = max(variance * 0.5, (base_sd if base_sd > 0 else variance))
    if minutes_cap is not None:
        sd = min(sd, max(1.0, float(minutes_cap) * 0.15))
    return MinutesProjection(mean, sd, min_minutes, max_minutes, False)


def allocate_team_minutes(
    projections: Sequence[MinutesProjection],
    *,
    config: dict[str, Any],
    depth_ranks: Sequence[int] | None = None,
) -> list[MinutesProjection]:
    """Scale available players so projected means sum to team_minutes_target."""
    minutes_cfg = config["minutes"]
    target = float(minutes_cfg.get("team_minutes_target", 240.0))
    max_minutes = float(minutes_cfg["max_minutes"])
    min_minutes = float(minutes_cfg["min_minutes"])
    variance = float(minutes_cfg["minutes_variance"])
    min_rotation = int(minutes_cfg.get("min_rotation_size", 9))
    max_rotation = int(minutes_cfg.get("max_rotation_size", 11))
    play_threshold = float(minutes_cfg.get("play_threshold", 1.0))

    n = len(projections)
    if n == 0:
        return []

    means = np.array([0.0 if p.out else float(p.mean) for p in projections], dtype=float)
    caps = np.array(
        [0.0 if p.out else float(p.max_minutes) for p in projections],
        dtype=float,
    )
    out = np.array([p.out for p in projections], dtype=bool)
    sds = np.array([float(p.sd) for p in projections], dtype=float)

    # Expand thin rotations using depth chart so 8–10+ players typically play.
    active_idx = np.where(~out)[0]
    ranks = list(depth_ranks) if depth_ranks is not None else list(range(n))
    if active_idx.size:
        playing = int(np.sum(means[active_idx] > play_threshold))
        if playing < min_rotation:
            candidates = sorted(
                (i for i in active_idx if means[i] <= play_threshold),
                key=lambda i: ranks[i] if i < len(ranks) else 99,
            )
            for i in candidates:
                if playing >= min_rotation:
                    break
                floor = depth_prior_minutes(ranks[i] if i < len(ranks) else 99, config)
                if floor <= 0:
                    floor = float(minutes_cfg.get("bench_floor", 6.0))
                means[i] = max(means[i], floor)
                playing += 1

        # Concentrate on the top rotation; fringe DNPs stay at 0.
        ranked = sorted(
            (i for i in active_idx if means[i] > play_threshold),
            key=lambda i: (-means[i], ranks[i] if i < len(ranks) else 99),
        )
        if len(ranked) > max_rotation:
            for i in ranked[max_rotation:]:
                means[i] = 0.0
        # Lock zeroed fringe out of cap-room redistribution (cap=0 ⇒ no share).
        for i in active_idx:
            if means[i] <= play_threshold:
                caps[i] = 0.0
                means[i] = 0.0

    means = _normalize_to_target(means, caps=caps, out=out, target=target, min_minutes=min_minutes)

    out_proj: list[MinutesProjection] = []
    for i, prev in enumerate(projections):
        if out[i]:
            out_proj.append(MinutesProjection(0.0, 0.0, 0.0, 0.0, True))
            continue
        mean = float(means[i])
        cap = float(caps[i])
        sd = max(variance * 0.5, sds[i] if sds[i] > 0 else variance)
        # Scale sd lightly with mean so low-minute players do not swing wildly.
        if mean < 12.0:
            sd = min(sd, max(1.5, mean * 0.35 + 1.0))
        out_proj.append(
            MinutesProjection(
                mean=mean,
                sd=sd,
                min_minutes=min_minutes,
                max_minutes=cap if cap > 0 else max_minutes,
                out=False,
            )
        )
    return out_proj


def normalize_team_minute_draws(
    draws: np.ndarray,
    *,
    out_mask: np.ndarray,
    caps: np.ndarray,
    target: float = 240.0,
    min_minutes: float = 0.0,
) -> np.ndarray:
    """Normalize per-run minute draws so each column sums to ``target``.

    ``draws`` shape is (n_players, n_runs). Out players stay at 0. Values are
    clipped to each player's cap after scaling.
    """
    if draws.size == 0:
        return draws
    out = np.asarray(out_mask, dtype=bool).reshape(-1)
    cap = np.asarray(caps, dtype=float).reshape(-1)
    result = np.array(draws, dtype=float, copy=True)
    result[out, :] = 0.0
    # Negative noise → 0 before scaling.
    result = np.maximum(result, 0.0)
    n_players, n_runs = result.shape
    for run in range(n_runs):
        col = result[:, run]
        available = ~out
        if not np.any(available):
            continue
        col = _normalize_vector(
            col,
            available=available,
            caps=cap,
            target=target,
            min_minutes=min_minutes,
        )
        result[:, run] = col
    return result


def add_overtime_minutes(
    minutes: np.ndarray,
    *,
    home_idx: np.ndarray,
    away_idx: np.ndarray,
    ot_periods: np.ndarray,
    out_mask: np.ndarray,
    caps: np.ndarray,
) -> np.ndarray:
    """Add 25 team-minutes per OT period, split by regulation minute share."""
    if minutes.size == 0 or not np.any(ot_periods > 0):
        return minutes
    result = np.array(minutes, dtype=float, copy=True)
    out = np.asarray(out_mask, dtype=bool)
    cap = np.asarray(caps, dtype=float)
    for pool in (home_idx, away_idx):
        if pool.size == 0:
            continue
        team = result[pool]
        team_out = out[pool]
        team_cap = cap[pool]
        for run in range(result.shape[1]):
            periods = int(ot_periods[run])
            if periods <= 0:
                continue
            bonus = 25.0 * periods
            weights = team[:, run].copy()
            weights[team_out] = 0.0
            total = float(weights.sum())
            if total <= 0:
                active = np.where(~team_out)[0]
                if active.size == 0:
                    continue
                share = np.zeros_like(weights)
                share[active] = 1.0 / active.size
            else:
                share = weights / total
            add = share * bonus
            new_vals = team[:, run] + add
            # Soft cap: allow OT to push slightly above regulation max.
            soft_cap = np.where(team_out, 0.0, np.maximum(team_cap, team_cap + 5.0 * periods))
            team[:, run] = np.minimum(new_vals, soft_cap)
        result[pool] = team
    return result


def _normalize_to_target(
    means: np.ndarray,
    *,
    caps: np.ndarray,
    out: np.ndarray,
    target: float,
    min_minutes: float,
) -> np.ndarray:
    values = means.astype(float).copy()
    values[out] = 0.0
    return _normalize_vector(
        values,
        available=~out,
        caps=caps,
        target=target,
        min_minutes=min_minutes,
    )


def _normalize_vector(
    values: np.ndarray,
    *,
    available: np.ndarray,
    caps: np.ndarray,
    target: float,
    min_minutes: float,
) -> np.ndarray:
    """Iteratively scale and clip so available players sum to target.

    Players with ``caps[i] <= 0`` are locked at zero (out / fringe) even if
    marked available. Positive caps are hard per-player maxima.
    """
    out = values.astype(float).copy()
    out[~available] = 0.0
    flexible = available & (np.asarray(caps, dtype=float) > 0)
    out[~flexible] = 0.0
    if not np.any(flexible):
        return out
    # Seed zeros with a tiny epsilon so a blank rotation can still scale.
    if float(out[flexible].sum()) <= 1e-9:
        out[flexible] = 1.0

    for _ in range(12):
        out = np.clip(out, 0.0, None)
        out[~flexible] = 0.0
        for i in np.where(flexible)[0]:
            cap = float(caps[i])
            out[i] = min(out[i], cap)
            if out[i] > 0 and min_minutes > 0:
                out[i] = max(out[i], min_minutes)

        total = float(out[flexible].sum())
        if total <= 1e-9:
            out[flexible] = target / float(np.sum(flexible))
            total = float(out[flexible].sum())

        if abs(total - target) < 1e-4:
            break

        if total > target:
            out[flexible] *= target / total
        else:
            deficit = target - total
            room = np.zeros_like(out)
            for i in np.where(flexible)[0]:
                room[i] = max(0.0, float(caps[i]) - out[i])
            room_sum = float(room.sum())
            if room_sum <= 1e-9:
                out[flexible] *= target / max(total, 1e-9)
            else:
                out += room * (deficit / room_sum)

    total = float(out[flexible].sum())
    if total > 1e-9 and abs(total - target) > 1e-3:
        scaled = out.copy()
        scaled[flexible] *= target / total
        ok = True
        for i in np.where(flexible)[0]:
            if scaled[i] > float(caps[i]) + 1e-6:
                ok = False
                break
        if ok:
            out = scaled
    out[~flexible] = 0.0
    return out
