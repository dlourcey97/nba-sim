"""Possession-by-possession game simulation, vectorized across runs.

Raw per-run draws stay in memory only long enough to build summaries. Callers
in outputs/ reduce the arrays and discard them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nba_sim.schema import ZONES
from projections.build import GameProjection, PlayerProjection
from projections.minutes import add_overtime_minutes, normalize_team_minute_draws

_ZONE_POINTS = np.array([2.0, 2.0, 2.0, 3.0, 3.0, 3.0])


@dataclass
class GameSimResult:
    game_id: str
    runs: int
    seed: int
    player_ids: np.ndarray
    player_names: list[str]
    team_abbrs: list[str]
    home_away: list[str]
    pts: np.ndarray
    reb: np.ndarray
    ast: np.ndarray
    fg3m: np.ndarray
    stl: np.ndarray
    blk: np.ndarray
    tov: np.ndarray
    minutes: np.ndarray
    home_pts: np.ndarray
    away_pts: np.ndarray
    overtime: np.ndarray
    # Mean projected/simulated possession endings per team (pace).
    home_possessions: float
    away_possessions: float


def simulate_game(
    projection: GameProjection,
    *,
    runs: int | None = None,
    seed: int | None = None,
    config: dict | None = None,
) -> GameSimResult:
    """Simulate one game. Default runs/seed come from config.yaml when omitted."""
    cfg = config or {}
    sim_cfg = cfg.get("simulation", {})
    n_runs = int(runs if runs is not None else sim_cfg.get("runs", 10000))
    if n_runs <= 0:
        raise ValueError("runs must be positive")
    base_seed = seed if seed is not None else sim_cfg.get("seed")
    if base_seed is None:
        base_seed = int(np.random.SeedSequence().entropy) % (2**31 - 1)
    rng = np.random.default_rng(int(base_seed))

    players = list(projection.players)
    n_players = len(players)
    if n_players == 0:
        raise ValueError(f"no players to simulate for {projection.game_id}")

    minutes = np.zeros((n_players, n_runs), dtype=float)
    for index, player in enumerate(players):
        minutes[index] = player.minutes.sample(rng, n_runs)

    home_idx = np.array([i for i, p in enumerate(players) if p.home_away == "H"], dtype=np.int32)
    away_idx = np.array([i for i, p in enumerate(players) if p.home_away == "A"], dtype=np.int32)
    if home_idx.size == 0 or away_idx.size == 0:
        raise ValueError("both home and away players are required")

    minutes_cfg = cfg.get("minutes", {})
    team_target = float(minutes_cfg.get("team_minutes_target", 240.0))
    min_minutes = float(minutes_cfg.get("min_minutes", 0.0))
    # When means are Step-2-like (gap_close=0), hard draw-normalize to 240
    # shrinks everyone whenever projected team totals exceed 240 and regenerates
    # the Fix 3 MIN MAE regression. Soft-close only nudges wild totals.
    gap_close = float(minutes_cfg.get("normalize_gap_close", 0.0))
    out_mask = np.array([p.minutes.out for p in players], dtype=bool)
    caps = np.array(
        [0.0 if p.minutes.out else float(p.minutes.max_minutes) for p in players],
        dtype=float,
    )
    for pool in (home_idx, away_idx):
        if gap_close >= 1.0:
            minutes[pool] = normalize_team_minute_draws(
                minutes[pool],
                out_mask=out_mask[pool],
                caps=caps[pool],
                target=team_target,
                min_minutes=min_minutes,
            )
        else:
            # gap_close=0: clip only, preserve projected means (Step 2 MAE).
            # Mild soft close when configured between 0 and 1.
            minutes[pool] = _soft_normalize_minute_draws(
                minutes[pool],
                out_mask=out_mask[pool],
                caps=caps[pool],
                target=team_target,
                gap_close=gap_close,
            )

    packed = _pack_rates(players)
    # Period × margin-bucket lineup grid (stint substitution model).
    # close games shorten rotations late; blowouts put the bench on the floor.
    minutes_cfg = cfg.get("minutes", {})
    close_thr = float(minutes_cfg.get("close_margin_threshold", 6.0))
    blowout_thr = float(minutes_cfg.get("blowout_margin_threshold", 15.0))
    expected_margin = float(getattr(projection, "expected_abs_margin", 8.0) or 8.0)
    rotation = getattr(projection, "rotation", None)
    home_grid = _lineups_state_grid(
        rng, home_idx, minutes, players, rotation=rotation
    )
    away_grid = _lineups_state_grid(
        rng, away_idx, minutes, players, rotation=rotation
    )

    sim_cfg = cfg.get("simulation", {})
    pace_sd = float(sim_cfg.get("pace_sd", 5.5))
    team_hot_sd = float(sim_cfg.get("team_hot_sd", 0.05))
    player_shoot_sd = float(sim_cfg.get("player_shoot_sd", 0.12))
    player_usage_sd = float(sim_cfg.get("player_usage_sd", 0.10))
    home_poss = np.clip(
        rng.normal(projection.home_possessions, pace_sd, size=n_runs), 80.0, 130.0
    )
    away_poss = np.clip(
        rng.normal(projection.away_possessions, pace_sd, size=n_runs), 80.0, 130.0
    )
    # Team-level hot/cold (small) + per-player tonight effects (main overdispersion).
    # Minutes noise is intentionally NOT inflated for coverage.
    home_hot = np.clip(rng.normal(1.0, team_hot_sd, size=n_runs), 0.88, 1.12)
    away_hot = np.clip(rng.normal(1.0, team_hot_sd, size=n_runs), 0.88, 1.12)
    player_hot = np.clip(
        rng.normal(1.0, player_shoot_sd, size=(n_players, n_runs)), 0.75, 1.30
    )
    player_usage = np.clip(
        rng.normal(1.0, player_usage_sd, size=(n_players, n_runs)), 0.70, 1.35
    )
    # Pace targets possession *endings* (NBA pace). OREB continuations must not
    # consume the budget — only dead balls, makes, FT trips, and DREBs count.
    base_target = np.clip(np.round(home_poss + away_poss).astype(int), 160, 260)
    target_endings = base_target.copy()
    late_pace_adjust = bool(sim_cfg.get("late_pace_adjust", True))
    game_state = getattr(projection, "game_state", None)
    if game_state is None:
        from projections.game_state import default_game_state_model

        game_state = default_game_state_model(cfg)
    foul_prob = float(
        sim_cfg.get("intentional_foul_prob", game_state.intentional_foul_prob)
    )
    pace_adjusted = np.zeros(n_runs, dtype=bool)

    pts = np.zeros((n_players, n_runs), dtype=float)
    reb = np.zeros((n_players, n_runs), dtype=float)
    ast = np.zeros((n_players, n_runs), dtype=float)
    fg3m = np.zeros((n_players, n_runs), dtype=float)
    stl = np.zeros((n_players, n_runs), dtype=float)
    blk = np.zeros((n_players, n_runs), dtype=float)
    tov = np.zeros((n_players, n_runs), dtype=float)
    home_pts = np.zeros(n_runs, dtype=float)
    away_pts = np.zeros(n_runs, dtype=float)

    offense_home = rng.random(n_runs) < 0.5
    endings = np.zeros(n_runs, dtype=np.int32)
    # Allow extra iterations for OREB retries (typical OREB rate ~25% of misses).
    max_iters = int(base_target.max() * 1.55) + 20
    run_ids = np.arange(n_runs)
    for _ in range(max_iters):
        active = endings < target_endings
        if not np.any(active):
            break
        period_idx, bucket_idx = _period_bucket_indexes(
            endings,
            base_target,
            home_pts,
            away_pts,
            expected_margin=expected_margin,
            close_thr=close_thr,
            blowout_thr=blowout_thr,
        )
        progress = endings.astype(float) / np.maximum(1.0, base_target.astype(float))
        # Once past ~70% of regulation, scale remaining endings by game state
        # (trail haste / lead slowdown / garbage time). Applied once per run.
        if late_pace_adjust:
            due = active & ~pace_adjusted & (progress >= 0.70)
            if np.any(due):
                factors = game_state.blend_factor_array(
                    period_idx,
                    np.abs(home_pts - away_pts),
                    close_thr=close_thr,
                    blowout_thr=blowout_thr,
                )
                remaining = np.maximum(0, target_endings - endings)
                target_endings = np.where(
                    due,
                    endings
                    + np.clip(np.round(remaining * factors), 8, 80).astype(np.int32),
                    target_endings,
                )
                target_endings = np.clip(target_endings, 160, 280)
                pace_adjusted |= due
        home_lineups = home_grid[run_ids, period_idx, bucket_idx]
        away_lineups = away_grid[run_ids, period_idx, bucket_idx]
        # Intentional fouls only matter in late Q4; skip the branch earlier.
        foul_p = foul_prob if float(progress.max()) >= 0.85 else 0.0
        home_delta, away_delta, offense_home, ended = _vector_possession(
            rng,
            packed,
            home_lineups,
            away_lineups,
            offense_home,
            active,
            pts,
            reb,
            ast,
            fg3m,
            stl,
            blk,
            tov,
            home_hot=home_hot,
            away_hot=away_hot,
            player_hot=player_hot,
            player_usage=player_usage,
            home_pts=home_pts if foul_p > 0 else None,
            away_pts=away_pts if foul_p > 0 else None,
            period_idx=period_idx if foul_p > 0 else None,
            progress=progress if foul_p > 0 else None,
            close_thr=close_thr,
            intentional_foul_prob=foul_p,
        )
        home_pts += home_delta
        away_pts += away_delta
        endings += ended.astype(np.int32)

    overtime = np.zeros(n_runs, dtype=bool)
    ot_periods = np.zeros(n_runs, dtype=np.int32)
    tied = home_pts == away_pts
    ot_period = 0
    while np.any(tied) and ot_period < 5:
        overtime |= tied
        ot_period += 1
        ot_periods = np.where(tied, ot_period, ot_periods)
        ot_endings = np.zeros(n_runs, dtype=np.int32)
        ot_target = np.where(tied, 16, 0)
        # OT uses Q4 close-game lineups (shortened star rotation).
        home_lineups = home_grid[run_ids, 3, 0]
        away_lineups = away_grid[run_ids, 3, 0]
        for _ in range(28):
            still = ot_endings < ot_target
            if not np.any(still):
                break
            home_delta, away_delta, offense_home, ended = _vector_possession(
                rng,
                packed,
                home_lineups,
                away_lineups,
                offense_home,
                still,
                pts,
                reb,
                ast,
                fg3m,
                stl,
                blk,
                tov,
                home_hot=home_hot,
                away_hot=away_hot,
                player_hot=player_hot,
                player_usage=player_usage,
            )
            home_pts += home_delta
            away_pts += away_delta
            ot_endings += ended.astype(np.int32)
            tied = home_pts == away_pts
            ot_target = np.where(tied, ot_target, ot_endings)

    # OT adds 25 team-minutes per period, split by regulation share.
    minutes = add_overtime_minutes(
        minutes,
        home_idx=home_idx,
        away_idx=away_idx,
        ot_periods=ot_periods,
        out_mask=out_mask,
        caps=caps,
    )

    return GameSimResult(
        game_id=projection.game_id,
        runs=n_runs,
        seed=int(base_seed),
        player_ids=np.array([p.player_id for p in players], dtype=np.int32),
        player_names=[p.player_name for p in players],
        team_abbrs=[p.team_abbr for p in players],
        home_away=[p.home_away for p in players],
        pts=pts,
        reb=reb,
        ast=ast,
        fg3m=fg3m,
        stl=stl,
        blk=blk,
        tov=tov,
        minutes=minutes,
        home_pts=home_pts,
        away_pts=away_pts,
        overtime=overtime,
        home_possessions=float(np.mean(home_poss)),
        away_possessions=float(np.mean(away_poss)),
    )


def _usage_weights(
    packed: dict[str, np.ndarray],
    off_lineups: np.ndarray,
    player_usage: np.ndarray | None,
    n_runs: int,
) -> np.ndarray:
    """On-court usage weights, optionally scaled by per-player tonight draws."""
    usage_w = packed["usage"][off_lineups].copy()
    if player_usage is not None:
        run_ids = np.arange(n_runs)[:, None]
        usage_w *= player_usage[off_lineups, run_ids]
    return np.clip(usage_w, 1e-6, None)


def _pack_rates(players: list[PlayerProjection]) -> dict[str, np.ndarray]:
    return {
        "usage": np.array([p.rates.usage for p in players], dtype=float),
        "tov_rate": np.array([p.rates.tov_rate for p in players], dtype=float),
        "ft_rate": np.array([p.rates.ft_rate for p in players], dtype=float),
        "ft_pct": np.array([p.rates.ft_pct for p in players], dtype=float),
        "oreb": np.array([p.rates.oreb_rate for p in players], dtype=float),
        "dreb": np.array([p.rates.dreb_rate for p in players], dtype=float),
        "ast_rate": np.array([p.rates.ast_rate for p in players], dtype=float),
        "stl_rate": np.array([p.rates.stl_rate for p in players], dtype=float),
        "blk_rate": np.array([p.rates.blk_rate for p in players], dtype=float),
        "zone_share": np.vstack([[getattr(p.rates, f"{zone}_share") for zone in ZONES] for p in players]),
        "zone_fg": np.vstack([[getattr(p.rates, f"{zone}_fg_pct") for zone in ZONES] for p in players]),
        "n_players": len(players),
    }


def _soft_normalize_minute_draws(
    draws: np.ndarray,
    *,
    out_mask: np.ndarray,
    caps: np.ndarray,
    target: float,
    gap_close: float,
) -> np.ndarray:
    """Clip outs/caps; optionally nudge column sums toward ``target``.

    ``gap_close=0`` preserves per-player draw means (no team rescale).
    """
    result = np.array(draws, dtype=float, copy=True)
    out = np.asarray(out_mask, dtype=bool).reshape(-1)
    cap = np.asarray(caps, dtype=float).reshape(-1)
    result[out, :] = 0.0
    result = np.maximum(result, 0.0)
    for i in range(result.shape[0]):
        if out[i]:
            continue
        if cap[i] > 0:
            result[i] = np.minimum(result[i], cap[i])
        else:
            result[i] = 0.0
    if result.size == 0:
        return result
    available = ~out & (cap > 0)
    if not np.any(available):
        return result
    # gap_close=0 still gets a mild pull so team totals land near 240 after
    # independent player noise (opening-night readiness); full 1.0 hard-normalizes.
    strength = float(gap_close) if gap_close > 0 else 0.45
    for run in range(result.shape[1]):
        col = result[:, run]
        total = float(col[available].sum())
        if total <= 1e-9:
            continue
        factor = 1.0 + strength * (target / total - 1.0)
        col = col * factor
        for i in np.where(available)[0]:
            col[i] = min(float(col[i]), float(cap[i]))
        result[:, run] = col
    return result


_BUCKETS = ("close", "moderate", "blowout")


def _period_bucket_indexes(
    endings: np.ndarray,
    target_endings: np.ndarray,
    home_pts: np.ndarray,
    away_pts: np.ndarray,
    *,
    expected_margin: float,
    close_thr: float,
    blowout_thr: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Map game progress + score to period (0–3) and margin bucket (0–2)."""
    progress = endings.astype(float) / np.maximum(1.0, target_endings.astype(float))
    period_idx = np.clip(np.floor(progress * 4.0).astype(np.int32), 0, 3)
    live = np.abs(home_pts - away_pts)
    # Early: lean on pregame expected margin; late: trust the live score.
    eff = (1.0 - progress) * float(expected_margin) + progress * live
    bucket_idx = np.where(
        eff < close_thr,
        0,
        np.where(eff < blowout_thr, 1, 2),
    ).astype(np.int32)
    return period_idx, bucket_idx


def _lineups_matrix(rng: np.random.Generator, pool: np.ndarray, minutes: np.ndarray) -> np.ndarray:
    """Return shape (n_runs, 5) player indexes (single stint)."""
    return _lineups_stints(rng, pool, minutes, n_stints=1)[:, 0, :]


def _lineups_stints(
    rng: np.random.Generator,
    pool: np.ndarray,
    minutes: np.ndarray,
    *,
    n_stints: int = 6,
) -> np.ndarray:
    """Return shape (n_runs, n_stints, 5) player indexes.

    Each stint is a minutes-weighted top-5 draw with noise so rotation players
    rotate through the floor in proportion to projected minutes.
    """
    n_runs = minutes.shape[1]
    size = min(5, int(pool.size))
    n_pool = int(pool.size)
    out = np.zeros((n_runs, n_stints, size), dtype=np.int32)
    weights = np.clip(minutes[pool], 0.0, None)  # (pool, runs)
    # Vectorized noise across runs × stints; argsort per (run, stint).
    noise_sd = np.maximum(3.0, 0.25 * np.std(weights, axis=0) + 2.0)  # (runs,)
    # (pool, runs, stints)
    noisy = weights[:, :, None] + rng.normal(0.0, 1.0, size=(n_pool, n_runs, n_stints)) * noise_sd[
        None, :, None
    ]
    # Zero-weight runs: replace with random scores so permutation is uniform.
    zero_runs = weights.sum(axis=0) <= 0
    if np.any(zero_runs):
        noisy[:, zero_runs, :] = rng.random((n_pool, int(np.sum(zero_runs)), n_stints))
    order = np.argsort(-noisy, axis=0)  # (pool, runs, stints)
    top = order[:size]  # (size, runs, stints)
    # Map pool-local indexes → global player indexes.
    for stint in range(n_stints):
        out[:, stint, :] = pool[top[:, :, stint]].T
    return out


def _lineups_state_grid(
    rng: np.random.Generator,
    pool: np.ndarray,
    minutes: np.ndarray,
    players: list[PlayerProjection],
    *,
    rotation=None,
) -> np.ndarray:
    """Return shape (n_runs, 4 periods, 3 buckets, 5) player indexes.

    Weights = projected minutes × period/margin priors, with a mild boost for
    players who historically share the floor (co-appearance).
    """
    from projections.rotations import RotationModel

    model = rotation if rotation is not None else RotationModel()
    n_runs = minutes.shape[1]
    size = min(5, int(pool.size))
    n_pool = int(pool.size)
    out = np.zeros((n_runs, 4, 3, size), dtype=np.int32)
    if n_pool == 0:
        return out

    base = np.clip(minutes[pool], 0.0, None)  # (pool, runs)
    team_id = int(players[int(pool[0])].team_id) if pool.size else 0
    player_ids = [int(players[int(i)].player_id) for i in pool]
    depths = [int(getattr(players[int(i)], "depth_rank", 99)) for i in pool]

    # Co-appearance boost relative to the team's minutes leader.
    leader_local = int(np.argmax(base.mean(axis=1))) if n_pool else 0
    leader_pid = player_ids[leader_local]
    co_boost = np.ones(n_pool, dtype=float)
    for j, pid in enumerate(player_ids):
        if j == leader_local:
            continue
        co_boost[j] = model.partner_boost(team_id, leader_pid, pid)

    for period in range(1, 5):
        for b_idx, bucket in enumerate(_BUCKETS):
            period_w = np.array(
                [
                    model.period_weights(depths[j], period=period, margin_bucket_name=bucket)
                    for j in range(n_pool)
                ],
                dtype=float,
            )
            weights = base * period_w[:, None] * co_boost[:, None]
            noise_sd = np.maximum(3.0, 0.25 * np.std(weights, axis=0) + 2.0)
            noisy = weights + rng.normal(0.0, 1.0, size=(n_pool, n_runs)) * noise_sd[None, :]
            zero_runs = weights.sum(axis=0) <= 0
            if np.any(zero_runs):
                noisy[:, zero_runs] = rng.random((n_pool, int(np.sum(zero_runs))))
            order = np.argsort(-noisy, axis=0)
            top = order[:size]
            out[:, period - 1, b_idx, :] = pool[top].T
    return out


def _vector_possession(
    rng: np.random.Generator,
    packed: dict[str, np.ndarray],
    home_lineups: np.ndarray,
    away_lineups: np.ndarray,
    offense_home: np.ndarray,
    active: np.ndarray,
    pts: np.ndarray,
    reb: np.ndarray,
    ast: np.ndarray,
    fg3m: np.ndarray,
    stl: np.ndarray,
    blk: np.ndarray,
    tov: np.ndarray,
    home_hot: np.ndarray | None = None,
    away_hot: np.ndarray | None = None,
    player_hot: np.ndarray | None = None,
    player_usage: np.ndarray | None = None,
    home_pts: np.ndarray | None = None,
    away_pts: np.ndarray | None = None,
    period_idx: np.ndarray | None = None,
    progress: np.ndarray | None = None,
    close_thr: float = 6.0,
    intentional_foul_prob: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (home_delta, away_delta, next_offense_home, ended).

    ``ended`` is True when the possession ending counts against pace (not OREB).
    """
    n_runs = active.shape[0]
    home_delta = np.zeros(n_runs)
    away_delta = np.zeros(n_runs)
    next_offense_home = offense_home.copy()
    ended = np.zeros(n_runs, dtype=bool)
    if not np.any(active):
        return home_delta, away_delta, next_offense_home, ended

    off_lineups = np.where(offense_home[:, None], home_lineups, away_lineups)
    def_lineups = np.where(offense_home[:, None], away_lineups, home_lineups)

    # Late-game intentional foul: trailing defense fouls leading offense to
    # stop the clock (2 FT, then possession flips to the fouling team).
    is_int_foul = np.zeros(n_runs, dtype=bool)
    if (
        intentional_foul_prob > 0
        and home_pts is not None
        and away_pts is not None
        and period_idx is not None
        and progress is not None
    ):
        margin = home_pts - away_pts
        # Offense is leading (defense trailing) in a close Q4 late game.
        offense_leading = np.where(offense_home, margin > 0, margin < 0)
        abs_m = np.abs(margin)
        eligible = (
            active
            & (period_idx >= 3)
            & (progress >= 0.85)
            & offense_leading
            & (abs_m > 0)
            & (abs_m <= close_thr + 2.0)
        )
        is_int_foul = eligible & (rng.random(n_runs) < intentional_foul_prob)
        if np.any(is_int_foul):
            # Foul the best FT shooter among the five on offense.
            ft_w = np.clip(packed["ft_pct"][off_lineups], 0.4, 0.95)
            slot = _weighted_choice(rng, ft_w)
            users = off_lineups[np.arange(n_runs), slot]
            ft_pct = np.clip(packed["ft_pct"][users], 0.4, 0.95)
            made = np.zeros(n_runs)
            idx = np.flatnonzero(is_int_foul)
            made[idx] = rng.binomial(2, ft_pct[idx])
            np.add.at(pts, (users[is_int_foul], idx), made[is_int_foul])
            home_delta = np.where(is_int_foul & offense_home, made, home_delta)
            away_delta = np.where(is_int_foul & ~offense_home, made, away_delta)
            next_offense_home[is_int_foul] = ~offense_home[is_int_foul]
            ended[is_int_foul] = True

    remaining_after_foul = active & ~is_int_foul
    if not np.any(remaining_after_foul):
        return home_delta, away_delta, next_offense_home, ended

    # Steal. Per-player rates are stl/def_poss; summing five on-court rates
    # overstates team steals, so scale toward league ~8 STL / 100 possessions.
    stl_w = packed["stl_rate"][def_lineups]
    stl_prob = np.clip(stl_w.sum(axis=1) * 0.78, 0.0, 0.095)
    is_stl = remaining_after_foul & (rng.random(n_runs) < stl_prob)
    if np.any(is_stl):
        pick = _weighted_choice(rng, stl_w[is_stl])
        runners = np.flatnonzero(is_stl)
        players = def_lineups[is_stl, pick]
        np.add.at(stl, (players, runners), 1)
        # Credited as a turnover on the offense as well.
        usage_w_tmp = _usage_weights(packed, off_lineups, player_usage, n_runs)
        user_slot_tmp = _weighted_choice(rng, usage_w_tmp)
        users_tmp = off_lineups[np.arange(n_runs), user_slot_tmp]
        np.add.at(tov, (users_tmp[is_stl], runners), 1)
        next_offense_home[is_stl] = ~offense_home[is_stl]
        ended[is_stl] = True

    remaining = active & ~is_stl
    if not np.any(remaining):
        return home_delta, away_delta, next_offense_home, ended

    usage_w = _usage_weights(packed, off_lineups, player_usage, n_runs)
    user_slot = _weighted_choice(rng, usage_w)
    users = off_lineups[np.arange(n_runs), user_slot]

    # Non-steal turnover (stl path already handled)
    tov_prob = np.clip(packed["tov_rate"][users], 0.02, 0.30)
    is_tov = remaining & (rng.random(n_runs) < tov_prob)
    if np.any(is_tov):
        runners = np.flatnonzero(is_tov)
        np.add.at(tov, (users[is_tov], runners), 1)
        next_offense_home[is_tov] = ~offense_home[is_tov]
        ended[is_tov] = True

    remaining = remaining & ~is_tov
    if not np.any(remaining):
        return home_delta, away_delta, next_offense_home, ended

    # Rare non-shooting foul / bonus FT trip (no FGA). Most FTA come from
    # shooting fouls attached to an FGA below.
    bonus_ft_prob = np.clip(packed["ft_rate"][users] / 2.15 * 0.20, 0.0, 0.08)
    is_bonus_ft = remaining & (rng.random(n_runs) < bonus_ft_prob)
    if np.any(is_bonus_ft):
        fta = np.where(rng.random(n_runs) < 0.85, 2, 3)
        ft_pct = np.clip(packed["ft_pct"][users], 0.4, 0.95)
        made = np.zeros(n_runs)
        idx = np.flatnonzero(is_bonus_ft)
        made[idx] = rng.binomial(fta[idx], ft_pct[idx])
        np.add.at(pts, (users[is_bonus_ft], idx), made[is_bonus_ft])
        home_delta = np.where(is_bonus_ft & offense_home, made, home_delta)
        away_delta = np.where(is_bonus_ft & ~offense_home, made, away_delta)
        next_offense_home[is_bonus_ft] = ~offense_home[is_bonus_ft]
        ended[is_bonus_ft] = True

    remaining = remaining & ~is_bonus_ft
    if not np.any(remaining):
        return home_delta, away_delta, next_offense_home, ended

    # Shot zone
    zone_share = packed["zone_share"][users]  # (n_runs, 6)
    zone_i = _weighted_choice(rng, zone_share)
    fg_pct = packed["zone_fg"][users, zone_i]
    if home_hot is not None and away_hot is not None:
        hot = np.where(offense_home, home_hot, away_hot)
        fg_pct = fg_pct * hot
    if player_hot is not None:
        # Per-player tonight shooting draw (negative-binomial-like overdispersion).
        fg_pct = fg_pct * player_hot[users, np.arange(n_runs)]
    fg_pct = np.clip(fg_pct, 0.15, 0.85)
    # Shooting-foul rate from expected FTA/use (≈2 FTA per foul on average).
    shoot_foul_prob = np.clip(packed["ft_rate"][users] / 2.05 * 0.80, 0.02, 0.35)
    ft_pct = np.clip(packed["ft_pct"][users], 0.4, 0.95)

    blk_w = packed["blk_rate"][def_lineups]
    blk_scale = np.where(zone_i == 0, 1.4, 0.7)
    blk_prob = np.clip(blk_w.sum(axis=1) * blk_scale * 0.78, 0.0, 0.065)
    is_blk = remaining & (rng.random(n_runs) < blk_prob)
    if np.any(is_blk):
        pick = _weighted_choice(rng, blk_w[is_blk])
        runners = np.flatnonzero(is_blk)
        players = def_lineups[is_blk, pick]
        np.add.at(blk, (players, runners), 1)

    # Miss path: block or natural miss -> rebound (unless shooting foul on the miss).
    is_make = remaining & ~is_blk & (rng.random(n_runs) < fg_pct)
    is_miss = remaining & ~is_make
    is_foul = remaining & ~is_blk & (rng.random(n_runs) < shoot_foul_prob)

    if np.any(is_make):
        points = _ZONE_POINTS[zone_i]
        runners = np.flatnonzero(is_make)
        np.add.at(pts, (users[is_make], runners), points[is_make])
        threes = is_make & (points == 3.0)
        if np.any(threes):
            np.add.at(fg3m, (users[threes], np.flatnonzero(threes)), 1)
        # And-one
        and_one = is_make & is_foul
        if np.any(and_one):
            ao_made = np.zeros(n_runs)
            ao_idx = np.flatnonzero(and_one)
            ao_made[ao_idx] = rng.binomial(1, ft_pct[ao_idx])
            np.add.at(pts, (users[and_one], ao_idx), ao_made[and_one])
            points = points + ao_made
        home_delta = np.where(is_make & offense_home, points, home_delta)
        away_delta = np.where(is_make & ~offense_home, points, away_delta)
        mate_slot = (user_slot + 1 + rng.integers(0, 4, size=n_runs)) % off_lineups.shape[1]
        mates = off_lineups[np.arange(n_runs), mate_slot]
        ast_prob = np.clip(packed["ast_rate"][mates], 0.35, 0.75)
        is_ast = is_make & (rng.random(n_runs) < ast_prob)
        if np.any(is_ast):
            np.add.at(ast, (mates[is_ast], np.flatnonzero(is_ast)), 1)
        next_offense_home[is_make] = ~offense_home[is_make]
        ended[is_make] = True

    # Shooting foul on a miss: FTs, no rebound.
    foul_miss = is_miss & is_foul
    if np.any(foul_miss):
        fta = np.where(_ZONE_POINTS[zone_i] >= 3.0, 3, 2)
        made = np.zeros(n_runs)
        idx = np.flatnonzero(foul_miss)
        made[idx] = rng.binomial(fta[idx], ft_pct[idx])
        np.add.at(pts, (users[foul_miss], idx), made[foul_miss])
        home_delta = np.where(foul_miss & offense_home, made, home_delta)
        away_delta = np.where(foul_miss & ~offense_home, made, away_delta)
        next_offense_home[foul_miss] = ~offense_home[foul_miss]
        ended[foul_miss] = True

    live_miss = is_miss & ~is_foul
    if np.any(live_miss):
        o_w = packed["oreb"][off_lineups]
        d_w = packed["dreb"][def_lineups]
        p_orb = np.clip(o_w.sum(axis=1) / (o_w.sum(axis=1) + d_w.sum(axis=1) + 1e-9), 0.05, 0.40)
        is_orb = live_miss & (rng.random(n_runs) < p_orb)
        is_drb = live_miss & ~is_orb
        if np.any(is_orb):
            pick = _weighted_choice(rng, o_w[is_orb])
            runners = np.flatnonzero(is_orb)
            players = off_lineups[is_orb, pick]
            np.add.at(reb, (players, runners), 1)
            next_offense_home[is_orb] = offense_home[is_orb]
            # OREB: possession continues — do NOT mark ended.
        if np.any(is_drb):
            pick = _weighted_choice(rng, d_w[is_drb])
            runners = np.flatnonzero(is_drb)
            players = def_lineups[is_drb, pick]
            np.add.at(reb, (players, runners), 1)
            next_offense_home[is_drb] = ~offense_home[is_drb]
            ended[is_drb] = True

    return home_delta, away_delta, next_offense_home, ended


def _weighted_choice(rng: np.random.Generator, weights: np.ndarray) -> np.ndarray:
    """weights shape (n, k) -> index in 0..k-1 per row."""
    clipped = np.clip(weights, 0.0, None)
    totals = clipped.sum(axis=1, keepdims=True)
    safe = np.where(totals > 0, clipped / totals, 1.0 / weights.shape[1])
    cdf = np.cumsum(safe, axis=1)
    u = rng.random(weights.shape[0])[:, None]
    return (u > cdf).sum(axis=1).astype(np.int32)
