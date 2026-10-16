"""Per-possession rate vectors used by blending and the simulator."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from nba_sim.schema import POSITIONS_5, ZONES

RATE_FIELDS = (
    "usage",
    "tov_rate",
    "ft_rate",
    "ft_pct",
    "oreb_rate",
    "dreb_rate",
    "ast_rate",
    "stl_rate",
    "blk_rate",
    "foul_rate",
) + tuple(f"{zone}_share" for zone in ZONES) + tuple(f"{zone}_fg_pct" for zone in ZONES)


@dataclass
class RateVector:
    """Per-possession / conditional rates for one player."""

    usage: float = 0.20
    tov_rate: float = 0.12
    ft_rate: float = 0.10
    ft_pct: float = 0.75
    oreb_rate: float = 0.05
    dreb_rate: float = 0.15
    ast_rate: float = 0.15
    stl_rate: float = 0.015
    blk_rate: float = 0.010
    foul_rate: float = 0.08
    restricted_area_share: float = 0.30
    paint_non_ra_share: float = 0.15
    midrange_share: float = 0.15
    left_corner_3_share: float = 0.05
    right_corner_3_share: float = 0.05
    above_break_3_share: float = 0.30
    restricted_area_fg_pct: float = 0.65
    paint_non_ra_fg_pct: float = 0.40
    midrange_fg_pct: float = 0.40
    left_corner_3_fg_pct: float = 0.38
    right_corner_3_fg_pct: float = 0.38
    above_break_3_fg_pct: float = 0.35
    sample_possessions: float = 0.0
    sample_games: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in RATE_FIELDS}

    @classmethod
    def from_dict(cls, values: dict[str, float], **extra: float) -> RateVector:
        payload = {name: float(values.get(name, getattr(cls(), name))) for name in RATE_FIELDS}
        payload.update(extra)
        return cls(**payload)

    def normalize_shares(self) -> RateVector:
        total = sum(getattr(self, f"{zone}_share") for zone in ZONES)
        if total <= 0:
            equal = 1.0 / len(ZONES)
            return replace(self, **{f"{zone}_share": equal for zone in ZONES})
        return replace(self, **{f"{zone}_share": getattr(self, f"{zone}_share") / total for zone in ZONES})


def empty_accumulator() -> dict[str, float]:
    return {
        "possessions": 0.0,
        "used": 0.0,
        "tov": 0.0,
        "fta": 0.0,
        "ftm": 0.0,
        "oreb_chances": 0.0,
        "oreb": 0.0,
        "dreb_chances": 0.0,
        "dreb": 0.0,
        "ast_chances": 0.0,
        "ast": 0.0,
        "stl": 0.0,
        "blk": 0.0,
        "games": 0.0,
        **{f"{zone}_fga": 0.0 for zone in ZONES},
        **{f"{zone}_fgm": 0.0 for zone in ZONES},
    }


def add_game_to_accumulator(
    acc: dict[str, float],
    *,
    rate_row: dict,
    log_row: dict | None,
    weight: float,
) -> None:
    if weight <= 0:
        return
    possessions = float(rate_row.get("possessions") or 0.0)
    if possessions <= 0:
        return
    usage = float(rate_row.get("usage") or 0.0)
    used = usage * possessions
    acc["possessions"] += weight * possessions
    acc["used"] += weight * used
    acc["games"] += weight
    acc["fta"] += weight * float(rate_row.get("fta") or 0.0)
    acc["ftm"] += weight * float(rate_row.get("ftm") or 0.0)
    acc["oreb_chances"] += weight * float(rate_row.get("oreb_chances") or 0.0)
    acc["dreb_chances"] += weight * float(rate_row.get("dreb_chances") or 0.0)
    acc["ast_chances"] += weight * float(rate_row.get("ast_chances") or 0.0)
    for zone in ZONES:
        acc[f"{zone}_fga"] += weight * float(rate_row.get(f"{zone}_fga") or 0.0)
        acc[f"{zone}_fgm"] += weight * float(rate_row.get(f"{zone}_fgm") or 0.0)
    if log_row is not None:
        acc["tov"] += weight * float(log_row.get("tov") or 0.0)
        acc["stl"] += weight * float(log_row.get("stl") or 0.0)
        acc["blk"] += weight * float(log_row.get("blk") or 0.0)
        acc["oreb"] += weight * float(log_row.get("oreb") or 0.0)
        acc["dreb"] += weight * float(log_row.get("dreb") or 0.0)
        acc["ast"] += weight * float(log_row.get("ast") or 0.0)


def vector_from_accumulator(acc: dict[str, float]) -> RateVector:
    possessions = acc["possessions"]
    if possessions <= 0:
        return RateVector()
    used = acc["used"]
    fga_total = sum(acc[f"{zone}_fga"] for zone in ZONES)
    shares = {}
    pcts = {}
    for zone in ZONES:
        fga = acc[f"{zone}_fga"]
        fgm = acc[f"{zone}_fgm"]
        shares[f"{zone}_share"] = (fga / fga_total) if fga_total > 0 else 1.0 / len(ZONES)
        pcts[f"{zone}_fg_pct"] = (fgm / fga) if fga > 0 else getattr(RateVector(), f"{zone}_fg_pct")
    oreb_chances = acc["oreb_chances"]
    dreb_chances = acc["dreb_chances"]
    ast_chances = acc["ast_chances"]
    fta = acc["fta"]
    vector = RateVector(
        usage=used / possessions,
        tov_rate=(acc["tov"] / used) if used > 0 else 0.12,
        ft_rate=(fta / used) if used > 0 else 0.10,
        ft_pct=(acc["ftm"] / fta) if fta > 0 else 0.75,
        oreb_rate=(acc["oreb"] / oreb_chances) if oreb_chances > 0 else 0.05,
        dreb_rate=(acc["dreb"] / dreb_chances) if dreb_chances > 0 else 0.15,
        ast_rate=(acc["ast"] / ast_chances) if ast_chances > 0 else 0.15,
        stl_rate=acc["stl"] / possessions,
        blk_rate=acc["blk"] / possessions,
        foul_rate=0.08,
        sample_possessions=possessions,
        sample_games=acc["games"],
        **shares,
        **pcts,
    )
    return vector.normalize_shares()


def blend_vectors(
    vectors: list[tuple[RateVector, float]],
    *,
    prior: RateVector | None = None,
    prior_strength: float = 0.0,
) -> RateVector:
    """Weighted average of rate vectors, optionally shrunk toward a prior."""
    if not vectors and prior is None:
        return RateVector()
    weights = []
    items = []
    for vector, weight in vectors:
        if weight <= 0:
            continue
        items.append(vector)
        weights.append(float(weight))
    if prior is not None and prior_strength > 0:
        items.append(prior)
        weights.append(float(prior_strength))
    if not items:
        return prior.normalize_shares() if prior is not None else RateVector()
    total = sum(weights)
    merged: dict[str, float] = {}
    for name in RATE_FIELDS:
        merged[name] = sum(getattr(item, name) * weight for item, weight in zip(items, weights)) / total
    sample_poss = sum(item.sample_possessions * weight for item, weight in zip(items, weights)) / total
    sample_games = sum(item.sample_games * weight for item, weight in zip(items, weights)) / total
    return RateVector.from_dict(merged, sample_possessions=sample_poss, sample_games=sample_games).normalize_shares()


def position_bucket(position: str | None) -> str:
    if not position:
        return "G"
    value = position.strip().upper()
    if value.startswith("C") or value in {"C", "C-F", "F-C"}:
        return "C"
    if value.startswith("F") or value in {"F", "F-G", "G-F", "SF", "PF"}:
        return "F"
    return "G"


def five_position(
    position: str | None,
    *,
    reb: float = 0.0,
    ast: float = 0.0,
    minutes: float = 0.0,
) -> str:
    """Map listed position (often G/F/C) onto PG/SG/SF/PF/C.

    Box scores usually only stamp starters as G/F/C. When the label is coarse
    or missing, reb/ast from that appearance pick the five-position bucket used
    for opponent defense allowed-to-position stats.
    """
    raw = (position or "").strip().upper()
    if raw in POSITIONS_5:
        return raw
    if raw in {"POINT GUARD", "PG"}:
        return "PG"
    if raw in {"SHOOTING GUARD", "SG"}:
        return "SG"
    if raw in {"SMALL FORWARD", "SF"}:
        return "SF"
    if raw in {"POWER FORWARD", "PF"}:
        return "PF"
    if raw in {"CENTER", "C"} or raw.startswith("C"):
        return "C"
    if raw in {"G", "G-F", "F-G"} or raw.startswith("G"):
        return "PG" if float(ast) >= max(float(reb), 3.0) else "SG"
    if raw in {"F", "F-C", "C-F"} or raw.startswith("F"):
        return "PF" if float(reb) >= 6.0 else "SF"
    # No listed position: infer from the box line.
    if float(minutes) <= 0:
        return "SF"
    if float(reb) >= 10.0 and float(ast) <= 3.0:
        return "C"
    if float(ast) >= 5.0:
        return "PG"
    if float(reb) >= 7.0:
        return "PF"
    if float(reb) >= 5.0:
        return "SF"
    return "SG"
