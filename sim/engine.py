"""Possession-by-possession game simulation, vectorized across runs.

Raw per-run draws stay in memory only long enough to build summaries. Callers
in outputs/ reduce the arrays and discard them. Optionally record a single
run's possession log (``trace_run``) for the typical-game narrative.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nba_sim.schema import ZONES
from projections.build import GameProjection, PlayerProjection
from projections.minutes import add_overtime_minutes, normalize_team_minute_draws
from sim.possession_log import (
    OUTCOME_BONUS_FT,
    OUTCOME_DREB,
    OUTCOME_FOUL_FT,
    OUTCOME_INT_FOUL,
    OUTCOME_MAKE_2,
    OUTCOME_MAKE_3,
    OUTCOME_NAMES,
    OUTCOME_OREB,
    OUTCOME_STEAL,
    OUTCOME_TOV,
    PERIOD_SECONDS,
    REGULATION_SECONDS,
    PossessionEvent,
    PossessionLog,
)

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
    # Seconds remaining at end of regulation (0 if regulation finished).
    clock_remaining: np.ndarray | None = None
    # Points scored in each regulation period: shape (n_runs, 4).
    home_period_pts: np.ndarray | None = None
    away_period_pts: np.ndarray | None = None
    # Optional single-run possession narrative (typical-game hook).
    possession_log: PossessionLog | None = None


def simulate_game(
    projection: GameProjection,
    *,
    runs: int | None = None,
    seed: int | None = None,
    config: dict | None = None,
    trace_run: int | None = None,
) -> GameSimResult:
    """Simulate one game. Default runs/seed come from config.yaml when omitted.

    ``trace_run`` (0-based) records a compact possession log for that single run
    only. Re-run with the same seed and ``trace_run`` after picking the typical
    sim index so the log matches the Monte Carlo cloud.
    """
    cfg = config or {}
    sim_cfg = cfg.get("simulation", {})
    n_runs = int(runs if runs is not None else sim_cfg.get("runs", 10000))
    if n_runs <= 0:
        raise ValueError("runs must be positive")
    if trace_run is not None and not (0 <= int(trace_run) < n_runs):
        raise ValueError(f"trace_run must be in [0, {n_runs})")
    base_seed = seed if seed is not None else sim_cfg.get("seed")
    if base_seed is None:
        base_seed = int(np.random.SeedSequence().entropy) % (2**31 - 1)
    rng = np.random.default_rng(int(base_seed))
    trace_i = int(trace_run) if trace_run is not None else None

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
    # Always enforce exactly team_target per team in regulation. Soft/gap_close
    # paths let early-season naive means drift to ~259 and mid-season to ~225;
    # OT (+25/period) is applied later via add_overtime_minutes.
    out_mask = np.array([p.minutes.out for p in players], dtype=bool)
    caps = np.array(
        [0.0 if p.minutes.out else float(p.minutes.max_minutes) for p in players],
        dtype=float,
    )
    for pool in (home_idx, away_idx):
        minutes[pool] = normalize_team_minute_draws(
            minutes[pool],
            out_mask=out_mask[pool],
            caps=caps[pool],
            target=team_target,
            min_minutes=min_minutes,
        )

    packed = _pack_rates(players)
    packed["assist_matrix"] = _assist_matrix(
        players, getattr(projection, "assist_network", None) or {}
    )
    packed["def_fg_factor"] = _defender_factor_array(
        players, getattr(projection, "defender_fg_factor", None) or {}
    )
    packed["def_fg3_factor"] = _defender_factor_array(
        players, getattr(projection, "defender_fg3_factor", None) or {}
    )
    packed["position_code"] = _position_codes(players)
    guard_share = _guard_share_array(players)
    if np.any(np.isfinite(guard_share)):
        packed["guard_share"] = guard_share
    packed["defender_impact_weight"] = float(
        (cfg.get("context") or {}).get("defender_impact_weight", 0.55)
    )
    # Period × margin-bucket lineup grid (stint substitution model).
    # close games shorten rotations late; blowouts put the bench on the floor.
    # Pure naive minutes: keep lineups proportional to minute draws only —
    # period/margin starter boosts were putting stars on the floor more than
    # their box MIN share, inflating starter PTS/REB/AST role shares.
    minutes_cfg = cfg.get("minutes", {})
    close_thr = float(minutes_cfg.get("close_margin_threshold", 6.0))
    blowout_thr = float(minutes_cfg.get("blowout_margin_threshold", 15.0))
    expected_margin = float(getattr(projection, "expected_abs_margin", 8.0) or 8.0)
    rotation = getattr(projection, "rotation", None)
    minutes_model = str(
        (cfg.get("features") or {}).get("minutes_model", "engine")
    ).lower()
    flat_lineups = minutes_model in {"naive_last10", "naive"}
    home_grid = _lineups_state_grid(
        rng,
        home_idx,
        minutes,
        players,
        rotation=None if flat_lineups else rotation,
        flat=flat_lineups,
    )
    away_grid = _lineups_state_grid(
        rng,
        away_idx,
        minutes,
        players,
        rotation=None if flat_lineups else rotation,
        flat=flat_lineups,
    )

    sim_cfg = cfg.get("simulation", {})
    packed["assist_p_scale"] = float(sim_cfg.get("assist_p_scale", 1.0))
    # Live misses with no player credit (team rebound). Keeps possession flip.
    packed["team_reb_rate"] = float(np.clip(sim_cfg.get("team_reb_rate", 0.073), 0.0, 0.20))
    packed["reb_share_power"] = float(np.clip(sim_cfg.get("reb_share_power", 1.0), 0.5, 3.0))
    # Fraction of who-gets-steal weight from raw stl_rate (rest = on-court mean).
    packed["stl_credit_raw_weight"] = float(
        np.clip(sim_cfg.get("stl_credit_raw_weight", 1.0), 0.0, 1.0)
    )
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
    # Symmetric clips around 1.0. Cap scales with configured SD so widening
    # player_shoot_sd / player_usage_sd actually widens the draw (hard 0.28/0.30
    # ceilings previously blocked coverage from reaching ~80%).
    shoot_cap = float(np.clip(1.5 * player_shoot_sd, 0.18, 0.60))
    usage_cap = float(np.clip(1.5 * player_usage_sd, 0.18, 0.60))
    player_hot = np.clip(
        rng.normal(1.0, player_shoot_sd, size=(n_players, n_runs)),
        1.0 - shoot_cap,
        1.0 + shoot_cap,
    )
    player_usage = np.clip(
        rng.normal(1.0, player_usage_sd, size=(n_players, n_runs)),
        1.0 - usage_cap,
        1.0 + usage_cap,
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
    # Game clock (seconds remaining in regulation). Advances with possession
    # endings so period boundaries match 12-minute quarters. Deterministic from
    # pace progress — no extra RNG — so box-score distributions stay stable.
    clock_remaining = np.full(n_runs, REGULATION_SECONDS, dtype=float)
    home_period_pts = np.zeros((n_runs, 4), dtype=float)
    away_period_pts = np.zeros((n_runs, 4), dtype=float)
    last_period_idx = np.zeros(n_runs, dtype=np.int32)
    period_home_start = np.zeros(n_runs, dtype=float)
    period_away_start = np.zeros(n_runs, dtype=float)
    possession_events: list[PossessionEvent] = []
    player_id_arr = np.array([p.player_id for p in players], dtype=np.int32)

    offense_home = rng.random(n_runs) < 0.5
    endings = np.zeros(n_runs, dtype=np.int32)
    # Allow extra iterations for OREB retries (typical OREB rate ~25% of misses).
    max_iters = int(base_target.max() * 1.55) + 20
    run_ids = np.arange(n_runs)
    for _ in range(max_iters):
        active = endings < target_endings
        if not np.any(active):
            break
        progress = endings.astype(float) / np.maximum(1.0, base_target.astype(float))
        clock_remaining = REGULATION_SECONDS * (1.0 - np.clip(progress, 0.0, 1.0))
        period_idx, bucket_idx = _period_bucket_indexes(
            clock_remaining,
            home_pts,
            away_pts,
            progress=progress,
            expected_margin=expected_margin,
            close_thr=close_thr,
            blowout_thr=blowout_thr,
        )
        # Snapshot points when a run rolls into a new quarter.
        rolled = active & (period_idx > last_period_idx)
        if np.any(rolled):
            for p in range(4):
                just_left = rolled & (last_period_idx == p)
                if not np.any(just_left):
                    continue
                home_period_pts[just_left, p] = (
                    home_pts[just_left] - period_home_start[just_left]
                )
                away_period_pts[just_left, p] = (
                    away_pts[just_left] - period_away_start[just_left]
                )
            period_home_start = np.where(rolled, home_pts, period_home_start)
            period_away_start = np.where(rolled, away_pts, period_away_start)
            last_period_idx = np.where(rolled, period_idx, last_period_idx)
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
        want_trace = trace_i is not None and bool(active[trace_i])
        offense_before = offense_home.copy() if want_trace else None
        home_delta, away_delta, offense_home, ended, trace = _vector_possession(
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
            fill_trace=want_trace,
        )
        if (
            want_trace
            and trace is not None
            and trace_i is not None
            and offense_before is not None
        ):
            event = _event_from_trace(
                trace,
                trace_i,
                period=int(period_idx[trace_i]) + 1,
                clock_remaining=float(clock_remaining[trace_i]),
                offense_home=bool(offense_before[trace_i]),
                home_abbr=projection.home_abbr,
                away_abbr=projection.away_abbr,
                player_ids=player_id_arr,
                player_names=[p.player_name for p in players],
                home_lineup=home_lineups[trace_i],
                away_lineup=away_lineups[trace_i],
                home_pts=int(round(float(home_pts[trace_i] + home_delta[trace_i]))),
                away_pts=int(round(float(away_pts[trace_i] + away_delta[trace_i]))),
            )
            if event is not None:
                possession_events.append(event)
        home_pts += home_delta
        away_pts += away_delta
        endings += ended.astype(np.int32)

    # Close out the final regulation period scores for runs that finished.
    for p in range(4):
        in_period = last_period_idx == p
        if not np.any(in_period):
            continue
        home_period_pts[in_period, p] = home_pts[in_period] - period_home_start[in_period]
        away_period_pts[in_period, p] = away_pts[in_period] - period_away_start[in_period]
    clock_remaining = np.maximum(0.0, clock_remaining)

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
            want_trace = trace_i is not None and bool(still[trace_i])
            offense_before = offense_home.copy() if want_trace else None
            home_delta, away_delta, offense_home, ended, trace = _vector_possession(
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
                fill_trace=want_trace,
            )
            if (
                want_trace
                and trace is not None
                and trace_i is not None
                and offense_before is not None
            ):
                ot_progress = ot_endings.astype(float) / np.maximum(
                    1.0, ot_target.astype(float)
                )
                event = _event_from_trace(
                    trace,
                    trace_i,
                    period=4 + ot_period,
                    clock_remaining=float(
                        300.0 * (1.0 - float(ot_progress[trace_i]))
                    ),
                    offense_home=bool(offense_before[trace_i]),
                    home_abbr=projection.home_abbr,
                    away_abbr=projection.away_abbr,
                    player_ids=player_id_arr,
                    player_names=[p.player_name for p in players],
                    home_lineup=home_lineups[trace_i],
                    away_lineup=away_lineups[trace_i],
                    home_pts=int(round(float(home_pts[trace_i] + home_delta[trace_i]))),
                    away_pts=int(round(float(away_pts[trace_i] + away_delta[trace_i]))),
                )
                if event is not None:
                    possession_events.append(event)
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

    possession_log = None
    if trace_i is not None:
        possession_log = PossessionLog(
            game_id=projection.game_id,
            run_index=trace_i,
            home_abbr=projection.home_abbr,
            away_abbr=projection.away_abbr,
            events=possession_events,
            home_period_pts=[
                int(round(float(home_period_pts[trace_i, p]))) for p in range(4)
            ],
            away_period_pts=[
                int(round(float(away_period_pts[trace_i, p]))) for p in range(4)
            ],
            final_home_pts=int(round(float(home_pts[trace_i]))),
            final_away_pts=int(round(float(away_pts[trace_i]))),
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
        clock_remaining=clock_remaining,
        home_period_pts=home_period_pts,
        away_period_pts=away_period_pts,
        possession_log=possession_log,
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


def _assist_matrix(
    players: list[PlayerProjection],
    network: dict[int, dict[int, float]],
) -> np.ndarray:
    """Shape (n_players, n_players): matrix[passer_idx, shooter_idx] = assists."""
    n = len(players)
    mat = np.zeros((n, n), dtype=float)
    if not network:
        return mat
    index = {int(p.player_id): i for i, p in enumerate(players)}
    for shooter_pid, edges in network.items():
        s_idx = index.get(int(shooter_pid))
        if s_idx is None:
            continue
        for passer_pid, weight in edges.items():
            p_idx = index.get(int(passer_pid))
            if p_idx is None or p_idx == s_idx:
                continue
            mat[p_idx, s_idx] += float(weight)
    return mat


_POS_CODE = {"PG": 0, "SG": 1, "SF": 2, "PF": 3, "C": 4}


def _position_codes(players: list[PlayerProjection]) -> np.ndarray:
    codes = np.full(len(players), -1, dtype=np.int8)
    for i, player in enumerate(players):
        raw = (player.position or "").upper().strip()
        if raw in _POS_CODE:
            codes[i] = _POS_CODE[raw]
        elif raw in {"G", "GUARD"}:
            codes[i] = 1
        elif raw in {"F", "FORWARD"}:
            codes[i] = 2
        elif raw in {"C-F", "F-C"}:
            codes[i] = 3
        elif raw in {"G-F", "F-G"}:
            codes[i] = 2
    return codes


def _defender_factor_array(
    players: list[PlayerProjection],
    factors: dict[int, float],
) -> np.ndarray:
    out = np.ones(len(players), dtype=float)
    for i, player in enumerate(players):
        out[i] = float(factors.get(int(player.player_id), 1.0))
    return out


def _guard_share_array(players: list[PlayerProjection]) -> np.ndarray:
    """Minutes spent guarding PG, SG, SF, PF, C. NaN when the player has no row."""
    out = np.full((len(players), 5), np.nan, dtype=float)
    for index, player in enumerate(players):
        share = getattr(player, "guard_share", None)
        if not share or len(share) != 5:
            continue
        out[index] = [float(value) for value in share]
    return out


def _primary_defender_slots(
    rng: np.random.Generator,
    *,
    off_lineups: np.ndarray,
    def_lineups: np.ndarray,
    user_slot: np.ndarray,
    position_code: np.ndarray,
    remaining: np.ndarray,
    guard_share: np.ndarray | None = None,
) -> np.ndarray:
    """Pick a primary defender slot (0-4) for each active run."""
    n_runs = off_lineups.shape[0]
    out = np.zeros(n_runs, dtype=np.int32)
    if not np.any(remaining):
        return out
    shooters = off_lineups[np.arange(n_runs), user_slot]
    off_pos = position_code[shooters]
    def_pos = position_code[def_lineups]  # (n_runs, 5)
    # Affinity: same pos=1.0, adjacent=0.55, else=0.20; unknown=0.35
    weights = np.full((n_runs, 5), 0.35, dtype=float)
    known = (off_pos >= 0)[:, None] & (def_pos >= 0)
    same = known & (def_pos == off_pos[:, None])
    adj = known & (np.abs(def_pos.astype(int) - off_pos[:, None].astype(int)) == 1)
    weights = np.where(same, 1.0, weights)
    weights = np.where(adj & ~same, 0.55, weights)
    weights = np.where(known & ~same & ~adj, 0.20, weights)
    if guard_share is not None:
        weights = _blend_guard_share(weights, off_pos, def_lineups, guard_share)
    # Only sample for remaining runs; others stay 0.
    picks = _weighted_choice(rng, weights)
    out = np.where(remaining, picks, out)
    return out


def _blend_guard_share(
    affinity: np.ndarray,
    off_pos: np.ndarray,
    def_lineups: np.ndarray,
    guard_share: np.ndarray,
) -> np.ndarray:
    """Blend position affinity with how often each defender actually guards that spot.

    ``guard_share`` is (n_players, 5) in PG–C order. Missing rows stay on affinity.
    """
    known_pos = off_pos >= 0
    pos = np.clip(off_pos, 0, 4)
    shares = guard_share[def_lineups, pos[:, None]]
    finite = np.isfinite(shares)
    row_has = known_pos & finite.any(axis=1)
    if not np.any(row_has):
        return affinity
    raw = np.where(finite, np.maximum(shares, 0.0), 0.0)
    row_sum = raw.sum(axis=1, keepdims=True)
    share_w = raw / np.maximum(row_sum, 1e-9)
    aff_sum = affinity.sum(axis=1, keepdims=True)
    aff_w = affinity / np.maximum(aff_sum, 1e-9)
    # The observed matchup is the main weight. Affinity covers players with no row.
    blended = 0.35 * aff_w + 0.65 * share_w
    return np.where(row_has[:, None], blended, affinity)


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
    if gap_close <= 0 or result.size == 0:
        return result
    available = ~out & (cap > 0)
    if not np.any(available):
        return result
    for run in range(result.shape[1]):
        col = result[:, run]
        total = float(col[available].sum())
        if total <= 1e-9:
            continue
        factor = 1.0 + float(gap_close) * (target / total - 1.0)
        col = col * factor
        for i in np.where(available)[0]:
            col[i] = min(float(col[i]), float(cap[i]))
        result[:, run] = col
    return result


_BUCKETS = ("close", "moderate", "blowout")


def _period_bucket_indexes(
    clock_remaining: np.ndarray,
    home_pts: np.ndarray,
    away_pts: np.ndarray,
    *,
    progress: np.ndarray,
    expected_margin: float,
    close_thr: float,
    blowout_thr: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Map game clock + score to period (0–3) and margin bucket (0–2).

    Period comes from seconds remaining (12-minute quarters). Margin bucket
    still blends pregame expected margin early with the live score late.
    """
    elapsed = np.clip(REGULATION_SECONDS - clock_remaining, 0.0, REGULATION_SECONDS)
    period_idx = np.clip((elapsed / PERIOD_SECONDS).astype(np.int32), 0, 3)
    live = np.abs(home_pts - away_pts)
    # Early: lean on pregame expected margin; late: trust the live score.
    prog = np.clip(progress.astype(float), 0.0, 1.0)
    eff = (1.0 - prog) * float(expected_margin) + prog * live
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
    flat: bool = False,
) -> np.ndarray:
    """Return shape (n_runs, 4 periods, 3 buckets, 5) player indexes.

    Weights = projected minutes × period/margin priors, with a mild boost for
    players who historically share the floor (co-appearance).

    ``flat=True`` (naive minutes path): ignore period/margin/co-appearance so
    on-court share tracks box-score minute draws.
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
    if not flat:
        for j, pid in enumerate(player_ids):
            if j == leader_local:
                continue
            co_boost[j] = model.partner_boost(team_id, leader_pid, pid)

    for period in range(1, 5):
        for b_idx, bucket in enumerate(_BUCKETS):
            if flat:
                period_w = np.ones(n_pool, dtype=float)
            else:
                period_w = np.array(
                    [
                        model.period_weights(
                            depths[j], period=period, margin_bucket_name=bucket
                        )
                        for j in range(n_pool)
                    ],
                    dtype=float,
                )
            weights = base * period_w[:, None] * co_boost[:, None]
            if flat:
                # Gumbel-top-k ≈ sample without replacement with probs ∝ minutes.
                # Temperature scales how often 12–18 MPG bench cracks the five.
                # temp≈1 → near hard top-5; temp≈3 → heavy bench rotation.
                # 1.35 keeps starter role shares near actual; elite REB/36 is
                # restored via reb_share_power on who-gets-it (not colder lineups).
                temperature = 1.35
                logits = np.log(np.maximum(weights, 1e-6)) / temperature
                gumbel = rng.gumbel(size=weights.shape)
                noisy = logits + gumbel
            else:
                noise_sd = np.maximum(3.0, 0.25 * np.std(weights, axis=0) + 2.0)
                noisy = weights + rng.normal(0.0, 1.0, size=(n_pool, n_runs)) * noise_sd[
                    None, :
                ]
            zero_runs = weights.sum(axis=0) <= 0
            if np.any(zero_runs):
                noisy[:, zero_runs] = rng.random((n_pool, int(np.sum(zero_runs))))
            order = np.argsort(-noisy, axis=0)
            top = order[:size]
            out[:, period - 1, b_idx, :] = pool[top].T
    return out


def _empty_trace(n_runs: int) -> dict[str, np.ndarray]:
    """Extra columns are filled only for the traced run. No RNG lives here."""
    return {
        "kind": np.zeros(n_runs, dtype=np.int8),
        "shooter": np.full(n_runs, -1, dtype=np.int32),
        "passer": np.full(n_runs, -1, dtype=np.int32),
        "points": np.zeros(n_runs, dtype=np.float32),
        "zone": np.full(n_runs, -1, dtype=np.int8),
        "shot_made": np.full(n_runs, -1, dtype=np.int8),
        "fta": np.zeros(n_runs, dtype=np.int8),
        "ftm": np.zeros(n_runs, dtype=np.int8),
        "rebounder": np.full(n_runs, -1, dtype=np.int32),
        "reb_side": np.zeros(n_runs, dtype=np.int8),
        "stealer": np.full(n_runs, -1, dtype=np.int32),
        "turnover": np.full(n_runs, -1, dtype=np.int32),
    }


def _game_clock(period: int, clock_remaining: float) -> str:
    """Clock left in the current period, ``M:SS``."""
    if period <= 4:
        remain = float(clock_remaining) - (4 - period) * PERIOD_SECONDS
    else:
        remain = float(clock_remaining)
    remain = max(0, int(round(remain)))
    return f"{remain // 60}:{remain % 60:02d}"


def _id_name(
    index: int,
    player_ids: np.ndarray,
    player_names: list[str],
) -> tuple[int | None, str | None]:
    if index < 0:
        return None, None
    return int(player_ids[index]), player_names[index]


def _lineup_ids(slots: np.ndarray, player_ids: np.ndarray) -> list[int]:
    return [int(player_ids[int(slot)]) for slot in slots]


def _event_from_trace(
    trace: dict[str, np.ndarray],
    run_index: int,
    *,
    period: int,
    clock_remaining: float,
    offense_home: bool,
    home_abbr: str,
    away_abbr: str,
    player_ids: np.ndarray,
    player_names: list[str],
    home_lineup: np.ndarray,
    away_lineup: np.ndarray,
    home_pts: int,
    away_pts: int,
) -> PossessionEvent | None:
    """Build one possession record from the traced row. Does not touch RNG."""
    kind = int(trace["kind"][run_index])
    if kind == 0:
        return None
    shooter_i = int(trace["shooter"][run_index])
    passer_i = int(trace["passer"][run_index])
    rebounder_i = int(trace["rebounder"][run_index])
    stealer_i = int(trace["stealer"][run_index])
    turnover_i = int(trace["turnover"][run_index])
    shooter_id, shooter_name = _id_name(shooter_i, player_ids, player_names)
    passer_id, passer_name = _id_name(passer_i, player_ids, player_names)
    rebounder_id, rebounder_name = _id_name(rebounder_i, player_ids, player_names)
    stealer_id, stealer_name = _id_name(stealer_i, player_ids, player_names)
    turnover_id, turnover_name = _id_name(turnover_i, player_ids, player_names)
    zone_i = int(trace["zone"][run_index])
    shot_zone = ZONES[zone_i] if 0 <= zone_i < len(ZONES) else None
    made_code = int(trace["shot_made"][run_index])
    shot_made = None if made_code < 0 else bool(made_code)
    shot_value = None
    if shot_zone is not None:
        shot_value = 3 if float(_ZONE_POINTS[zone_i]) >= 2.5 else 2
    reb_code = int(trace["reb_side"][run_index])
    rebound = {1: "off", 2: "def"}.get(reb_code)
    return PossessionEvent(
        period=period,
        clock_remaining=clock_remaining,
        offense_home=offense_home,
        outcome=OUTCOME_NAMES.get(kind, "unknown"),
        shooter_id=shooter_id,
        passer_id=passer_id,
        points=int(round(float(trace["points"][run_index]))),
        home_pts=home_pts,
        away_pts=away_pts,
        game_clock=_game_clock(period, clock_remaining),
        shooter_name=shooter_name,
        passer_name=passer_name,
        offense_abbr=home_abbr if offense_home else away_abbr,
        shot_zone=shot_zone,
        shot_value=shot_value,
        shot_made=shot_made,
        fta=int(trace["fta"][run_index]),
        ftm=int(trace["ftm"][run_index]),
        rebounder_id=rebounder_id,
        rebounder_name=rebounder_name,
        rebound=rebound,
        stealer_id=stealer_id,
        stealer_name=stealer_name,
        turnover_id=turnover_id,
        turnover_name=turnover_name,
        home_lineup=_lineup_ids(home_lineup, player_ids),
        away_lineup=_lineup_ids(away_lineup, player_ids),
    )


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
    fill_trace: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, np.ndarray] | None]:
    """Return (home_delta, away_delta, next_offense_home, ended, trace).

    ``ended`` is True when the possession ending counts against pace (not OREB).
    ``trace`` is filled only when ``fill_trace`` is True (single-run logging).
    """
    n_runs = active.shape[0]
    home_delta = np.zeros(n_runs)
    away_delta = np.zeros(n_runs)
    next_offense_home = offense_home.copy()
    ended = np.zeros(n_runs, dtype=bool)
    trace = _empty_trace(n_runs) if fill_trace else None
    if not np.any(active):
        return home_delta, away_delta, next_offense_home, ended, trace

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
            if trace is not None:
                trace["kind"][is_int_foul] = OUTCOME_INT_FOUL
                trace["shooter"][is_int_foul] = users[is_int_foul]
                trace["points"][is_int_foul] = made[is_int_foul]
                trace["fta"][is_int_foul] = 2
                trace["ftm"][is_int_foul] = made[is_int_foul]

    remaining_after_foul = active & ~is_int_foul
    if not np.any(remaining_after_foul):
        return home_delta, away_delta, next_offense_home, ended, trace

    # Steal. Per-player rates are stl/def_poss; summing five on-court rates
    # Scale on-court steal-rate sum toward league ~8.4 STL / 100 possessions.
    # P(steal) from raw rates; who-gets-it blends raw with on-court mean so
    # high-rate bench specialists do not soak starter STL share (team STL fixed).
    stl_w = packed["stl_rate"][def_lineups]
    stl_prob = np.clip(stl_w.sum(axis=1) * 0.88, 0.0, 0.100)
    is_stl = remaining_after_foul & (rng.random(n_runs) < stl_prob)
    if np.any(is_stl):
        raw_w = np.maximum(stl_w[is_stl], 1e-8)
        mean_w = raw_w.mean(axis=1, keepdims=True)
        raw_frac = float(packed.get("stl_credit_raw_weight", 1.0))
        credit_w = raw_frac * raw_w + (1.0 - raw_frac) * mean_w
        pick = _weighted_choice(rng, credit_w)
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
        if trace is not None:
            trace["kind"][is_stl] = OUTCOME_STEAL
            trace["shooter"][is_stl] = users_tmp[is_stl]
            trace["turnover"][is_stl] = users_tmp[is_stl]
            trace["stealer"][is_stl] = players

    remaining = active & ~is_stl & ~is_int_foul
    if not np.any(remaining):
        return home_delta, away_delta, next_offense_home, ended, trace

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
        if trace is not None:
            trace["kind"][is_tov] = OUTCOME_TOV
            trace["shooter"][is_tov] = users[is_tov]
            trace["turnover"][is_tov] = users[is_tov]

    remaining = remaining & ~is_tov
    if not np.any(remaining):
        return home_delta, away_delta, next_offense_home, ended, trace

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
        if trace is not None:
            trace["kind"][is_bonus_ft] = OUTCOME_BONUS_FT
            trace["shooter"][is_bonus_ft] = users[is_bonus_ft]
            trace["points"][is_bonus_ft] = made[is_bonus_ft]
            trace["fta"][is_bonus_ft] = fta[is_bonus_ft]
            trace["ftm"][is_bonus_ft] = made[is_bonus_ft]

    remaining = remaining & ~is_bonus_ft
    if not np.any(remaining):
        return home_delta, away_delta, next_offense_home, ended, trace

    # Shot zone
    zone_share = packed["zone_share"][users]  # (n_runs, 6)
    zone_i = _weighted_choice(rng, zone_share)
    fg_pct = packed["zone_fg"][users, zone_i]
    # Primary defender (position/minutes affinity) adjusts make% by zone family.
    if "def_fg_factor" in packed and "position_code" in packed:
        def_slots = _primary_defender_slots(
            rng,
            off_lineups=off_lineups,
            def_lineups=def_lineups,
            user_slot=user_slot,
            position_code=packed["position_code"],
            remaining=remaining,
            guard_share=packed.get("guard_share"),
        )
        defenders = def_lineups[np.arange(n_runs), def_slots]
        is_three = zone_i >= 3
        def_factor = np.where(
            is_three,
            packed["def_fg3_factor"][defenders],
            packed["def_fg_factor"][defenders],
        )
        weight = float(packed.get("defender_impact_weight", 0.55))
        # Blend toward 1.0 so matchup defense is a soft overlay on team defense.
        def_factor = 1.0 + weight * (def_factor - 1.0)
        fg_pct = fg_pct * def_factor
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
    # RA shots are blocked more often; keep team BLK near ~4.9 / game.
    blk_scale = np.where(zone_i == 0, 1.45, 0.88)
    blk_prob = np.clip(blk_w.sum(axis=1) * blk_scale, 0.0, 0.085)
    is_blk = remaining & (rng.random(n_runs) < blk_prob)
    if np.any(is_blk):
        # Soften who-gets-block: blend rates with on-court mean so starter BLK
        # share stays near actual (±3%) while team BLK totals stay put.
        raw_w = np.maximum(blk_w[is_blk], 1e-8)
        mean_w = raw_w.mean(axis=1, keepdims=True)
        credit_w = 0.35 * raw_w + 0.65 * mean_w
        pick = _weighted_choice(rng, credit_w)
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
        # Assists: ast_rate = historical AST / teammate FGM while on court.
        # On a make, P(assisted) ≈ sum of on-court non-shooter rates; the passer
        # is drawn weighted by those rates (not a uniform random teammate).
        passer_idx = _credit_assists(
            rng,
            is_make=is_make,
            off_lineups=off_lineups,
            user_slot=user_slot,
            packed=packed,
            ast=ast,
        )
        next_offense_home[is_make] = ~offense_home[is_make]
        ended[is_make] = True
        if trace is not None:
            # points may include and-one; zone points decide 2 vs 3 label.
            zone_pts = _ZONE_POINTS[zone_i]
            trace["kind"][is_make & (zone_pts < 2.5)] = OUTCOME_MAKE_2
            trace["kind"][is_make & (zone_pts >= 2.5)] = OUTCOME_MAKE_3
            trace["shooter"][is_make] = users[is_make]
            trace["points"][is_make] = points[is_make]
            trace["zone"][is_make] = zone_i[is_make]
            trace["shot_made"][is_make] = 1
            if np.any(and_one):
                trace["fta"][and_one] = 1
                trace["ftm"][and_one] = ao_made[and_one]
            if passer_idx is not None:
                assisted = passer_idx >= 0
                trace["passer"][assisted] = passer_idx[assisted]

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
        if trace is not None:
            trace["kind"][foul_miss] = OUTCOME_FOUL_FT
            trace["shooter"][foul_miss] = users[foul_miss]
            trace["points"][foul_miss] = made[foul_miss]
            trace["zone"][foul_miss] = zone_i[foul_miss]
            trace["shot_made"][foul_miss] = 0
            trace["fta"][foul_miss] = fta[foul_miss]
            trace["ftm"][foul_miss] = made[foul_miss]

    live_miss = is_miss & ~is_foul
    if np.any(live_miss):
        o_raw = packed["oreb"][off_lineups]
        d_raw = packed["dreb"][def_lineups]
        # ORB% from raw rates (team total). Who-gets-it uses powered weights so
        # elite rebounders keep historical share of player boards.
        p_orb = np.clip(
            o_raw.sum(axis=1) / (o_raw.sum(axis=1) + d_raw.sum(axis=1) + 1e-9),
            0.05,
            0.40,
        )
        power = float(packed.get("reb_share_power", 1.0))
        o_w = np.power(np.maximum(o_raw, 0.0), power)
        d_w = np.power(np.maximum(d_raw, 0.0), power)
        is_orb = live_miss & (rng.random(n_runs) < p_orb)
        is_drb = live_miss & ~is_orb
        if trace is not None:
            trace["zone"][live_miss] = zone_i[live_miss]
            trace["shot_made"][live_miss] = 0
            trace["reb_side"][is_orb] = 1
            trace["reb_side"][is_drb] = 2
        # Team rebounds: possession flips/continues like a player board, but no
        # box-score credit. Matches ~7% of misses that never land on a player.
        team_reb_rate = float(packed.get("team_reb_rate", 0.073))
        is_team_reb = live_miss & (rng.random(n_runs) < team_reb_rate)
        credit_orb = is_orb & ~is_team_reb
        credit_drb = is_drb & ~is_team_reb
        if np.any(credit_orb):
            pick = _weighted_choice(rng, o_w[credit_orb])
            runners = np.flatnonzero(credit_orb)
            players = off_lineups[credit_orb, pick]
            np.add.at(reb, (players, runners), 1)
            if trace is not None:
                trace["rebounder"][credit_orb] = players
        if np.any(is_orb):
            next_offense_home[is_orb] = offense_home[is_orb]
            # OREB: possession continues — do NOT mark ended.
            if trace is not None:
                trace["kind"][is_orb] = OUTCOME_OREB
                trace["shooter"][is_orb] = users[is_orb]
        if np.any(credit_drb):
            pick = _weighted_choice(rng, d_w[credit_drb])
            runners = np.flatnonzero(credit_drb)
            players = def_lineups[credit_drb, pick]
            np.add.at(reb, (players, runners), 1)
            if trace is not None:
                trace["rebounder"][credit_drb] = players
        if np.any(is_drb):
            next_offense_home[is_drb] = ~offense_home[is_drb]
            ended[is_drb] = True
            if trace is not None:
                trace["kind"][is_drb] = OUTCOME_DREB
                trace["shooter"][is_drb] = users[is_drb]

    return home_delta, away_delta, next_offense_home, ended, trace


def _credit_assists(
    rng: np.random.Generator,
    *,
    is_make: np.ndarray,
    off_lineups: np.ndarray,
    user_slot: np.ndarray,
    packed: dict[str, np.ndarray],
    ast: np.ndarray,
) -> np.ndarray | None:
    """Credit the passer on assisted makes.

    Prefer the passer→shooter assist network when available for the shooter;
    otherwise fall back to on-court ``ast_rate`` weights. P(assisted) still
    uses the scaled sum of on-court non-shooter rates so team AST level stays
    calibrated.

    Returns per-run passer player-index (-1 if none).
    """
    n_runs = off_lineups.shape[0]
    passer_idx = np.full(n_runs, -1, dtype=np.int32)
    if not np.any(is_make):
        return passer_idx
    # Baseline: on-court ast_rate (historical AST / teammate FGM).
    rates = packed["ast_rate"][off_lineups].copy()
    rates[np.arange(n_runs), user_slot] = 0.0
    # Prefer passer→shooter network weights when the matrix has mass for the
    # on-court passer against this shooter.
    matrix = packed.get("assist_matrix")
    if matrix is not None and np.any(matrix):
        shooters = off_lineups[np.arange(n_runs), user_slot]
        # network_w[run, slot] = matrix[lineup_player, shooter]
        network_w = matrix[off_lineups, shooters[:, None]]
        network_w[np.arange(n_runs), user_slot] = 0.0
        net_sum = network_w.sum(axis=1, keepdims=True)
        has_net = net_sum[:, 0] > 0
        # Scale network to the same total mass as ast_rate, then soft-blend so
        # creators keep volume while who→whom edges reshape the passer.
        rate_sum = rates.sum(axis=1, keepdims=True)
        scaled = np.where(
            net_sum > 0,
            network_w * (rate_sum / np.maximum(net_sum, 1e-9)),
            rates,
        )
        alpha = 0.35
        blended = (1.0 - alpha) * rates + alpha * scaled
        rates = np.where(has_net[:, None], blended, rates)
    # P(assisted) from ast_rate sums so team AST volume stays calibrated.
    p_rates = packed["ast_rate"][off_lineups].copy()
    p_rates[np.arange(n_runs), user_slot] = 0.0
    p_totals = p_rates[is_make].sum(axis=1)
    scale = float(packed.get("assist_p_scale", 1.0))
    make_idx = np.flatnonzero(is_make)
    do_ast = rng.random(make_idx.shape[0]) < np.clip(p_totals * scale, 0.0, 1.0)
    if not np.any(do_ast):
        return passer_idx
    pick = _weighted_choice(rng, rates[is_make][do_ast])
    runners = make_idx[do_ast]
    players = off_lineups[runners, pick]
    np.add.at(ast, (players, runners), 1)
    passer_idx[runners] = players
    return passer_idx


def _weighted_choice(rng: np.random.Generator, weights: np.ndarray) -> np.ndarray:
    """weights shape (n, k) -> index in 0..k-1 per row."""
    clipped = np.clip(weights, 0.0, None)
    totals = clipped.sum(axis=1, keepdims=True)
    safe = np.where(totals > 0, clipped / totals, 1.0 / weights.shape[1])
    cdf = np.cumsum(safe, axis=1)
    u = rng.random(weights.shape[0])[:, None]
    return (u > cdf).sum(axis=1).astype(np.int32)
