#!/usr/bin/env python3
"""Diagnose scoring bias: actual league rates vs instrumented Monte Carlo sim.

Usage:
  PYTHONPATH=. .venv/bin/python scripts/diagnose_scoring_bias.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nba_sim.schema import ZONES
from nba_sim.settings import load_settings
from nba_sim.storage import read_rows
from projections.blend import available_season_window, load_season_bundle
from projections.build import ProjectionCache, build_game_projections
from sim.engine import (
    _ZONE_POINTS,
    _lineups_matrix,
    _pack_rates,
    _weighted_choice,
)

THREE_ZONES = ("left_corner_3", "right_corner_3", "above_break_3")
RUNS = 200
SAMPLE_GAMES = 20
SEED = 42


@dataclass
class LeagueActuals:
    season: str
    team_games: int
    ppg: float
    pace: float
    fga: float
    fgm: float
    fg_pct: float
    pa3: float
    pm3: float
    fg3_pct: float
    fta: float
    ftm: float
    ft_pct: float
    oreb: float
    tov: float
    stl: float
    blk: float
    zone_fga: dict[str, float] = field(default_factory=dict)
    zone_fg_pct: dict[str, float] = field(default_factory=dict)
    zone_share: dict[str, float] = field(default_factory=dict)


@dataclass
class SimAgg:
    games: int = 0
    # per team-game (home and away counted separately)
    pts: float = 0.0
    poss_proj: float = 0.0
    trips: float = 0.0
    poss_endings: float = 0.0
    stl: float = 0.0
    tov: float = 0.0
    ft_trips: float = 0.0
    fta: float = 0.0
    ftm: float = 0.0
    fga: float = 0.0
    fgm: float = 0.0
    pa3: float = 0.0
    pm3: float = 0.0
    blk: float = 0.0
    oreb: float = 0.0
    dreb: float = 0.0
    make_pts: float = 0.0
    ft_pts: float = 0.0
    zone_fga: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    zone_fgm: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    def add_team(self, other: "SimAgg") -> None:
        self.games += other.games
        for name in (
            "pts",
            "poss_proj",
            "trips",
            "poss_endings",
            "stl",
            "tov",
            "ft_trips",
            "fta",
            "ftm",
            "fga",
            "fgm",
            "pa3",
            "pm3",
            "blk",
            "oreb",
            "dreb",
            "make_pts",
            "ft_pts",
        ):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        for zone in ZONES:
            self.zone_fga[zone] += other.zone_fga[zone]
            self.zone_fgm[zone] += other.zone_fgm[zone]

    def per_team_game(self) -> dict[str, float]:
        n = max(self.games, 1)
        out = {
            "pts": self.pts / n,
            "poss_proj": self.poss_proj / n,
            "trips": self.trips / n,
            "poss_endings": self.poss_endings / n,
            "stl": self.stl / n,
            "tov": self.tov / n,
            "ft_trips": self.ft_trips / n,
            "fta": self.fta / n,
            "ftm": self.ftm / n,
            "ft_pct": (self.ftm / self.fta) if self.fta else 0.0,
            "fga": self.fga / n,
            "fgm": self.fgm / n,
            "fg_pct": (self.fgm / self.fga) if self.fga else 0.0,
            "pa3": self.pa3 / n,
            "pm3": self.pm3 / n,
            "fg3_pct": (self.pm3 / self.pa3) if self.pa3 else 0.0,
            "blk": self.blk / n,
            "oreb": self.oreb / n,
            "dreb": self.dreb / n,
            "make_pts": self.make_pts / n,
            "ft_pts": self.ft_pts / n,
            "ppp_vs_proj": (self.pts / self.poss_proj) if self.poss_proj else 0.0,
            "ppp_vs_endings": (self.pts / self.poss_endings) if self.poss_endings else 0.0,
        }
        for zone in ZONES:
            zfga = self.zone_fga[zone]
            zfgm = self.zone_fgm[zone]
            out[f"{zone}_fga"] = zfga / n
            out[f"{zone}_fg_pct"] = (zfgm / zfga) if zfga else 0.0
            out[f"{zone}_share"] = (zfga / self.fga) if self.fga else 0.0
        return out


def compute_actuals(settings, season: str) -> LeagueActuals:
    teams = read_rows(settings, "team_game_results", season)
    logs = read_rows(settings, "player_game_logs", season)
    rates = read_rows(settings, "player_game_rates", season)

    pts = [float(r["pts"]) for r in teams if r.get("pts") is not None]
    paces = [float(r["pace"]) for r in teams if r.get("pace") is not None]
    by_gt_log: dict[tuple, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in logs:
        key = (str(row["game_id"]), int(row["team_id"]))
        for name in ("oreb", "tov", "stl", "blk"):
            by_gt_log[key][name] += float(row.get(name) or 0)

    by_gt_rate: dict[tuple, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rates:
        key = (str(row["game_id"]), int(row["team_id"]))
        by_gt_rate[key]["fta"] += float(row.get("fta") or 0)
        by_gt_rate[key]["ftm"] += float(row.get("ftm") or 0)
        for zone in ZONES:
            by_gt_rate[key][f"{zone}_fga"] += float(row.get(f"{zone}_fga") or 0)
            by_gt_rate[key][f"{zone}_fgm"] += float(row.get(f"{zone}_fgm") or 0)

    n_rate = max(len(by_gt_rate), 1)
    fga = sum(sum(v[f"{z}_fga"] for z in ZONES) for v in by_gt_rate.values()) / n_rate
    fgm = sum(sum(v[f"{z}_fgm"] for z in ZONES) for v in by_gt_rate.values()) / n_rate
    pa3 = sum(sum(v[f"{z}_fga"] for z in THREE_ZONES) for v in by_gt_rate.values()) / n_rate
    pm3 = sum(sum(v[f"{z}_fgm"] for z in THREE_ZONES) for v in by_gt_rate.values()) / n_rate
    fta = sum(v["fta"] for v in by_gt_rate.values()) / n_rate
    ftm = sum(v["ftm"] for v in by_gt_rate.values()) / n_rate
    n_log = max(len(by_gt_log), 1)

    zone_fga = {}
    zone_fg_pct = {}
    zone_share = {}
    for zone in ZONES:
        zfga = sum(v[f"{zone}_fga"] for v in by_gt_rate.values()) / n_rate
        zfgm = sum(v[f"{zone}_fgm"] for v in by_gt_rate.values()) / n_rate
        zone_fga[zone] = zfga
        zone_fg_pct[zone] = (zfgm / zfga) if zfga else 0.0
        zone_share[zone] = (zfga / fga) if fga else 0.0

    return LeagueActuals(
        season=season,
        team_games=len(pts),
        ppg=sum(pts) / len(pts) if pts else 0.0,
        pace=sum(paces) / len(paces) if paces else 0.0,
        fga=fga,
        fgm=fgm,
        fg_pct=(fgm / fga) if fga else 0.0,
        pa3=pa3,
        pm3=pm3,
        fg3_pct=(pm3 / pa3) if pa3 else 0.0,
        fta=fta,
        ftm=ftm,
        ft_pct=(ftm / fta) if fta else 0.0,
        oreb=sum(v["oreb"] for v in by_gt_log.values()) / n_log,
        tov=sum(v["tov"] for v in by_gt_log.values()) / n_log,
        stl=sum(v["stl"] for v in by_gt_log.values()) / n_log,
        blk=sum(v["blk"] for v in by_gt_log.values()) / n_log,
        zone_fga=zone_fga,
        zone_fg_pct=zone_fg_pct,
        zone_share=zone_share,
    )


def midseason_sample(schedule: list[dict], n: int = SAMPLE_GAMES) -> list[dict]:
    finals = sorted(
        [row for row in schedule if row.get("status") == "final"],
        key=lambda row: (row["game_date"], row["game_id"]),
    )
    if len(finals) < n + 20:
        # need prior games for as_of; skip first chunk
        usable = finals[max(10, len(finals) // 5) :]
    else:
        start = len(finals) // 3
        usable = finals[start : start + len(finals) // 3]
    if len(usable) <= n:
        return usable
    idx = np.linspace(0, len(usable) - 1, n, dtype=int)
    return [usable[i] for i in idx]


def _instrumented_possession(
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
    counts: dict[str, np.ndarray],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Same math as sim.engine._vector_possession with outcome counters."""
    n_runs = active.shape[0]
    home_delta = np.zeros(n_runs)
    away_delta = np.zeros(n_runs)
    next_offense_home = offense_home.copy()
    if not np.any(active):
        return home_delta, away_delta, next_offense_home

    def _add(name: str, mask: np.ndarray, values: np.ndarray | None = None) -> None:
        """Accumulate per-run totals; split offense events by home/away offense."""
        if values is None:
            values = mask.astype(float)
        counts[name] += values
        if name.startswith("def_"):
            return
        counts[f"H_{name}"] += np.where(offense_home, values, 0.0)
        counts[f"A_{name}"] += np.where(~offense_home, values, 0.0)

    counts["trips"] += active.astype(float)
    _add("trips_side", active)

    off_lineups = np.where(offense_home[:, None], home_lineups, away_lineups)
    def_lineups = np.where(offense_home[:, None], away_lineups, home_lineups)

    stl_w = packed["stl_rate"][def_lineups]
    stl_prob = np.clip(stl_w.sum(axis=1), 0.0, 0.12)
    is_stl = active & (rng.random(n_runs) < stl_prob)
    if np.any(is_stl):
        pick = _weighted_choice(rng, stl_w[is_stl])
        runners = np.flatnonzero(is_stl)
        players = def_lineups[is_stl, pick]
        np.add.at(stl, (players, runners), 1)
        next_offense_home[is_stl] = ~offense_home[is_stl]
        # Steal credited to defense; possession ending credited to offense
        counts["def_stl"] += is_stl.astype(float)
        counts["H_def_stl"] += (is_stl & ~offense_home).astype(float)  # home defense
        counts["A_def_stl"] += (is_stl & offense_home).astype(float)
        _add("poss_end", is_stl)

    remaining = active & ~is_stl
    if not np.any(remaining):
        return home_delta, away_delta, next_offense_home

    usage_w = packed["usage"][off_lineups]
    user_slot = _weighted_choice(rng, usage_w)
    users = off_lineups[np.arange(n_runs), user_slot]

    tov_prob = np.clip(packed["tov_rate"][users], 0.02, 0.35)
    is_tov = remaining & (rng.random(n_runs) < tov_prob)
    if np.any(is_tov):
        runners = np.flatnonzero(is_tov)
        np.add.at(tov, (users[is_tov], runners), 1)
        next_offense_home[is_tov] = ~offense_home[is_tov]
        _add("tov", is_tov)
        _add("poss_end", is_tov)

    remaining = remaining & ~is_tov
    if not np.any(remaining):
        return home_delta, away_delta, next_offense_home

    ft_prob = np.clip(packed["ft_rate"][users], 0.0, 0.60)
    is_ft = remaining & (rng.random(n_runs) < ft_prob)
    if np.any(is_ft):
        fta = np.where(rng.random(n_runs) < 0.85, 2, 3)
        ft_pct = np.clip(packed["ft_pct"][users], 0.4, 0.95)
        made = np.zeros(n_runs)
        idx = np.flatnonzero(is_ft)
        made[idx] = rng.binomial(fta[idx], ft_pct[idx])
        runners = idx
        np.add.at(pts, (users[is_ft], runners), made[is_ft])
        home_delta = np.where(is_ft & offense_home, made, home_delta)
        away_delta = np.where(is_ft & ~offense_home, made, away_delta)
        next_offense_home[is_ft] = ~offense_home[is_ft]
        _add("ft_trips", is_ft)
        _add("fta", is_ft, np.where(is_ft, fta, 0).astype(float))
        _add("ftm", is_ft, made)
        _add("ft_pts", is_ft, made)
        _add("poss_end", is_ft)

    remaining = remaining & ~is_ft
    if not np.any(remaining):
        return home_delta, away_delta, next_offense_home

    zone_share = packed["zone_share"][users]
    zone_i = _weighted_choice(rng, zone_share)
    fg_pct = np.clip(packed["zone_fg"][users, zone_i], 0.15, 0.85)

    blk_w = packed["blk_rate"][def_lineups]
    blk_scale = np.where(zone_i == 0, 1.4, 0.7)
    blk_prob = np.clip(blk_w.sum(axis=1) * blk_scale, 0.0, 0.10)
    is_blk = remaining & (rng.random(n_runs) < blk_prob)
    if np.any(is_blk):
        pick = _weighted_choice(rng, blk_w[is_blk])
        runners = np.flatnonzero(is_blk)
        players = def_lineups[is_blk, pick]
        np.add.at(blk, (players, runners), 1)
        counts["def_blk"] += is_blk.astype(float)
        counts["H_def_blk"] += (is_blk & ~offense_home).astype(float)
        counts["A_def_blk"] += (is_blk & offense_home).astype(float)

    is_shot = remaining
    _add("fga", is_shot)
    for zi, zone in enumerate(ZONES):
        mask = is_shot & (zone_i == zi)
        _add(f"fga_{zone}", mask)
    points_all = _ZONE_POINTS[zone_i]
    _add("pa3", is_shot & (points_all == 3.0))

    is_make = remaining & ~is_blk & (rng.random(n_runs) < fg_pct)
    is_miss = remaining & ~is_make

    if np.any(is_make):
        points = _ZONE_POINTS[zone_i]
        runners = np.flatnonzero(is_make)
        np.add.at(pts, (users[is_make], runners), points[is_make])
        threes = is_make & (points == 3.0)
        if np.any(threes):
            np.add.at(fg3m, (users[threes], np.flatnonzero(threes)), 1)
        home_delta = np.where(is_make & offense_home, points, home_delta)
        away_delta = np.where(is_make & ~offense_home, points, away_delta)
        mate_slot = (user_slot + 1 + rng.integers(0, 4, size=n_runs)) % off_lineups.shape[1]
        mates = off_lineups[np.arange(n_runs), mate_slot]
        ast_prob = np.clip(packed["ast_rate"][mates], 0.35, 0.75)
        is_ast = is_make & (rng.random(n_runs) < ast_prob)
        if np.any(is_ast):
            np.add.at(ast, (mates[is_ast], np.flatnonzero(is_ast)), 1)
        next_offense_home[is_make] = ~offense_home[is_make]
        _add("fgm", is_make)
        _add("make_pts", is_make, np.where(is_make, points, 0.0))
        _add("pm3", threes)
        for zi, zone in enumerate(ZONES):
            _add(f"fgm_{zone}", is_make & (zone_i == zi))
        _add("poss_end", is_make)

    if np.any(is_miss):
        o_w = packed["oreb"][off_lineups]
        d_w = packed["dreb"][def_lineups]
        p_orb = np.clip(o_w.sum(axis=1) / (o_w.sum(axis=1) + d_w.sum(axis=1) + 1e-9), 0.05, 0.40)
        is_orb = is_miss & (rng.random(n_runs) < p_orb)
        is_drb = is_miss & ~is_orb
        if np.any(is_orb):
            pick = _weighted_choice(rng, o_w[is_orb])
            runners = np.flatnonzero(is_orb)
            players = off_lineups[is_orb, pick]
            np.add.at(reb, (players, runners), 1)
            next_offense_home[is_orb] = offense_home[is_orb]
            _add("oreb", is_orb)
        if np.any(is_drb):
            pick = _weighted_choice(rng, d_w[is_drb])
            runners = np.flatnonzero(is_drb)
            players = def_lineups[is_drb, pick]
            np.add.at(reb, (players, runners), 1)
            next_offense_home[is_drb] = ~offense_home[is_drb]
            counts["def_dreb"] += is_drb.astype(float)
            counts["H_def_dreb"] += (is_drb & ~offense_home).astype(float)
            counts["A_def_dreb"] += (is_drb & offense_home).astype(float)
            _add("poss_end", is_drb)

    return home_delta, away_delta, next_offense_home


def simulate_instrumented(projection, *, runs: int, seed: int, config: dict) -> tuple[SimAgg, SimAgg]:
    """Return (home_agg, away_agg) averaged across runs (totals summed then /runs)."""
    rng = np.random.default_rng(seed)
    players = list(projection.players)
    n_players = len(players)
    minutes = np.zeros((n_players, runs), dtype=float)
    for index, player in enumerate(players):
        minutes[index] = player.minutes.sample(rng, runs)

    home_idx = np.array([i for i, p in enumerate(players) if p.home_away == "H"], dtype=np.int32)
    away_idx = np.array([i for i, p in enumerate(players) if p.home_away == "A"], dtype=np.int32)
    packed = _pack_rates(players)
    home_lineups = _lineups_matrix(rng, home_idx, minutes)
    away_lineups = _lineups_matrix(rng, away_idx, minutes)

    home_poss = np.clip(rng.normal(projection.home_possessions, 3.5, size=runs), 80.0, 130.0)
    away_poss = np.clip(rng.normal(projection.away_possessions, 3.5, size=runs), 80.0, 130.0)
    reg_trips = np.clip(np.round(home_poss + away_poss).astype(int), 160, 260)

    pts = np.zeros((n_players, runs), dtype=float)
    reb = np.zeros((n_players, runs), dtype=float)
    ast = np.zeros((n_players, runs), dtype=float)
    fg3m = np.zeros((n_players, runs), dtype=float)
    stl = np.zeros((n_players, runs), dtype=float)
    blk = np.zeros((n_players, runs), dtype=float)
    tov = np.zeros((n_players, runs), dtype=float)
    home_pts = np.zeros(runs, dtype=float)
    away_pts = np.zeros(runs, dtype=float)

    base_keys = [
        "trips",
        "trips_side",
        "poss_end",
        "tov",
        "ft_trips",
        "fta",
        "ftm",
        "ft_pts",
        "fga",
        "fgm",
        "pa3",
        "pm3",
        "oreb",
        "make_pts",
        "def_stl",
        "def_blk",
        "def_dreb",
    ]
    counts: dict[str, np.ndarray] = {k: np.zeros(runs) for k in base_keys}
    for zone in ZONES:
        counts[f"fga_{zone}"] = np.zeros(runs)
        counts[f"fgm_{zone}"] = np.zeros(runs)
    # Side-split mirrors created lazily via _add; pre-create for mean lookups.
    for key in list(counts):
        if key in {"trips", "def_stl", "def_blk", "def_dreb"}:
            continue
        counts[f"H_{key}"] = np.zeros(runs)
        counts[f"A_{key}"] = np.zeros(runs)
    for key in ("def_stl", "def_blk", "def_dreb"):
        counts[f"H_{key}"] = np.zeros(runs)
        counts[f"A_{key}"] = np.zeros(runs)

    offense_home = rng.random(runs) < 0.5
    max_trips = int(reg_trips.max())
    for trip in range(max_trips):
        active = trip < reg_trips
        if not np.any(active):
            break
        home_delta, away_delta, offense_home = _instrumented_possession(
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
            counts,
        )
        home_pts += home_delta
        away_pts += away_delta

    # Overtime (same as engine) — still count
    tied = home_pts == away_pts
    ot_period = 0
    while np.any(tied) and ot_period < 5:
        ot_period += 1
        for _ in range(16):
            home_delta, away_delta, offense_home = _instrumented_possession(
                rng,
                packed,
                home_lineups,
                away_lineups,
                offense_home,
                tied,
                pts,
                reb,
                ast,
                fg3m,
                stl,
                blk,
                tov,
                counts,
            )
            home_pts += home_delta
            away_pts += away_delta
            tied = home_pts == away_pts

    def side_agg(is_home: bool) -> SimAgg:
        prefix = "H_" if is_home else "A_"
        agg = SimAgg(games=1)
        if is_home:
            agg.pts = float(home_pts.mean())
            agg.poss_proj = float(home_poss.mean())
        else:
            agg.pts = float(away_pts.mean())
            agg.poss_proj = float(away_poss.mean())
        agg.poss_endings = float(counts[f"{prefix}poss_end"].mean())
        agg.trips = float(counts[f"{prefix}trips_side"].mean())
        for name in ("tov", "ft_trips", "fta", "ftm", "fga", "fgm", "pa3", "pm3", "oreb", "make_pts", "ft_pts"):
            setattr(agg, name, float(counts[f"{prefix}{name}"].mean()))
        agg.stl = float(counts[f"{prefix}def_stl"].mean())
        agg.blk = float(counts[f"{prefix}def_blk"].mean())
        agg.dreb = float(counts[f"{prefix}def_dreb"].mean())
        for zone in ZONES:
            agg.zone_fga[zone] = float(counts[f"{prefix}fga_{zone}"].mean())
            agg.zone_fgm[zone] = float(counts[f"{prefix}fgm_{zone}"].mean())
        return agg

    return side_agg(True), side_agg(False)


def expected_ppp_from_rates(players: list, side: str) -> dict[str, float]:
    """Closed-form expected points per projected possession for one side's on-court mix.

    Uses average of players with minutes.mean > 0, usage-weighted for offense rates,
    and simple 5-man average for rebound/steal (approximation of engine lineup).
    """
    active = [p for p in players if p.home_away == side and p.minutes.mean > 0]
    if not active:
        return {}
    # Top-8 by minutes as proxy for rotation; normalize usage among them
    active = sorted(active, key=lambda p: -p.minutes.mean)[:8]
    usage = np.array([p.rates.usage for p in active], dtype=float)
    usage = usage / usage.sum() if usage.sum() > 0 else np.full(len(active), 1 / len(active))

    # Usage-weighted shooter rates
    tov = sum(u * p.rates.tov_rate for u, p in zip(usage, active))
    ft_rate = sum(u * p.rates.ft_rate for u, p in zip(usage, active))
    ft_pct = sum(u * p.rates.ft_pct for u, p in zip(usage, active))
    # Zone mix / fg
    efg_pts = 0.0
    fg = 0.0
    for zi, zone in enumerate(ZONES):
        share = sum(u * getattr(p.rates, f"{zone}_share") for u, p in zip(usage, active))
        pct = sum(u * getattr(p.rates, f"{zone}_fg_pct") for u, p in zip(usage, active))
        pts = float(_ZONE_POINTS[zi])
        efg_pts += share * pct * pts
        fg += share * pct

    # Approx 5-man steal/blk/oreb from top-5 minutes
    top5 = sorted(active, key=lambda p: -p.minutes.mean)[:5]
    stl = sum(p.rates.stl_rate for p in top5)
    blk = sum(p.rates.blk_rate for p in top5) * 0.9  # mixed zone scale
    oreb = sum(p.rates.oreb_rate for p in top5)
    dreb = sum(p.rates.dreb_rate for p in top5)
    p_orb = oreb / (oreb + dreb + 1e-9)
    p_orb = min(0.40, max(0.05, p_orb))
    p_stl = min(0.12, stl)
    p_blk = min(0.10, blk)

    # One trip expected points (ignoring OREB chains first), then inflate by geometric OREB
    # Engine path: stl -> tov -> ft -> shot
    rem = 1.0 - p_stl
    p_tov = rem * min(0.35, max(0.02, tov))
    rem2 = rem - p_tov
    p_ft = rem2 * min(0.60, max(0.0, ft_rate))
    rem3 = rem2 - p_ft
    # FT: 85% 2FTA, 15% 3FTA
    e_ft_pts = p_ft * (0.85 * 2 + 0.15 * 3) * ft_pct
    p_shot = rem3
    p_make = p_shot * (1.0 - p_blk) * fg
    p_miss = p_shot - p_make
    e_make_pts = p_shot * (1.0 - p_blk) * efg_pts / max(fg, 1e-9) * fg  # = p_shot*(1-blk)*efg_pts component
    # cleaner:
    e_make_pts = p_shot * (1.0 - p_blk) * efg_pts
    # After miss, OREB continues — geometric series of extra trips
    p_continue = p_miss * p_orb
    # Expected points from one initial trip including OREB chain:
    # E = e0 + p_continue * E  => E = e0 / (1 - p_continue) where e0 is pts from this trip only
    e0 = e_ft_pts + e_make_pts
    e_trip = e0 / max(1e-9, 1.0 - p_continue)
    p_end = 1.0 - p_continue  # fraction of trips that end a possession
    return {
        "p_stl": p_stl,
        "p_tov": p_tov,
        "p_ft": p_ft,
        "p_shot": p_shot,
        "fg": fg,
        "efg_pts": efg_pts,
        "p_orb": p_orb,
        "p_continue": p_continue,
        "e_pts_per_trip": e_trip,
        "e_pts_per_poss_ending": e_trip / p_end if p_end else 0.0,
        "ft_rate_raw": ft_rate,
        "tov_rate_raw": tov,
        "implied_fta_per_trip": p_ft * (0.85 * 2 + 0.15 * 3),
    }


def projection_rate_snapshot(projection) -> dict[str, float]:
    """Average projected rates for players expected to play."""
    rows = []
    for side in ("H", "A"):
        active = [p for p in projection.players if p.home_away == side and p.minutes.mean > 0]
        if not active:
            continue
        usage = np.array([p.rates.usage for p in active])
        usage = usage / usage.sum() if usage.sum() else np.ones(len(active)) / len(active)
        rows.append(
            {
                "usage_sum": float(sum(p.rates.usage for p in active)),
                "tov": float(sum(u * p.rates.tov_rate for u, p in zip(usage, active))),
                "ft_rate": float(sum(u * p.rates.ft_rate for u, p in zip(usage, active))),
                "ft_pct": float(sum(u * p.rates.ft_pct for u, p in zip(usage, active))),
                "stl5": float(sum(p.rates.stl_rate for p in sorted(active, key=lambda x: -x.minutes.mean)[:5])),
                "oreb5": float(sum(p.rates.oreb_rate for p in sorted(active, key=lambda x: -x.minutes.mean)[:5])),
                "dreb5": float(sum(p.rates.dreb_rate for p in sorted(active, key=lambda x: -x.minutes.mean)[:5])),
                "poss": projection.home_possessions if side == "H" else projection.away_possessions,
                **expected_ppp_from_rates(projection.players, side),
            }
        )
    if not rows:
        return {}
    keys = rows[0].keys()
    return {k: float(np.mean([r[k] for r in rows])) for k in keys}


def fmt(x: float, digits: int = 2) -> str:
    return f"{x:.{digits}f}"


def pct_delta(sim: float, act: float) -> str:
    if act == 0:
        return "n/a"
    return f"{100.0 * (sim - act) / act:+.1f}%"


def print_actuals(a: LeagueActuals) -> None:
    print(f"\n{'=' * 72}")
    print(f"ACTUAL league averages — {a.season}  (n_team_games={a.team_games})")
    print(f"{'=' * 72}")
    print(f"  PPG={fmt(a.ppg)}  pace={fmt(a.pace)}  PPP={fmt(a.ppg / a.pace, 3)}")
    print(f"  FGA={fmt(a.fga)} FG%={fmt(a.fg_pct, 3)}  3PA={fmt(a.pa3)} 3P%={fmt(a.fg3_pct, 3)}")
    print(f"  FTA={fmt(a.fta)} FT%={fmt(a.ft_pct, 3)}  OREB={fmt(a.oreb)} TOV={fmt(a.tov)}")
    print(f"  STL={fmt(a.stl)} BLK={fmt(a.blk)}")
    for zone in ZONES:
        print(
            f"  {zone:18s} FGA={fmt(a.zone_fga[zone])} share={fmt(a.zone_share[zone], 3)} "
            f"FG%={fmt(a.zone_fg_pct[zone], 3)}"
        )


def print_sim_vs_actual(label: str, sim: dict[str, float], a: LeagueActuals) -> None:
    print(f"\n{'-' * 72}")
    print(f"SIMULATED vs ACTUAL — {label}")
    print(f"{'-' * 72}")
    rows = [
        ("PPG", sim["pts"], a.ppg),
        ("pace/poss_proj", sim["poss_proj"], a.pace),
        ("poss_endings", sim["poss_endings"], a.pace),
        ("trips (off share)", sim["trips"], a.pace),
        ("FGA", sim["fga"], a.fga),
        ("FG%", sim["fg_pct"], a.fg_pct),
        ("3PA", sim["pa3"], a.pa3),
        ("3P%", sim["fg3_pct"], a.fg3_pct),
        ("FTA", sim["fta"], a.fta),
        ("FT%", sim["ft_pct"], a.ft_pct),
        ("OREB", sim["oreb"], a.oreb),
        ("TOV", sim["tov"], a.tov),
        ("STL", sim["stl"], a.stl),
        ("BLK", sim["blk"], a.blk),
        ("FT trips", sim["ft_trips"], a.fta / 2.1),  # approx FT possessions
        ("make_pts", sim["make_pts"], a.ppg - a.ftm),
        ("ft_pts", sim["ft_pts"], a.ftm),
    ]
    print(f"  {'metric':18s} {'sim':>8s} {'actual':>8s} {'delta':>8s}")
    for name, s, act in rows:
        print(f"  {name:18s} {fmt(s):>8s} {fmt(act):>8s} {pct_delta(s, act):>8s}")
    print(f"  PPP vs proj poss   {fmt(sim['ppp_vs_proj'], 3)}")
    print(f"  PPP vs endings     {fmt(sim['ppp_vs_endings'], 3)}")
    print(f"  endings/proj       {fmt(sim['poss_endings'] / sim['poss_proj'], 3)}")
    print(f"  trips/proj         {fmt(sim['trips'] / sim['poss_proj'], 3)}")
    for zone in ZONES:
        print(
            f"  {zone:18s} FGA sim={fmt(sim[f'{zone}_fga'])} act={fmt(a.zone_fga[zone])} "
            f"({pct_delta(sim[f'{zone}_fga'], a.zone_fga[zone])})  "
            f"FG% sim={fmt(sim[f'{zone}_fg_pct'], 3)} act={fmt(a.zone_fg_pct[zone], 3)}"
        )


def main() -> int:
    settings = load_settings()
    config = settings.config
    seasons = ["2024-25", "2025-26"]
    seasons_back = list(config["blending"]["season_weights"]["seasons_back"])

    needed: set[str] = set()
    for season in seasons:
        window = available_season_window(settings, season, seasons_back)
        needed.update(window)
        needed.add(season)
    print(f"Loading season bundles: {sorted(needed)}")
    bundle_cache = {label: load_season_bundle(settings, label) for label in sorted(needed)}

    overall = SimAgg()
    snap_vals: list[dict[str, float]] = []

    for season in seasons:
        actuals = compute_actuals(settings, season)
        print_actuals(actuals)

        schedule = read_rows(settings, "schedule", season)
        sample = midseason_sample(schedule, SAMPLE_GAMES)
        print(f"\nSampling {len(sample)} mid-season games, {RUNS} runs each...")

        window = available_season_window(settings, season, seasons_back)
        if season not in window:
            window = [season] + window
        bundles = [bundle_cache[label] for label in window if label in bundle_cache]
        cache = ProjectionCache()
        season_agg = SimAgg()
        actual_sample_pts = []

        for i, row in enumerate(sample):
            game_id = str(row["game_id"])
            try:
                projection = build_game_projections(
                    settings,
                    season=season,
                    game_id=game_id,
                    as_of=row["game_date"],
                    bundles=bundles,
                    cache=cache,
                )
            except ValueError as exc:
                print(f"  skip {game_id}: {exc}")
                continue
            home_n = sum(1 for p in projection.players if p.home_away == "H" and p.minutes.mean > 0)
            away_n = sum(1 for p in projection.players if p.home_away == "A" and p.minutes.mean > 0)
            if home_n < 5 or away_n < 5:
                print(f"  skip {game_id}: thin roster H={home_n} A={away_n}")
                continue

            snap = projection_rate_snapshot(projection)
            snap_vals.append(snap)

            home_a, away_a = simulate_instrumented(
                projection, runs=RUNS, seed=SEED + i, config=config
            )
            season_agg.add_team(home_a)
            season_agg.add_team(away_a)
            overall.add_team(home_a)
            overall.add_team(away_a)
            actual_sample_pts.append(float(row["home_pts"]))
            actual_sample_pts.append(float(row["away_pts"]))
            print(
                f"  {game_id} {row['game_date']} proj_poss "
                f"H={projection.home_possessions:.1f} A={projection.away_possessions:.1f} "
                f"sim_pts H={home_a.pts:.1f} A={away_a.pts:.1f} "
                f"actual H={row['home_pts']} A={row['away_pts']}"
            )

        sim = season_agg.per_team_game()
        print_sim_vs_actual(season, sim, actuals)
        if actual_sample_pts:
            print(
                f"  sample actual PPG={fmt(float(np.mean(actual_sample_pts)))} "
                f"(these games only)"
            )
        if snap_vals:
            # season-specific snaps: last len(sample) entries roughly
            pass

    print(f"\n{'=' * 72}")
    print("PROJECTION RATE SNAPSHOT (avg across sampled games/sides)")
    print(f"{'=' * 72}")
    if snap_vals:
        keys = snap_vals[0].keys()
        for k in keys:
            print(f"  {k:28s} {fmt(float(np.mean([s[k] for s in snap_vals])), 4)}")

    # Overall combined
    a24 = compute_actuals(settings, "2024-25")
    # blend actuals for display reference
    a25 = compute_actuals(settings, "2025-26")
    blended = LeagueActuals(
        season="2024-25+2025-26",
        team_games=a24.team_games + a25.team_games,
        ppg=0.5 * (a24.ppg + a25.ppg),
        pace=0.5 * (a24.pace + a25.pace),
        fga=0.5 * (a24.fga + a25.fga),
        fgm=0.5 * (a24.fgm + a25.fgm),
        fg_pct=0.5 * (a24.fg_pct + a25.fg_pct),
        pa3=0.5 * (a24.pa3 + a25.pa3),
        pm3=0.5 * (a24.pm3 + a25.pm3),
        fg3_pct=0.5 * (a24.fg3_pct + a25.fg3_pct),
        fta=0.5 * (a24.fta + a25.fta),
        ftm=0.5 * (a24.ftm + a25.ftm),
        ft_pct=0.5 * (a24.ft_pct + a25.ft_pct),
        oreb=0.5 * (a24.oreb + a25.oreb),
        tov=0.5 * (a24.tov + a25.tov),
        stl=0.5 * (a24.stl + a25.stl),
        blk=0.5 * (a24.blk + a25.blk),
        zone_fga={z: 0.5 * (a24.zone_fga[z] + a25.zone_fga[z]) for z in ZONES},
        zone_fg_pct={z: 0.5 * (a24.zone_fg_pct[z] + a25.zone_fg_pct[z]) for z in ZONES},
        zone_share={z: 0.5 * (a24.zone_share[z] + a25.zone_share[z]) for z in ZONES},
    )
    print_sim_vs_actual("ALL SAMPLED GAMES", overall.per_team_game(), blended)

    print(f"\n{'=' * 72}")
    print("ENGINE MATH NOTES (for root-cause)")
    print(f"{'=' * 72}")
    print(
        """
  1) Trip budget (sim/engine.py ~77-79):
       reg_trips = round(home_poss + away_poss)
     Pace is NBA possession *endings*. OREB keeps offense but still consumes a trip
     (engine ~311-322). So poss_endings < pace → fewer scoring opportunities.

  2) ft_rate (projections/rates.py ~144): fta/used is FTA *count* per use.
     Engine (~254-262) treats it as P(FT trip) then shoots 2–3 FTA → ~2.1× FTA.

  3) Steal then turnover (engine ~222-247): stl_rate path plus tov_rate = box TOV/used
     (TOV includes steals) → double-counted dead possessions.

  4) stl_rate / blk_rate (rates.py ~149-150): denominator is off+def possessions,
     but applied only on defense → understated team steal/block rates (partially
     offsets #3 for steals).
"""
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
