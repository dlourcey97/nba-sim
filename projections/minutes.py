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
    # P(plays tonight). Sampled before minutes: sit-outs are exact zeros, then
    # team normalize redistributes to players who drew "plays".
    play_prob: float = 1.0

    def sample(self, rng: np.random.Generator, size: int = 1) -> np.ndarray:
        if self.out or self.mean <= 0 or self.play_prob <= 0:
            return np.zeros(size, dtype=float)
        draws = rng.normal(self.mean, self.sd, size=size)
        draws = np.clip(draws, self.min_minutes, self.max_minutes)
        if self.play_prob < 1.0 - 1e-12:
            plays = rng.random(size) < float(self.play_prob)
            draws = np.where(plays, draws, 0.0)
        return draws


def estimate_play_prob(
    *,
    status: str | None,
    appear_rate: float,
    started: bool,
    depth_rank: int,
    base_mean: float,
    minutes_cap: float | None,
) -> float:
    """P(plays tonight) from injury status, recent DNP rate, and rotation role.

    ``appear_rate`` is fraction of recent team games with minutes > 0 (0–1).
    Conditional minutes (``mean``) stay as projected minutes *given* he plays.
    """
    status_norm = (status or "available").lower()
    if status_norm in {"out", "doubtful"}:
        return 0.0
    appear = float(np.clip(appear_rate, 0.0, 1.0))
    # Rotation prior when appearance history is missing (rookies / new team).
    if started or (depth_rank <= 4 and base_mean >= 26.0):
        role = 0.98
    elif depth_rank <= 7 and base_mean >= 18.0:
        role = 0.94
    elif base_mean >= 10.0:
        role = 0.88
    elif base_mean > 0:
        role = 0.55
    else:
        role = 0.20
    # Available players: dress at their recent appear rate. Do not haircut a
    # 90% appearance guy down to ~80% via a role blend — that invented DNPs,
    # redistributed boards/points to starters, and broke role-share reconcile.
    base = appear if appear > 0 else role
    if started or base_mean >= 24.0:
        base = max(base, 0.96)
    elif base_mean >= 14.0:
        base = max(base, 0.88)
    elif base_mean >= 8.0:
        base = max(base, 0.70)
    if status_norm == "questionable":
        base = min(base, 0.62) * 0.90
    elif status_norm == "probable":
        base = max(base, 0.88) * 0.97
    if minutes_cap is not None and float(minutes_cap) <= 0:
        return 0.0
    return float(np.clip(base, 0.0, 0.995))


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
    team_game_dates: Sequence[date] | None = None,
) -> tuple[float, float, list[date], int]:
    """Same as recent_minutes plus the number of same-team samples used.

    When ``recent_decay`` > 0, the mean weights newer games more
    (weight for age k is exp(-recent_decay * k), k=0 most recent).

    When ``team_game_dates`` is provided, minutes are aligned to the team's last
    ``window`` games before ``as_of`` (missed games count as 0). That stops
    inactive / G-League players from carrying stale mid-season minutes into
    the 240 pool as ghost DNPs.
    """
    values: list[float] = []
    dates: list[date] = []
    same_team = True

    if team_game_dates is not None:
        # Align to the team's recent slate. Full absences (inactive) → 0.
        # Active rotation players who appear most nights use appearance means
        # so a rare coach DNP does not crush their projection.
        # Never-appeared on this team (trades / opening-night signings): do NOT
        # treat a full window of zeros as a strong same-team sample — fall
        # through to any-team history so stars keep their prior minutes.
        team_dates = sorted(d for d in team_game_dates if d < as_of)[-window:]
        if team_dates:
            by_date: dict[date, float] = {}
            for bundle in bundles:
                if bundle.season != current_season and by_date:
                    continue
                for row in bundle.logs_by_player.get(player_id, []):
                    if row["game_date"] < as_of and int(row["team_id"]) == team_id:
                        by_date[row["game_date"]] = float(row["minutes"] or 0.0)
            appeared = [by_date[d] for d in team_dates if d in by_date]
            aligned = [by_date.get(d, 0.0) for d in team_dates]
            appear_rate = len(appeared) / max(len(team_dates), 1)
            if appear_rate >= 0.5 and appeared:
                mean, sd, n = _summarize_recent(appeared[-window:], recent_decay, same_team=True)
                return mean, sd, team_dates, n
            if appear_rate > 0 and aligned:
                mean, sd, n = _summarize_recent(aligned, recent_decay, same_team=True)
                return mean, sd, team_dates, n
            # appear_rate == 0 → fall through to any-team history below.

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
    mean, sd, n = _summarize_recent(recent, recent_decay, same_team=same_team)
    if not same_team:
        # Cross-team history: keep nearly-full minutes only for true stars
        # (trade acquisions who were 32+ MPG). Everyone else drops to a
        # depth-chart-sized role so they cannot crowd out same-team rotation
        # players on opening night / week 1.
        if mean >= 32.0:
            mean = 0.85 * mean
        elif mean >= 24.0:
            mean = min(0.40 * mean, 14.0)
        else:
            mean = min(0.35 * mean, 10.0)
    return mean, sd, recent_dates, n


def naive_last10_minutes(
    bundles: Sequence[SeasonBundle],
    *,
    player_id: int,
    as_of: date,
    window: int = 10,
    recent_decay: float = 0.45,
) -> tuple[float, float, int]:
    """Weighted mean of the last ``window`` games the player actually played.

    Only appearances with minutes > 0 count (DNPs / inactive nights omitted).
    No team alignment, depth priors, or cross-team discounts.
    """
    paired: list[tuple[date, float]] = []
    for bundle in bundles:
        for row in bundle.logs_by_player.get(player_id, []):
            if row["game_date"] >= as_of:
                break
            mins = float(row.get("minutes") or 0.0)
            if mins <= 0:
                continue
            paired.append((row["game_date"], mins))
    if not paired:
        return 0.0, 0.0, 0
    paired.sort(key=lambda item: item[0])
    recent = [mins for _d, mins in paired[-window:]]
    mean, sd, n = _summarize_recent(recent, recent_decay, same_team=True)
    return mean, sd, n


def _summarize_recent(
    recent: Sequence[float],
    recent_decay: float,
    *,
    same_team: bool,
) -> tuple[float, float, int]:
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
    n = len(recent) if same_team else max(1, len(recent) // 2)
    return mean, sd, n


def effective_minutes_gap_close(
    *,
    current_season_games_before: int,
    config: dict[str, Any],
) -> float:
    """Gap-close used for allocate + sim draws.

    Mid-season (enough current-season finals): ``normalize_gap_close`` (usually 0)
    for best MIN MAE. Early season / opening night: ``early_season_gap_close`` so
    trade-inflated rosters still land near 240.
    """
    minutes_cfg = config.get("minutes", {})
    base = float(minutes_cfg.get("normalize_gap_close", 0.0))
    early_n = int(minutes_cfg.get("early_season_games", 10))
    if early_n > 0 and current_season_games_before < early_n:
        return float(minutes_cfg.get("early_season_gap_close", 0.55))
    return base


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
    """Blend recent same-team minutes with roster depth prior.

    Trust recent minutes heavily. Depth priors only fill sparse samples inside
    the intended rotation — they must not invent a full 11-man rotation of
    ghosts that later steal minutes when the team is scaled to 240.
    """
    minutes_cfg = config["minutes"]
    depth = depth_prior_minutes(depth_rank, config)
    min_rotation = int(minutes_cfg.get("min_rotation_size", 8))
    # Outside the intended rotation: need real same-team history to crack in.
    if recent_n <= 0 and depth_rank >= min_rotation:
        return 0.0
    # Deep depth with no prior minutes stays at 0 even if a tiny depth prior exists.
    if recent_n <= 0 and depth <= 0:
        return 0.0
    # Playoff stretches often run 40+ MPG; do not carry that into RS projections.
    if recent_n >= 5 and recent_mean > 36.0:
        recent_mean = 36.0
    if recent_n <= 0:
        base = depth
    elif recent_n < 3:
        w = recent_n / 3.0
        base = w * recent_mean + (1.0 - w) * max(depth, recent_mean * 0.5)
    else:
        # Strong recent signal — trust it fully (depth already ranked the roster).
        base = recent_mean
    if started:
        starter_floor = float(minutes_cfg.get("starter_floor", 24.0))
        base = max(base, starter_floor)
    elif depth_rank < min_rotation and base > 0:
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
    appear_rate: float = 1.0,
    depth_rank: int = 99,
) -> MinutesProjection:
    """Per-player injury/status adjustment before team allocation.

    Mean/sd are minutes *conditional on playing*. Sit-out risk is ``play_prob``.
    """
    minutes_cfg = config["minutes"]
    min_minutes = float(minutes_cfg["min_minutes"])
    max_minutes = float(minutes_cfg["max_minutes"])
    variance = float(minutes_cfg["minutes_variance"])
    foul_prior = float(minutes_cfg["foul_trouble_rate_prior"])

    status_norm = (status or "available").lower()
    if status_norm in {"out", "doubtful"}:
        return MinutesProjection(0.0, 0.0, 0.0, 0.0, True, play_prob=0.0)

    mean = base_mean
    # Do not haircut Q/Probable means — uncertainty is in play_prob draws.
    # Light starter tilt only — team allocation owns the hard redistribution.
    # Do not cap non-starters at 28: sixth men often play 30+.
    if started and mean > 0:
        mean = max(mean, float(minutes_cfg.get("starter_floor", 24.0)) * 0.9)

    # Foul trouble is already partly in recent minutes variance; keep a tiny haircut.
    mean *= 1.0 - 0.25 * foul_prior
    if minutes_cap is not None:
        mean = min(mean, float(minutes_cap))
        max_minutes = min(max_minutes, float(minutes_cap))
    mean = float(np.clip(mean, min_minutes, max_minutes))
    sd = max(variance * 0.5, (base_sd if base_sd > 0 else variance))
    if minutes_cap is not None:
        sd = min(sd, max(1.0, float(minutes_cap) * 0.15))
    play_prob = estimate_play_prob(
        status=status_norm,
        appear_rate=appear_rate,
        started=started,
        depth_rank=depth_rank,
        base_mean=mean,
        minutes_cap=minutes_cap,
    )
    return MinutesProjection(mean, sd, min_minutes, max_minutes, False, play_prob=play_prob)


def allocate_team_minutes(
    projections: Sequence[MinutesProjection],
    *,
    config: dict[str, Any],
    depth_ranks: Sequence[int] | None = None,
) -> list[MinutesProjection]:
    """Scale available players so projected means sum to team_minutes_target.

    Over-240 totals are trimmed from the bottom first (ghost / fringe DNPs)
    before any proportional shrink, so starters and rotation keep their means.
    """
    minutes_cfg = config["minutes"]
    target = float(minutes_cfg.get("team_minutes_target", 240.0))
    max_minutes = float(minutes_cfg["max_minutes"])
    min_minutes = float(minutes_cfg["min_minutes"])
    variance = float(minutes_cfg["minutes_variance"])
    min_rotation = int(minutes_cfg.get("min_rotation_size", 8))
    max_rotation = int(minutes_cfg.get("max_rotation_size", 10))
    play_threshold = float(minutes_cfg.get("play_threshold", 1.0))
    # Players at/above this mean are never truncated by max_rotation.
    keep_threshold = float(minutes_cfg.get("rotation_keep_threshold", 14.0))
    # When over target, zero players below this before proportional scale.
    fringe_cut = float(minutes_cfg.get("fringe_cut_minutes", 8.0))
    gap_close = float(minutes_cfg.get("normalize_gap_close", 0.55))

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

    active_idx = np.where(~out)[0]
    ranks = list(depth_ranks) if depth_ranks is not None else list(range(n))
    # gap_close > 0 → expand thin rotations and soft-scale toward 240
    # (early season / opening night when trade history overfills the roster).
    # gap_close == 0 → Step-2-like means for best MIN MAE: zero ghosts only;
    # extreme overfill (> target+40) fringe-trims without forcing exactly 240.
    if active_idx.size and gap_close > 0:
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
                    continue
                means[i] = max(means[i], floor)
                playing += 1

        ranked = sorted(
            (i for i in active_idx if means[i] > play_threshold),
            key=lambda i: (-means[i], ranks[i] if i < len(ranks) else 99),
        )
        if len(ranked) > max_rotation:
            for i in ranked[max_rotation:]:
                if means[i] < keep_threshold:
                    means[i] = 0.0

        for i in active_idx:
            if means[i] <= play_threshold:
                caps[i] = 0.0
                means[i] = 0.0

        total = float(means[~out].sum()) if np.any(~out) else 0.0
        if total > 1e-9:
            factor = 1.0 + float(gap_close) * (target / total - 1.0)
            star_protect = float(minutes_cfg.get("gap_close_star_floor", 34.0))
            if factor > 1.0:
                # Expanding toward 240: do not dump fringe cuts onto stars.
                scaled = means.copy()
                for i in np.where(~out)[0]:
                    if means[i] >= star_protect:
                        scaled[i] = means[i]
                    elif caps[i] > 0:
                        scaled[i] = means[i] * factor
                # If still short, give leftover to mid-rotation (8–star_protect).
                short = target - float(scaled[~out].sum())
                if short > 1.0:
                    mid = [
                        i
                        for i in np.where(~out)[0]
                        if 8.0 <= scaled[i] < star_protect and caps[i] > scaled[i]
                    ]
                    if mid:
                        room = np.array([caps[i] - scaled[i] for i in mid], dtype=float)
                        room_sum = float(room.sum())
                        if room_sum > 1e-9:
                            give = min(short, room_sum)
                            for i, r in zip(mid, room):
                                scaled[i] += give * (r / room_sum)
            else:
                scaled = means * factor
            for i in np.where(~out)[0]:
                if caps[i] > 0:
                    means[i] = min(float(scaled[i]), float(caps[i]))
                else:
                    means[i] = 0.0
    elif active_idx.size:
        for i in active_idx:
            if means[i] <= play_threshold:
                caps[i] = 0.0
                means[i] = 0.0
        total = float(means[~out].sum()) if np.any(~out) else 0.0
        # Only cut clear ghosts when the book is absurdly over regulation.
        if total > target + 40.0:
            means = _trim_from_bottom(
                means,
                caps=caps,
                out=out,
                target=target + 20.0,
                play_threshold=play_threshold,
                fringe_cut=fringe_cut,
                keep_threshold=keep_threshold,
                min_rotation=min_rotation,
            )

    out_proj: list[MinutesProjection] = []
    for i, prev in enumerate(projections):
        if out[i]:
            out_proj.append(
                MinutesProjection(0.0, 0.0, 0.0, 0.0, True, play_prob=0.0)
            )
            continue
        mean = float(means[i])
        cap = float(caps[i])
        # Historical / recent sd when available; floor from config (not inflated).
        sd = max(variance * 0.5, sds[i] if sds[i] > 0 else variance)
        # Cap sd for every band — mid-rotation players with volatile history
        # (e.g. post-injury) previously kept sd≈12 at ~24 MIN, which put PTS
        # p10 at 0 despite a healthy projected mean.
        if mean < 12.0:
            sd = min(sd, max(1.5, mean * 0.35 + 1.0))
        else:
            sd = min(sd, max(variance, mean * 0.20))
        out_proj.append(
            MinutesProjection(
                mean=mean,
                sd=sd,
                min_minutes=min_minutes,
                max_minutes=cap if cap > 0 else max_minutes,
                out=False,
                play_prob=float(prev.play_prob),
            )
        )
    return out_proj


def _trim_from_bottom(
    means: np.ndarray,
    *,
    caps: np.ndarray,
    out: np.ndarray,
    target: float,
    play_threshold: float,
    fringe_cut: float,
    keep_threshold: float,
    min_rotation: int = 8,
) -> np.ndarray:
    """Zero lowest minutes until the team total is near ``target``.

    Protects the top-5 by mean (typical starters). Cuts fringe first, then any
    non-protected player while above ``min_rotation``, so ghost DNPs do not
    force a proportional shrink of the real rotation.
    """
    values = means.astype(float).copy()
    values[out] = 0.0
    soft_target = target + 2.0
    while float(values.sum()) > soft_target:
        playing = [
            i
            for i in range(len(values))
            if not out[i] and values[i] > play_threshold
        ]
        if len(playing) <= min_rotation:
            break
        ranked = sorted(playing, key=lambda i: -values[i])
        protected = set(ranked[:5])
        # Prefer cutting clear fringe; if still over, cut any non-protected.
        fringe = [
            i
            for i in playing
            if i not in protected and values[i] < fringe_cut
        ]
        candidates = fringe or [i for i in playing if i not in protected]
        if not candidates:
            break
        victim = min(candidates, key=lambda i: (values[i], -i))
        # Stop cutting real rotation pieces unless still far over target.
        if values[victim] >= keep_threshold and float(values.sum()) < target + 25.0:
            break
        values[victim] = 0.0
        caps[victim] = 0.0
    return values


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
