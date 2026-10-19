"""Kalman-filter team ratings with rest-aware home-court advantage.

State is each team's net rating (pts / 100 poss vs average). After every final
game the filter updates both teams from the HCA-adjusted margin residual.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np

from nba_sim.settings import Settings
from nba_sim.storage import read_rows
from projections.context import TeamStrength


@dataclass
class TeamKalmanState:
    mean: float = 0.0
    var: float = 25.0


@dataclass
class KalmanRatings:
    """As-of snapshot of team net ratings and HCA knobs."""

    ratings: dict[int, float] = field(default_factory=dict)
    variances: dict[int, float] = field(default_factory=dict)
    source: str = "defaults"

    def team_strength(self, team_id: int, league: TeamStrength) -> TeamStrength:
        net = float(self.ratings.get(int(team_id), 0.0))
        return TeamStrength(
            ortg=float(league.ortg + 0.5 * net),
            drtg=float(league.drtg - 0.5 * net),
        )


def rest_hca_points(
    rest_home: int,
    rest_away: int,
    *,
    config: dict[str, Any],
) -> float:
    """Non-linear HCA in points from both teams' rest (0 = B2B)."""
    ctx = config.get("context", {})
    base = float(ctx.get("kalman_hca_points", 2.8))
    # Rest value curve (points contribution to the home team's expected margin).
    curve = ctx.get(
        "rest_hca_curve",
        {0: -2.2, 1: 0.0, 2: 0.6, 3: 0.9, 4: 1.0},
    )
    curve = {int(k): float(v) for k, v in curve.items()}

    def _val(days: int) -> float:
        days = max(0, int(days))
        if days in curve:
            return curve[days]
        return curve[max(curve)] if curve else 0.0

    hca = base + _val(rest_home) - _val(rest_away)
    # Both on B2B: damp absolute HCA (tired-on-tired).
    if rest_home == 0 and rest_away == 0:
        hca *= float(ctx.get("both_b2b_hca_scale", 0.55))
    return float(hca)


def rest_fg_adjustment(
    rest_home: int,
    rest_away: int,
    *,
    home_away: str,
    config: dict[str, Any],
) -> float:
    """Translate rest HCA points into a soft FG% multiplicative delta."""
    hca_pts = rest_hca_points(rest_home, rest_away, config=config)
    # ~1 point of margin ≈ 0.004 relative FG for the home offense.
    scale = float(config.get("context", {}).get("hca_points_to_fg", 0.004))
    delta = hca_pts * scale
    if home_away == "H":
        return delta
    return -delta


@dataclass
class KalmanTracker:
    """Incremental walk-forward Kalman (advance only forward in time)."""

    season: str
    config: dict[str, Any]
    schedule: list[dict]
    states: dict[int, TeamKalmanState] = field(default_factory=dict)
    last_date: dict[int, date] = field(default_factory=dict)
    next_index: int = 0
    cursor_as_of: date | None = None
    process_var: float = 1.5
    obs_var: float = 140.0
    init_var: float = 25.0

    def snapshot(self) -> KalmanRatings:
        return KalmanRatings(
            ratings={tid: st.mean for tid, st in self.states.items()},
            variances={tid: st.var for tid, st in self.states.items()},
            source=f"kalman:{self.season}",
        )

    def advance_to(self, as_of: date) -> KalmanRatings:
        """Incorporate all finals with game_date < as_of."""
        if self.cursor_as_of is not None and as_of < self.cursor_as_of:
            # Should not happen in walk-forward; rebuild from scratch.
            self._reset()
        while self.next_index < len(self.schedule):
            row = self.schedule[self.next_index]
            if row["game_date"] >= as_of:
                break
            self._update_game(row)
            self.next_index += 1
        self.cursor_as_of = as_of
        return self.snapshot()

    def _reset(self) -> None:
        prior = {tid: TeamKalmanState(mean=st.mean, var=self.init_var) for tid, st in self.states.items()}
        # Keep prior means as priors but clear game path — actually full reset:
        means = {tid: st.mean for tid, st in self.states.items()}
        self.states = {
            tid: TeamKalmanState(mean=net, var=self.init_var) for tid, net in means.items()
        }
        self.last_date.clear()
        self.next_index = 0
        self.cursor_as_of = None

    def _update_game(self, row: dict) -> None:
        home = int(row["home_team_id"])
        away = int(row["away_team_id"])
        margin = float(row.get("home_pts") or 0.0) - float(row.get("away_pts") or 0.0)
        game_date = row["game_date"]
        rest_home = _rest_days(self.last_date.get(home), game_date)
        rest_away = _rest_days(self.last_date.get(away), game_date)
        hca = rest_hca_points(rest_home, rest_away, config=self.config)

        home_state = self.states.setdefault(home, TeamKalmanState(var=self.init_var))
        away_state = self.states.setdefault(away, TeamKalmanState(var=self.init_var))
        home_state.var += self.process_var
        away_state.var += self.process_var

        pred = home_state.mean - away_state.mean + hca
        resid = margin - pred
        s = home_state.var + away_state.var + self.obs_var
        if s > 1e-9:
            k_home = home_state.var / s
            k_away = away_state.var / s
            home_state.mean += k_home * resid
            away_state.mean -= k_away * resid
            home_state.var *= max(0.05, 1.0 - k_home)
            away_state.var *= max(0.05, 1.0 - k_away)

        self.last_date[home] = game_date
        self.last_date[away] = game_date


def make_kalman_tracker(
    settings: Settings,
    *,
    season: str,
    config: dict[str, Any],
    prior_nets: dict[int, float] | None = None,
) -> KalmanTracker:
    ctx = config.get("context", {})
    schedule = [
        row
        for row in read_rows(settings, "schedule", season)
        if str(row.get("status") or "") == "final"
    ]
    schedule.sort(key=lambda r: (r["game_date"], r["game_id"]))
    init_var = float(ctx.get("kalman_init_var", 25.0))
    states: dict[int, TeamKalmanState] = {}
    if prior_nets:
        for tid, net in prior_nets.items():
            states[int(tid)] = TeamKalmanState(mean=float(net), var=init_var)
    return KalmanTracker(
        season=season,
        config=config,
        schedule=schedule,
        states=states,
        process_var=float(ctx.get("kalman_process_var", 1.5)),
        obs_var=float(ctx.get("kalman_obs_var", 140.0)),
        init_var=init_var,
    )


def build_kalman_as_of(
    settings: Settings,
    *,
    season: str,
    as_of: date,
    config: dict[str, Any],
    prior_nets: dict[int, float] | None = None,
) -> KalmanRatings:
    """Run the filter through all finals strictly before ``as_of``."""
    tracker = make_kalman_tracker(
        settings, season=season, config=config, prior_nets=prior_nets
    )
    return tracker.advance_to(as_of)


def prior_nets_from_strength(strength: dict[int, TeamStrength], league: TeamStrength) -> dict[int, float]:
    out = {}
    for tid, ts in strength.items():
        out[int(tid)] = float((ts.ortg - ts.drtg) - (league.ortg - league.drtg))
    return out


def _rest_days(prev: date | None, game_date: date) -> int:
    if prev is None:
        return 3
    return max(0, (game_date - prev).days - 1)
