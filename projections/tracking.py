"""Prior-season NBA tracking multipliers. Flags default off, so this is a no-op.

Shot creation, rebound chances, and passing are separate switches. Season S
reads season S-1 only.
"""

from __future__ import annotations

import pyarrow.parquet as pq

from projections.rates import RateVector

_FLAGS = (
    "tracking_shot_creation_enabled",
    "tracking_rebounds_enabled",
    "tracking_passing_enabled",
)


def prior_season(season: str) -> str:
    start = int(season.split("-", 1)[0]) - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _enabled(config: dict) -> bool:
    ctx = config.get("context") or {}
    return any(bool(ctx.get(name, False)) for name in _FLAGS)


def apply_tracking_rates(
    rates: RateVector,
    *,
    player_id: int,
    season: str,
    config: dict,
    cache,
    settings,
) -> RateVector:
    if not _enabled(config):
        return rates
    rows = cache.tracking_rows
    if rows is None:
        path = settings.data_dir / "external" / "tracking" / "player_tracking.parquet"
        rows = pq.read_table(path).to_pylist() if path.is_file() else []
        cache.tracking_rows = rows
    wanted = prior_season(season)
    row = next(
        (
            item
            for item in rows
            if str(item["season"]) == wanted and int(item["player_id"]) == int(player_id)
        ),
        None,
    )
    if row is None:
        return rates
    ctx = config.get("context") or {}
    usage = rates.usage
    oreb = rates.oreb_rate
    dreb = rates.dreb_rate
    ast = rates.ast_rate
    if bool(ctx.get("tracking_shot_creation_enabled", False)):
        usage *= _creation_factor(rows, wanted, row)
    if bool(ctx.get("tracking_rebounds_enabled", False)):
        scale = _vs_league(rows, wanted, row, "reb_chances", "minutes")
        oreb *= scale
        dreb *= scale
    if bool(ctx.get("tracking_passing_enabled", False)):
        ast *= _vs_league(rows, wanted, row, "potential_ast", "minutes")
    return RateVector(
        usage=min(0.45, max(0.05, usage)),
        tov_rate=rates.tov_rate,
        ft_rate=rates.ft_rate,
        ft_pct=rates.ft_pct,
        oreb_rate=min(0.25, max(0.0, oreb)),
        dreb_rate=min(0.40, max(0.0, dreb)),
        ast_rate=min(0.50, max(0.0, ast)),
        stl_rate=rates.stl_rate,
        blk_rate=rates.blk_rate,
        foul_rate=rates.foul_rate,
        restricted_area_share=rates.restricted_area_share,
        paint_non_ra_share=rates.paint_non_ra_share,
        midrange_share=rates.midrange_share,
        left_corner_3_share=rates.left_corner_3_share,
        right_corner_3_share=rates.right_corner_3_share,
        above_break_3_share=rates.above_break_3_share,
        restricted_area_fg_pct=rates.restricted_area_fg_pct,
        paint_non_ra_fg_pct=rates.paint_non_ra_fg_pct,
        midrange_fg_pct=rates.midrange_fg_pct,
        left_corner_3_fg_pct=rates.left_corner_3_fg_pct,
        right_corner_3_fg_pct=rates.right_corner_3_fg_pct,
        above_break_3_fg_pct=rates.above_break_3_fg_pct,
        sample_possessions=rates.sample_possessions,
        sample_games=rates.sample_games,
    )


def _creation_factor(rows: list[dict], season: str, row: dict) -> float:
    """Pull-up share of pull-up plus catch-and-shoot, versus the league."""

    def share(item: dict) -> tuple[float, float] | None:
        pull = float(item.get("pullup_fga") or 0.0)
        catch = float(item.get("catch_fga") or 0.0)
        total = pull + catch
        if total <= 0:
            return None
        return pull / total, total

    player = share(row)
    league_vals = [
        value[0]
        for item in rows
        if str(item["season"]) == season
        for value in [share(item)]
        if value is not None
    ]
    if player is None or not league_vals:
        return 1.0
    league = sum(league_vals) / len(league_vals)
    if league <= 0:
        return 1.0
    sample = player[1]
    shrunk = sample / (sample + 200.0)
    shift = shrunk * (player[0] / league - 1.0)
    return 1.0 + max(-0.02, min(0.02, 0.15 * shift))


def _vs_league(rows: list[dict], season: str, row: dict, numer: str, denom: str) -> float:
    def rate(item: dict) -> float | None:
        bottom = float(item.get(denom) or 0.0)
        if bottom <= 0:
            return None
        return float(item.get(numer) or 0.0) / bottom

    player = rate(row)
    league_vals = [
        value
        for item in rows
        if str(item["season"]) == season
        for value in [rate(item)]
        if value is not None
    ]
    if player is None or not league_vals:
        return 1.0
    league = sum(league_vals) / len(league_vals)
    if league <= 0:
        return 1.0
    sample = float(row.get(denom) or 0.0)
    shrunk = sample / (sample + 200.0)
    shift = shrunk * (player / league - 1.0)
    return 1.0 + max(-0.02, min(0.02, 0.15 * shift))
