"""Compact defender impact aggregates from NBA matchup endpoints.

Stores per-defender FG% allowed (overall + 3PT), never raw matchup rows.
Walk-forward must only use prior-season partitions (season aggregates leak
same-season results).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def defender_impact_from_league_matchups(
    season: str,
    rows: list[dict[str, Any]],
) -> list[dict]:
    """Collapse LeagueSeasonMatchups OFF×DEF rows into per-defender totals."""
    totals: dict[int, dict[str, float]] = defaultdict(
        lambda: {
            "possessions": 0.0,
            "fga": 0.0,
            "fgm": 0.0,
            "fg3a": 0.0,
            "fg3m": 0.0,
            "pts": 0.0,
            "matchup_sec": 0.0,
        }
    )
    names: dict[int, str] = {}
    for row in rows:
        def_id = _int(row.get("DEF_PLAYER_ID") or row.get("def_player_id"))
        if def_id is None:
            continue
        names[def_id] = str(
            row.get("DEF_PLAYER_NAME") or row.get("def_player_name") or ""
        )
        bucket = totals[def_id]
        bucket["possessions"] += float(row.get("PARTIAL_POSS") or row.get("partial_poss") or 0.0)
        bucket["fga"] += float(row.get("MATCHUP_FGA") or row.get("matchup_fga") or 0.0)
        bucket["fgm"] += float(row.get("MATCHUP_FGM") or row.get("matchup_fgm") or 0.0)
        bucket["fg3a"] += float(row.get("MATCHUP_FG3A") or row.get("matchup_fg3a") or 0.0)
        bucket["fg3m"] += float(row.get("MATCHUP_FG3M") or row.get("matchup_fg3m") or 0.0)
        bucket["pts"] += float(row.get("PLAYER_PTS") or row.get("player_pts") or 0.0)
        bucket["matchup_sec"] += float(
            row.get("MATCHUP_TIME_SEC") or row.get("matchup_time_sec") or 0.0
        )
    out: list[dict] = []
    for def_id, bucket in sorted(totals.items()):
        fga = bucket["fga"]
        fg3a = bucket["fg3a"]
        out.append(
            {
                "season": season,
                "defender_id": def_id,
                "defender_name": names.get(def_id) or f"player:{def_id}",
                "possessions": bucket["possessions"],
                "fga": fga,
                "fgm": bucket["fgm"],
                "fg3a": fg3a,
                "fg3m": bucket["fg3m"],
                "pts": bucket["pts"],
                "matchup_sec": bucket["matchup_sec"],
                "fg_pct": (bucket["fgm"] / fga) if fga > 0 else None,
                "fg3_pct": (bucket["fg3m"] / fg3a) if fg3a > 0 else None,
            }
        )
    return out


def primary_defender_weights(
    *,
    offense_positions: list[str | None],
    defense_positions: list[str | None],
    defense_minutes: list[float],
) -> list[list[float]]:
    """Soft assignment weights: each offensive slot → 5 defensive slots.

    Prefer same/adjacent position; fall back to minutes share.
    """
    n_off = len(offense_positions)
    n_def = len(defense_positions)
    weights = [[0.0] * n_def for _ in range(n_off)]
    min_arr = [max(0.0, float(m)) for m in defense_minutes]
    min_sum = sum(min_arr) or 1.0
    for i, off_pos in enumerate(offense_positions):
        scores = []
        for j, def_pos in enumerate(defense_positions):
            pos_score = _position_affinity(off_pos, def_pos)
            min_score = min_arr[j] / min_sum
            scores.append(0.65 * pos_score + 0.35 * min_score)
        total = sum(scores) or 1.0
        weights[i] = [s / total for s in scores]
    return weights


def _position_affinity(off: str | None, deff: str | None) -> float:
    o = _norm_pos(off)
    d = _norm_pos(deff)
    if o is None or d is None:
        return 0.35
    if o == d:
        return 1.0
    adjacent = {
        "PG": {"SG"},
        "SG": {"PG", "SF"},
        "SF": {"SG", "PF"},
        "PF": {"SF", "C"},
        "C": {"PF"},
    }
    if d in adjacent.get(o, set()):
        return 0.55
    return 0.15


def _norm_pos(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).upper().strip()
    if text in {"PG", "SG", "SF", "PF", "C"}:
        return text
    if text in {"G", "GUARD"}:
        return "SG"
    if text in {"F", "FORWARD"}:
        return "SF"
    if text in {"C-F", "F-C"}:
        return "PF"
    if text in {"G-F", "F-G"}:
        return "SF"
    return None


def _int(value) -> int | None:
    if value is None or value == "" or str(value) == "0":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
