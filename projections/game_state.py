"""Game-state pace factors: late fouls, trail haste, lead slowdown, garbage time.

Learned from lineup_stints possessions/duration when available; otherwise uses
research defaults. Factors multiply the remaining possession budget in Q3–Q4.
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


@dataclass
class GameStateModel:
    """Pace multipliers by period × margin situation (offense perspective)."""

    # Relative possessions/sec vs league mid-game baseline (1.0 = normal).
    # Keys: (period 1-4, "trail"|"lead"|"close"|"blowout_lead"|"blowout_trail")
    pace_factor: dict[tuple[int, str], float] = field(default_factory=dict)
    intentional_foul_prob: float = 0.22  # per possession when eligible
    source: str = "defaults"

    def factor(
        self,
        *,
        period: int,
        abs_margin: float,
        offense_leading: bool,
        close_thr: float,
        blowout_thr: float,
    ) -> float:
        period = int(np.clip(period, 1, 4))
        if abs_margin >= blowout_thr:
            key = (period, "blowout_lead" if offense_leading else "blowout_trail")
        elif abs_margin < close_thr:
            key = (period, "lead" if offense_leading else "trail")
        else:
            key = (period, "close")
        return float(self.pace_factor.get(key, 1.0))

    def blend_factor_array(
        self,
        period_idx: np.ndarray,
        abs_margin: np.ndarray,
        *,
        close_thr: float,
        blowout_thr: float,
    ) -> np.ndarray:
        """Vectorized 0.5*(lead+trail) pace factor for each run."""
        periods = np.clip(period_idx.astype(np.int32) + 1, 1, 4)
        out = np.ones(period_idx.shape[0], dtype=float)
        for period in (1, 2, 3, 4):
            mask = periods == period
            if not np.any(mask):
                continue
            am = abs_margin[mask]
            blow = am >= blowout_thr
            close = am < close_thr
            mid = ~blow & ~close
            lead = np.empty(am.shape[0], dtype=float)
            trail = np.empty(am.shape[0], dtype=float)
            lead[blow] = self.pace_factor.get((period, "blowout_lead"), 1.0)
            trail[blow] = self.pace_factor.get((period, "blowout_trail"), 1.0)
            lead[close] = self.pace_factor.get((period, "lead"), 1.0)
            trail[close] = self.pace_factor.get((period, "trail"), 1.0)
            lead[mid] = self.pace_factor.get((period, "close"), 1.0)
            trail[mid] = self.pace_factor.get((period, "close"), 1.0)
            out[mask] = 0.5 * (lead + trail)
        return out


_DEFAULTS: dict[tuple[int, str], float] = {
    # Early: near-neutral
    (1, "trail"): 1.00,
    (1, "lead"): 1.00,
    (1, "close"): 1.00,
    (1, "blowout_lead"): 1.00,
    (1, "blowout_trail"): 1.01,
    (2, "trail"): 1.01,
    (2, "lead"): 0.99,
    (2, "close"): 1.00,
    (2, "blowout_lead"): 1.01,
    (2, "blowout_trail"): 1.02,
    # Late: trailing teams hurry; leaders ice; garbage time uptempo
    (3, "trail"): 1.04,
    (3, "lead"): 0.97,
    (3, "close"): 1.01,
    (3, "blowout_lead"): 1.03,
    (3, "blowout_trail"): 1.04,
    (4, "trail"): 1.08,
    (4, "lead"): 0.93,
    (4, "close"): 1.02,
    (4, "blowout_lead"): 1.05,
    (4, "blowout_trail"): 1.06,
}


def default_game_state_model(config: dict[str, Any] | None = None) -> GameStateModel:
    sim = (config or {}).get("simulation", {})
    model = GameStateModel(pace_factor=dict(_DEFAULTS), source="defaults")
    if "intentional_foul_prob" in sim:
        model.intentional_foul_prob = float(sim["intentional_foul_prob"])
    # Optional config overrides for late factors.
    for key, default in list(_DEFAULTS.items()):
        period, sit = key
        cfg_key = f"pace_{sit}_q{period}"
        if cfg_key in sim:
            model.pace_factor[key] = float(sim[cfg_key])
    return model


def load_game_state_model(
    settings: Settings,
    bundles: Sequence[SeasonBundle],
    *,
    as_of: date,
    config: dict[str, Any],
    stint_cache: dict[str, list] | None = None,
) -> GameStateModel:
    """Fit pace factors from stint poss/sec; fall back to defaults."""
    model = default_game_state_model(config)
    rows: list[dict] = []
    seasons: list[str] = []
    for bundle in bundles:
        if stint_cache is not None and bundle.season in stint_cache:
            part = stint_cache[bundle.season]
        else:
            try:
                part = read_rows(settings, "lineup_stints", bundle.season)
            except Exception:
                part = []
            if stint_cache is not None:
                stint_cache[bundle.season] = part
        if not part:
            continue
        seasons.append(bundle.season)
        for row in part:
            if row["game_date"] >= as_of:
                continue
            rows.append(row)
    if len(rows) < 500:
        return model
    # Cap fit sample so walk-forward startup stays fast.
    if len(rows) > 30000:
        step = max(1, len(rows) // 30000)
        rows = rows[::step]

    # Aggregate possessions per minute by period × situation.
    sums: dict[tuple[int, str], list[float]] = defaultdict(list)
    for row in rows:
        period = int(row["period"])
        if period > 4:
            period = 4
        if period < 1:
            continue
        dur = float(row.get("duration_sec") or 0.0)
        poss = float(row.get("possessions") or 0.0)
        if dur < 20.0 or poss <= 0:
            continue
        rate = poss / (dur / 60.0)  # possessions per minute of stint
        margin = int(row.get("team_margin") or 0)
        abs_m = abs(margin)
        minutes_cfg = config.get("minutes", {})
        close = float(minutes_cfg.get("close_margin_threshold", 6.0))
        blowout = float(minutes_cfg.get("blowout_margin_threshold", 15.0))
        leading = margin > 0
        if abs_m >= blowout:
            sit = "blowout_lead" if leading else "blowout_trail"
        elif abs_m < close:
            sit = "lead" if leading else "trail"
        else:
            sit = "close"
        sums[(period, sit)].append(rate)

    # Baseline = moderate close Q1–Q2
    baseline_vals: list[float] = []
    for period in (1, 2):
        baseline_vals.extend(sums.get((period, "close"), []))
        baseline_vals.extend(sums.get((period, "lead"), []))
        baseline_vals.extend(sums.get((period, "trail"), []))
    baseline = float(np.median(baseline_vals)) if baseline_vals else 2.0
    if baseline <= 0:
        return model

    learned = dict(_DEFAULTS)
    for key, vals in sums.items():
        if len(vals) < 40:
            continue
        rate = float(np.median(vals))
        factor = float(np.clip(rate / baseline, 0.85, 1.20))
        # Blend with defaults so sparse cells stay sane.
        learned[key] = 0.55 * factor + 0.45 * _DEFAULTS.get(key, 1.0)
    model.pace_factor = learned
    model.source = "stints:" + ",".join(seasons)
    sim = config.get("simulation", {})
    if "intentional_foul_prob" in sim:
        model.intentional_foul_prob = float(sim["intentional_foul_prob"])
    return model
