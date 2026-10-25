"""Fetch and store compact Synergy play-type rates (nba_api SynergyPlayTypes).

Never persists raw API payloads. Current season refreshes at most once per day
(see ``context.play_types_fetch_interval_days``). Credit: stats.nba.com Synergy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from ingest.rosters import prior_season_label
from nba_sim.settings import Settings
from nba_sim.storage import read_rows, store_rows

LogFn = Callable[[str], None]

# (API PlayType param, canonical storage label)
PLAY_TYPE_SPECS: tuple[tuple[str, str], ...] = (
    ("Isolation", "Isolation"),
    ("PRBallHandler", "P&R Ball Handler"),
    ("PRRollman", "P&R Roll Man"),
    ("Postup", "Post Up"),
    ("Spotup", "Spot Up"),
    ("Handoff", "Handoff"),
    ("Cut", "Cut"),
    ("OffScreen", "Off Screen"),
    ("Transition", "Transition"),
    ("OffRebound", "Putbacks"),
    ("Misc", "Misc"),
)

PLAY_TYPES: tuple[str, ...] = tuple(label for _, label in PLAY_TYPE_SPECS)
SIDES: tuple[str, str] = ("offense", "defense")
ENTITY_KINDS: tuple[str, str] = ("player", "team")

DEFAULT_INTERVAL_DAYS = 1
DEFAULT_REGRESSION_POSS = 200.0
DEFAULT_SEASON_HALF_LIFE_POSS = 400.0


@dataclass(frozen=True)
class PlayTypeFetchStatus:
    fetched: bool
    skipped_fresh: bool
    seasons_written: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PlayTypeRates:
    """Per play-type offense (player) or defense (team) rates after regression."""

    mix: dict[str, float]  # frequency weights (sum ≈ 1 for offense mix)
    ppp: dict[str, float]
    tov_pct: dict[str, float]
    ft_pct: dict[str, float]
    score_pct: dict[str, float]
    possessions: dict[str, float]


def refresh_play_types(
    settings: Settings,
    *,
    seasons: Iterable[str] | None = None,
    log: LogFn = print,
    force: bool = False,
) -> PlayTypeFetchStatus:
    """Fetch Synergy play types; current season at most once per interval."""
    ctx = settings.config.get("context") or {}
    if not bool(ctx.get("play_types_enabled", True)):
        log("play_types fetch disabled (context.play_types_enabled=false)")
        return PlayTypeFetchStatus(
            fetched=False, skipped_fresh=False, seasons_written=(), warnings=()
        )

    interval = int(ctx.get("play_types_fetch_interval_days", DEFAULT_INTERVAL_DAYS))
    current = settings.current_season
    if seasons is None:
        # Default backfill window: 2023-24 through current.
        start_year = 2023
        cur_start = int(str(current).split("-")[0])
        targets = [f"{y}-{str(y + 1)[-2:]}" for y in range(start_year, cur_start + 1)]
    else:
        targets = [str(s).strip() for s in seasons if str(s).strip()]

    warnings: list[str] = []
    written: list[str] = []
    any_fetch = False
    skipped_fresh = False

    for season in targets:
        if (
            season == current
            and not force
            and _season_is_fresh(settings, season, interval_days=interval)
        ):
            log(f"play_types {season}: fresh (within {interval}d); skip")
            skipped_fresh = True
            continue
        try:
            rows = fetch_season_play_types(settings, season, log=log)
        except Exception as exc:  # noqa: BLE001 — never break daily
            msg = f"play_types {season} fetch failed: {exc}"
            log(f"WARNING: {msg}")
            warnings.append(msg)
            continue
        if not rows:
            msg = f"play_types {season}: empty response"
            log(f"WARNING: {msg}")
            warnings.append(msg)
            continue
        store_rows(
            settings,
            "play_types",
            season,
            rows,
            allow_historical=True,
        )
        log(f"play_types {season}: wrote {len(rows)} rows")
        written.append(season)
        any_fetch = True

    return PlayTypeFetchStatus(
        fetched=any_fetch,
        skipped_fresh=skipped_fresh and not any_fetch,
        seasons_written=tuple(written),
        warnings=tuple(warnings),
    )


def fetch_season_play_types(
    settings: Settings,
    season: str,
    *,
    log: LogFn = print,
) -> list[dict[str, Any]]:
    """Download all play-type slices for one season and collapse to compact rows."""
    http = settings.config.get("http") or {}
    delay = float(http.get("delay_seconds", 0.7))
    max_retries = int(http.get("max_retries", 3))
    backoff = float(http.get("backoff_seconds", 2.0))
    timeout = float(http.get("timeout_seconds", 60.0))
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    # Accumulate by key for multi-team player merges.
    acc: dict[tuple[str, int, str, str], dict[str, Any]] = {}
    import time

    for entity_kind, player_or_team in (("team", "T"), ("player", "P")):
        for side_api, side in (("offensive", "offense"), ("defensive", "defense")):
            for api_name, label in PLAY_TYPE_SPECS:
                frames = _synergy_request(
                    season=season,
                    player_or_team=player_or_team,
                    play_type=api_name,
                    type_grouping=side_api,
                    timeout=timeout,
                    max_retries=max_retries,
                    backoff=backoff,
                    log=log,
                )
                for raw in frames:
                    _merge_raw_row(
                        acc,
                        raw,
                        entity_kind=entity_kind,
                        play_type=label,
                        side=side,
                        season=season,
                        fetched_at=fetched_at,
                    )
                time.sleep(delay)

    return [_finalize_row(row) for row in acc.values()]


def rows_for_season(settings: Settings, season: str) -> list[dict[str, Any]]:
    try:
        return list(read_rows(settings, "play_types", season))
    except Exception:
        return []


def league_baselines(
    rows: list[dict[str, Any]],
    *,
    entity_kind: str,
    side: str,
) -> dict[str, dict[str, float]]:
    """Possession-weighted league averages keyed by play_type."""
    buckets: dict[str, dict[str, float]] = {}
    for row in rows:
        if str(row.get("entity_kind")) != entity_kind:
            continue
        if str(row.get("side")) != side:
            continue
        pt = str(row.get("play_type") or "")
        poss = float(row.get("possessions") or 0.0)
        if poss <= 0 or not pt:
            continue
        b = buckets.setdefault(
            pt,
            {"poss": 0.0, "ppp": 0.0, "tov": 0.0, "ft": 0.0, "score": 0.0, "freq": 0.0},
        )
        b["poss"] += poss
        b["ppp"] += poss * float(row.get("ppp") or 0.0)
        b["tov"] += poss * float(row.get("tov_pct") or 0.0)
        b["ft"] += poss * float(row.get("ft_pct") or 0.0)
        b["score"] += poss * float(row.get("score_pct") or 0.0)
        b["freq"] += poss * float(row.get("frequency") or 0.0)
    out: dict[str, dict[str, float]] = {}
    for pt, b in buckets.items():
        p = b["poss"]
        out[pt] = {
            "ppp": b["ppp"] / p,
            "tov_pct": b["tov"] / p,
            "ft_pct": b["ft"] / p,
            "score_pct": b["score"] / p,
            "frequency": b["freq"] / p,
            "possessions": p,
        }
    return out


def load_entity_rates(
    rows: list[dict[str, Any]],
    *,
    entity_kind: str,
    entity_id: int,
    side: str,
    league: dict[str, dict[str, float]],
    regression_possessions: float = DEFAULT_REGRESSION_POSS,
) -> PlayTypeRates | None:
    """Regress one entity's rates toward league by play type."""
    by_type: dict[str, dict[str, float]] = {}
    for row in rows:
        if str(row.get("entity_kind")) != entity_kind:
            continue
        if int(row.get("entity_id") or 0) != int(entity_id):
            continue
        if str(row.get("side")) != side:
            continue
        pt = str(row.get("play_type") or "")
        if not pt:
            continue
        by_type[pt] = {
            "possessions": float(row.get("possessions") or 0.0),
            "frequency": float(row.get("frequency") or 0.0),
            "ppp": float(row.get("ppp") or 0.0),
            "tov_pct": float(row.get("tov_pct") or 0.0),
            "ft_pct": float(row.get("ft_pct") or 0.0),
            "score_pct": float(row.get("score_pct") or 0.0),
        }
    if not by_type and not league:
        return None

    mix: dict[str, float] = {}
    ppp: dict[str, float] = {}
    tov: dict[str, float] = {}
    ft: dict[str, float] = {}
    score: dict[str, float] = {}
    poss_out: dict[str, float] = {}
    prior = max(1.0, float(regression_possessions))
    for pt in PLAY_TYPES:
        lg = league.get(pt) or {
            "ppp": 1.0,
            "tov_pct": 0.12,
            "ft_pct": 0.12,
            "score_pct": 0.45,
            "frequency": 1.0 / len(PLAY_TYPES),
        }
        raw = by_type.get(pt)
        if raw is None:
            mix[pt] = float(lg["frequency"])
            ppp[pt] = float(lg["ppp"])
            tov[pt] = float(lg["tov_pct"])
            ft[pt] = float(lg["ft_pct"])
            score[pt] = float(lg["score_pct"])
            poss_out[pt] = 0.0
            continue
        poss = float(raw["possessions"])
        w = poss / (poss + prior) if poss > 0 else 0.0
        mix[pt] = w * float(raw["frequency"]) + (1.0 - w) * float(lg["frequency"])
        ppp[pt] = w * float(raw["ppp"]) + (1.0 - w) * float(lg["ppp"])
        tov[pt] = w * float(raw["tov_pct"]) + (1.0 - w) * float(lg["tov_pct"])
        ft[pt] = w * float(raw["ft_pct"]) + (1.0 - w) * float(lg["ft_pct"])
        score[pt] = w * float(raw["score_pct"]) + (1.0 - w) * float(lg["score_pct"])
        poss_out[pt] = poss

    total_mix = sum(mix.values())
    if total_mix > 0:
        mix = {k: v / total_mix for k, v in mix.items()}
    return PlayTypeRates(
        mix=mix, ppp=ppp, tov_pct=tov, ft_pct=ft, score_pct=score, possessions=poss_out
    )


def blend_rates(
    current: PlayTypeRates | None,
    prior: PlayTypeRates | None,
    *,
    current_poss_total: float,
    half_life_possessions: float = DEFAULT_SEASON_HALF_LIFE_POSS,
) -> PlayTypeRates | None:
    """Blend current-season rates with prior; weight prior until sample grows."""
    if current is None:
        return prior
    if prior is None:
        return current
    half = max(1.0, float(half_life_possessions))
    w = float(current_poss_total) / (float(current_poss_total) + half)
    mix: dict[str, float] = {}
    ppp: dict[str, float] = {}
    tov: dict[str, float] = {}
    ft: dict[str, float] = {}
    score: dict[str, float] = {}
    poss: dict[str, float] = {}
    for pt in PLAY_TYPES:
        mix[pt] = w * current.mix.get(pt, 0.0) + (1.0 - w) * prior.mix.get(pt, 0.0)
        ppp[pt] = w * current.ppp.get(pt, 1.0) + (1.0 - w) * prior.ppp.get(pt, 1.0)
        tov[pt] = w * current.tov_pct.get(pt, 0.12) + (1.0 - w) * prior.tov_pct.get(
            pt, 0.12
        )
        ft[pt] = w * current.ft_pct.get(pt, 0.12) + (1.0 - w) * prior.ft_pct.get(pt, 0.12)
        score[pt] = w * current.score_pct.get(pt, 0.45) + (1.0 - w) * prior.score_pct.get(
            pt, 0.45
        )
        poss[pt] = current.possessions.get(pt, 0.0) + prior.possessions.get(pt, 0.0)
    total = sum(mix.values())
    if total > 0:
        mix = {k: v / total for k, v in mix.items()}
    return PlayTypeRates(
        mix=mix, ppp=ppp, tov_pct=tov, ft_pct=ft, score_pct=score, possessions=poss
    )


def matchup_factors(
    player_off: PlayTypeRates,
    team_def: PlayTypeRates,
    league_def: dict[str, dict[str, float]],
    *,
    weight: float,
) -> tuple[float, float, float]:
    """Return (fg_factor, tov_factor, ft_factor) softened by ``weight``.

    FG: player's mix × (own PPP vs play-type) relative to how well the defense
    allows PPP vs league. TOV/FT: mix × (opp rate / league rate).
    """
    if weight <= 0:
        return 1.0, 1.0, 1.0

    base_ppp = 0.0
    vs_ppp = 0.0
    tov_rel = 0.0
    ft_rel = 0.0
    for pt, w_mix in player_off.mix.items():
        if w_mix <= 0:
            continue
        lg = league_def.get(pt) or {"ppp": 1.0, "tov_pct": 0.12, "ft_pct": 0.12}
        lg_ppp = max(0.5, float(lg["ppp"]))
        lg_tov = max(0.02, float(lg["tov_pct"]))
        lg_ft = max(0.02, float(lg["ft_pct"]))
        def_ppp = max(0.5, float(team_def.ppp.get(pt, lg_ppp)))
        def_tov = max(0.02, float(team_def.tov_pct.get(pt, lg_tov)))
        def_ft = max(0.02, float(team_def.ft_pct.get(pt, lg_ft)))
        p_ppp = max(0.5, float(player_off.ppp.get(pt, lg_ppp)))
        base_ppp += w_mix * p_ppp
        # Defense that allows fewer PPP than league suppresses the player's PPP.
        vs_ppp += w_mix * p_ppp * (def_ppp / lg_ppp)
        tov_rel += w_mix * (def_tov / lg_tov)
        ft_rel += w_mix * (def_ft / lg_ft)

    if base_ppp <= 1e-9:
        raw_fg = 1.0
    else:
        raw_fg = vs_ppp / base_ppp
    # Soften toward 1.0: factor = raw ** weight, then clip.
    fg = _soft_factor(raw_fg, weight, lo=0.92, hi=1.08)
    tov = _soft_factor(tov_rel if tov_rel > 0 else 1.0, weight, lo=0.90, hi=1.12)
    ft = _soft_factor(ft_rel if ft_rel > 0 else 1.0, weight, lo=0.90, hi=1.12)
    return fg, tov, ft


def apply_play_type_factors(
    rates: Any,
    *,
    fg_factor: float,
    tov_factor: float,
    ft_factor: float,
) -> Any:
    """Multiply zone FG%, tov_rate, and ft_rate by matchup factors."""
    from dataclasses import replace

    from projections.rates import ZONES, RateVector

    if not isinstance(rates, RateVector):
        return rates
    if (
        abs(fg_factor - 1.0) < 1e-9
        and abs(tov_factor - 1.0) < 1e-9
        and abs(ft_factor - 1.0) < 1e-9
    ):
        return rates
    updates: dict[str, float] = {
        "tov_rate": min(0.30, max(0.02, float(rates.tov_rate) * tov_factor)),
        "ft_rate": min(0.45, max(0.02, float(rates.ft_rate) * ft_factor)),
    }
    for zone in ZONES:
        key = f"{zone}_fg_pct"
        base = float(getattr(rates, key))
        updates[key] = min(0.85, max(0.15, base * fg_factor))
    return replace(rates, **updates)


def play_type_season_for_projection(
    settings: Settings,
    *,
    season: str,
) -> tuple[str | None, str | None, bool]:
    """Return (primary_season, prior_season, blend_current).

    Walk-forward / non-current: previous season only (no leakage).
    Live current season: blend current with prior.
    """
    prior = prior_season_label(season)
    if season == settings.current_season:
        return season, prior, True
    return prior, None, False


def _soft_factor(raw: float, weight: float, *, lo: float, hi: float) -> float:
    # raw**weight with raw near 1; weight in (0,1] softens.
    w = max(0.0, min(1.0, float(weight)))
    if w <= 0:
        return 1.0
    value = float(raw) ** w
    return min(hi, max(lo, value))


def _season_is_fresh(settings: Settings, season: str, *, interval_days: int) -> bool:
    rows = rows_for_season(settings, season)
    if not rows:
        return False
    stamps = [str(r.get("fetched_at") or "") for r in rows if r.get("fetched_at")]
    if not stamps:
        return False
    newest = max(stamps)
    try:
        fetched = datetime.fromisoformat(newest.replace("Z", "+00:00"))
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    age = datetime.now(timezone.utc) - fetched
    return age.total_seconds() < float(interval_days) * 86400.0


def _synergy_request(
    *,
    season: str,
    player_or_team: str,
    play_type: str,
    type_grouping: str,
    timeout: float,
    max_retries: int,
    backoff: float,
    log: LogFn,
) -> list[dict[str, Any]]:
    import time

    from nba_api.stats.endpoints import synergyplaytypes as spt

    last_exc: Exception | None = None
    for attempt in range(max(1, max_retries)):
        try:
            ep = spt.SynergyPlayTypes(
                player_or_team_abbreviation=player_or_team,
                season=season,
                play_type_nullable=play_type,
                type_grouping_nullable=type_grouping,
                per_mode_simple="Totals",
                season_type_all_star="Regular Season",
                timeout=timeout,
            )
            df = ep.synergy_play_type.get_data_frame()
            if df is None or df.empty:
                return []
            # Drop raw frame immediately after converting — never store it.
            return df.to_dict("records")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log(
                f"play_types retry {attempt + 1}/{max_retries} "
                f"{season} {player_or_team}/{type_grouping}/{play_type}: {exc}"
            )
            time.sleep(backoff * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    return []


def _merge_raw_row(
    acc: dict[tuple[str, int, str, str], dict[str, Any]],
    raw: dict[str, Any],
    *,
    entity_kind: str,
    play_type: str,
    side: str,
    season: str,
    fetched_at: str,
) -> None:
    if entity_kind == "player":
        entity_id = int(raw.get("PLAYER_ID") or 0)
        name = str(raw.get("PLAYER_NAME") or f"player:{entity_id}")
        team_id = raw.get("TEAM_ID")
        team_id_i = int(team_id) if team_id is not None else None
    else:
        entity_id = int(raw.get("TEAM_ID") or 0)
        name = str(raw.get("TEAM_ABBREVIATION") or raw.get("TEAM_NAME") or entity_id)
        team_id_i = entity_id
    if entity_id <= 0:
        return
    poss = float(raw.get("POSS") or 0.0)
    if poss <= 0:
        return
    key = (entity_kind, entity_id, play_type, side)
    freq = float(raw.get("POSS_PCT") or 0.0)
    ppp = float(raw.get("PPP") or 0.0)
    tov = float(raw.get("TOV_POSS_PCT") or 0.0)
    ft = float(raw.get("FT_POSS_PCT") or 0.0)
    score = float(raw.get("SCORE_POSS_PCT") or 0.0)
    gp = float(raw.get("GP") or 0.0)
    existing = acc.get(key)
    if existing is None:
        acc[key] = {
            "season": season,
            "entity_kind": entity_kind,
            "entity_id": entity_id,
            "entity_name": name,
            "team_id": team_id_i,
            "play_type": play_type,
            "side": side,
            "_poss": poss,
            "_freq_w": freq * poss,
            "_ppp_w": ppp * poss,
            "_tov_w": tov * poss,
            "_ft_w": ft * poss,
            "_score_w": score * poss,
            "_gp": gp,
            "fetched_at": fetched_at,
        }
        return
    existing["_poss"] += poss
    existing["_freq_w"] += freq * poss
    existing["_ppp_w"] += ppp * poss
    existing["_tov_w"] += tov * poss
    existing["_ft_w"] += ft * poss
    existing["_score_w"] += score * poss
    existing["_gp"] = max(float(existing["_gp"]), gp)
    # Prefer the name/team from the larger sample chunk (already accumulated).
    if team_id_i is not None and entity_kind == "player":
        existing["team_id"] = team_id_i
        existing["entity_name"] = name


def _finalize_row(row: dict[str, Any]) -> dict[str, Any]:
    poss = float(row.pop("_poss", 0.0))
    return {
        "season": row["season"],
        "entity_kind": row["entity_kind"],
        "entity_id": int(row["entity_id"]),
        "entity_name": str(row["entity_name"]),
        "team_id": None if row.get("team_id") is None else int(row["team_id"]),
        "play_type": row["play_type"],
        "side": row["side"],
        "possessions": poss,
        "frequency": float(row.pop("_freq_w", 0.0)) / poss if poss else 0.0,
        "ppp": float(row.pop("_ppp_w", 0.0)) / poss if poss else 0.0,
        "tov_pct": float(row.pop("_tov_w", 0.0)) / poss if poss else 0.0,
        "ft_pct": float(row.pop("_ft_w", 0.0)) / poss if poss else 0.0,
        "score_pct": float(row.pop("_score_w", 0.0)) / poss if poss else 0.0,
        "gp": float(row.pop("_gp", 0.0)),
        "fetched_at": row["fetched_at"],
    }
