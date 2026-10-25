"""Ridge-regularized adjusted plus-minus from lineup stints.

Fits player net ratings with (X'WX + λI)β = X'Wy, choosing λ by out-of-sample
MSE on a held-out date slice. Team strength is the minutes-weighted mean of
tonight's roster ratings mapped onto ORtg/DRtg.
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
from projections.context import TeamStrength


@dataclass
class RapmModel:
    """Player net ratings (points per 100 possessions vs average)."""

    ratings: dict[int, float] = field(default_factory=dict)
    lambda_: float = 1000.0
    source: str = "defaults"
    oos_mse: float = 0.0

    def player_rating(self, player_id: int) -> float:
        return float(self.ratings.get(int(player_id), 0.0))

    def roster_net(
        self,
        players: Sequence[tuple[int, float]],
    ) -> float:
        """Minutes-weighted mean RAPM for a projected rotation."""
        total = 0.0
        weight = 0.0
        for player_id, minutes in players:
            minutes = float(max(0.0, minutes))
            if minutes <= 0:
                continue
            total += minutes * self.player_rating(int(player_id))
            weight += minutes
        if weight <= 0:
            return 0.0
        return float(total / weight)

    def team_strength(
        self,
        players: Sequence[tuple[int, float]],
        *,
        league: TeamStrength,
        prior: TeamStrength | None = None,
        current: TeamStrength | None = None,
        current_games: int = 0,
        config: dict[str, Any] | None = None,
    ) -> TeamStrength:
        """Map roster RAPM onto ORtg/DRtg and blend with current-season results."""
        ctx = (config or {}).get("context", {})
        half_life = float(ctx.get("team_strength_half_life", 20.0))
        rapm_w = float(ctx.get("rapm_strength_weight", 0.55))
        # Opening weeks: trust prior-season team strength over noisy RAPM of a
        # 2-game rotation (and over SOS-unaware early form baked into RAPM).
        rapm_hl = float(ctx.get("rapm_blend_half_life", 10.0))
        if rapm_hl > 0:
            g = max(0, int(current_games))
            rapm_w = rapm_w * (g / (g + rapm_hl))
        net = self.roster_net(players)
        # Split net evenly between offense and defense.
        base_ortg = prior.ortg if prior is not None else league.ortg
        base_drtg = prior.drtg if prior is not None else league.drtg
        rapm_ortg = league.ortg + 0.5 * net
        rapm_drtg = league.drtg - 0.5 * net
        roster_ortg = (1.0 - rapm_w) * base_ortg + rapm_w * rapm_ortg
        roster_drtg = (1.0 - rapm_w) * base_drtg + rapm_w * rapm_drtg
        if current is not None and current_games > 0 and half_life > 0:
            w = current_games / (current_games + half_life)
            ortg = (1.0 - w) * roster_ortg + w * current.ortg
            drtg = (1.0 - w) * roster_drtg + w * current.drtg
        else:
            ortg = roster_ortg
            drtg = roster_drtg
        return TeamStrength(ortg=float(ortg), drtg=float(drtg))


def load_rapm_model(
    settings: Settings,
    bundles: Sequence[SeasonBundle],
    *,
    as_of: date,
    config: dict[str, Any],
    stint_cache: dict[str, list] | None = None,
) -> RapmModel:
    """Load RAPM ratings for roster strength.

    Prefer published nbarapm.com time-decay RAPM when enabled and present under
    ``DATA_DIR/external/`` (see ``ingest/rapm_fetch.py``). Otherwise fit ridge
    RAPM from stints, then box-score plus-minus shrinkage.
    """
    ctx = config.get("context") or {}
    if bool(ctx.get("nbarapm_prefer_external", True)):
        try:
            from ingest.rapm_fetch import load_timedecay_ratings, load_timedecay_source_updated

            ratings = load_timedecay_ratings(settings)
        except Exception:
            ratings = {}
        if len(ratings) >= 50:
            updated = None
            try:
                updated = load_timedecay_source_updated(settings)
            except Exception:
                updated = None
            src = "nbarapm.com/timedecay"
            if updated is not None:
                src = f"{src}:{updated.isoformat()}"
            return RapmModel(ratings=ratings, lambda_=0.0, source=src, oos_mse=0.0)

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
            if row.get("plus_minus") is None:
                continue
            rows.append(row)

    if len(rows) >= 800:
        model = _fit_stint_rapm(rows, config=config)
        model.source = "stints:" + ",".join(seasons)
        return model

    return _fit_box_rapm(bundles, as_of=as_of, config=config)


def _fit_stint_rapm(rows: list[dict], *, config: dict[str, Any]) -> RapmModel:
    ctx = config.get("context", {})
    lambdas = [
        float(x)
        for x in ctx.get("rapm_lambdas", [200.0, 500.0, 1000.0, 2000.0, 5000.0])
    ]
    # Sort by date for chronological OOS split.
    rows = sorted(rows, key=lambda r: (r["game_date"], str(r["game_id"])))
    if len(rows) > 40000:
        step = max(1, len(rows) // 40000)
        rows = rows[::step]

    players = sorted(
        {
            int(row[f"p{i}"])
            for row in rows
            for i in range(1, 6)
        }
    )
    index = {pid: j for j, pid in enumerate(players)}
    n = len(players)
    if n == 0:
        return RapmModel(source="empty")

    # Chronological holdout for lambda selection.
    split = int(len(rows) * 0.85)
    train_rows = rows[: max(split, 1)]
    test_rows = rows[split:] if split < len(rows) else rows[-max(1, len(rows) // 10) :]

    best_lam = lambdas[0]
    best_mse = float("inf")
    best_beta = np.zeros(n)
    for lam in lambdas:
        beta = _ridge_from_stints(train_rows, index, n, lam)
        mse = _stint_mse(test_rows, index, beta)
        if mse < best_mse:
            best_mse = mse
            best_lam = lam
            best_beta = beta

    # Refit on all rows with chosen lambda.
    beta = _ridge_from_stints(rows, index, n, best_lam)
    ratings = {pid: float(beta[index[pid]]) for pid in players}
    return RapmModel(
        ratings=ratings,
        lambda_=float(best_lam),
        oos_mse=float(best_mse),
        source="stints",
    )


def _ridge_from_stints(
    rows: list[dict],
    index: dict[int, int],
    n: int,
    lam: float,
) -> np.ndarray:
    xtx = np.zeros((n, n), dtype=float)
    xty = np.zeros(n, dtype=float)
    for row in rows:
        poss = float(row.get("possessions") or 0.0)
        if poss < 1.0:
            # Duration-based weight when possession counter is sparse.
            poss = max(float(row.get("duration_sec") or 0.0) / 24.0, 0.5)
        pm = float(row.get("plus_minus") or 0.0)
        y = 100.0 * pm / poss
        ids = [index[int(row[f"p{i}"])] for i in range(1, 6) if int(row[f"p{i}"]) in index]
        if len(ids) < 5:
            continue
        w = poss
        for a in ids:
            xty[a] += w * y
            for b in ids:
                xtx[a, b] += w
    xtx.flat[:: n + 1] += float(lam)
    try:
        return np.linalg.solve(xtx, xty)
    except np.linalg.LinAlgError:
        return np.linalg.lstsq(xtx, xty, rcond=None)[0]


def _stint_mse(rows: list[dict], index: dict[int, int], beta: np.ndarray) -> float:
    if not rows:
        return float("inf")
    err = 0.0
    weight = 0.0
    for row in rows:
        poss = float(row.get("possessions") or 0.0)
        if poss < 1.0:
            poss = max(float(row.get("duration_sec") or 0.0) / 24.0, 0.5)
        pm = float(row.get("plus_minus") or 0.0)
        y = 100.0 * pm / poss
        ids = [index[int(row[f"p{i}"])] for i in range(1, 6) if int(row[f"p{i}"]) in index]
        if len(ids) < 5:
            continue
        pred = float(sum(beta[j] for j in ids))
        err += poss * (pred - y) ** 2
        weight += poss
    if weight <= 0:
        return float("inf")
    return float(err / weight)


def _fit_box_rapm(
    bundles: Sequence[SeasonBundle],
    *,
    as_of: date,
    config: dict[str, Any],
) -> RapmModel:
    """Shrinkage estimator from box-score plus-minus when stint PM is missing."""
    ctx = config.get("context", {})
    lam = float(ctx.get("rapm_box_lambda", 400.0))
    sums: dict[int, float] = defaultdict(float)
    minutes: dict[int, float] = defaultdict(float)
    for bundle in bundles:
        for player_id, logs in bundle.logs_by_player.items():
            for row in logs:
                if row["game_date"] >= as_of:
                    break
                mins = float(row.get("minutes") or 0.0)
                if mins <= 0:
                    continue
                pm = row.get("plus_minus")
                if pm is None:
                    continue
                # Convert game PM to per-100-possession scale (~ pace 100).
                sums[int(player_id)] += float(pm) * (100.0 / max(mins, 1.0))
                minutes[int(player_id)] += mins
    ratings = {}
    for pid, total in sums.items():
        m = minutes[pid]
        raw = total / m if m > 0 else 0.0
        # Ridge-like shrink: β = (x'x)/(x'x+λ) * mean
        ratings[pid] = float(raw * (m / (m + lam)))
    return RapmModel(ratings=ratings, lambda_=lam, source="box_scores")
