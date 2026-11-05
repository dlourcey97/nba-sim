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


# Exclusive offensive buckets. A top scorer is a scorer even at center, because
# the share is "time spent on the other team's scorers," not his listed position.
_BUCKETS = ("scorer", "wing", "big")
# Prior-season points per game. Twenty games keeps a short sample from qualifying.
SCORER_PPG = 18.0
SCORER_MIN_GAMES = 20


def scorer_ids_from_logs(rows: list[dict[str, Any]]) -> set[int]:
    """Players at or above 18 points per game over at least 20 appearances."""
    points: dict[int, float] = defaultdict(float)
    games: dict[int, int] = defaultdict(int)
    for row in rows:
        if float(row.get("minutes") or 0.0) <= 0.0:
            continue
        player_id = _int(row.get("player_id"))
        if player_id is None:
            continue
        points[player_id] += float(row.get("pts") or 0.0)
        games[player_id] += 1
    return {
        player_id
        for player_id, played in games.items()
        if played >= SCORER_MIN_GAMES and points[player_id] / played >= SCORER_PPG
    }


def offensive_bucket(position: str | None, *, is_scorer: bool) -> str:
    """Classify who the defender was matched up with.

    Top scorers are their own group. Everyone else is a big (center or power
    forward) or a wing (guards and small forwards, including an unknown spot).
    """
    if is_scorer:
        return "scorer"
    if _norm_pos(position) in {"C", "PF"}:
        return "big"
    return "wing"


def buckets_from_logs(rows: list[dict[str, Any]]) -> dict[int, str]:
    """Bucket every player who appeared, using his most common listed position."""
    scorers = scorer_ids_from_logs(rows)
    counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        player_id = _int(row.get("player_id"))
        if player_id is None:
            continue
        position = row.get("position")
        if position:
            counts[player_id][str(position)] += 1
    buckets: dict[int, str] = {}
    seen = set(counts) | scorers
    for player_id in seen:
        position = None
        if counts[player_id]:
            position = max(counts[player_id], key=counts[player_id].get)
        buckets[player_id] = offensive_bucket(position, is_scorer=player_id in scorers)
    return buckets


def matchup_shares_from_league_matchups(
    season: str,
    rows: list[dict[str, Any]],
    *,
    buckets_by_offense_id: dict[int, str],
) -> list[dict]:
    """Compact share of each defender's matchup seconds by offensive bucket.

    Raw OFF×DEF rows are not stored. An offensive player missing from
    ``buckets_by_offense_id`` is skipped, so an unknown name is not dumped
    into a bucket. Shares are zero when the defender has no classified seconds.
    """
    seconds: dict[int, dict[str, float]] = defaultdict(
        lambda: {bucket: 0.0 for bucket in _BUCKETS}
    )
    names: dict[int, str] = {}
    for row in rows:
        def_id = _int(row.get("DEF_PLAYER_ID") or row.get("def_player_id"))
        off_id = _int(row.get("OFF_PLAYER_ID") or row.get("off_player_id"))
        if def_id is None or off_id is None:
            continue
        bucket = buckets_by_offense_id.get(off_id)
        if bucket not in _BUCKETS:
            continue
        names[def_id] = str(
            row.get("DEF_PLAYER_NAME") or row.get("def_player_name") or names.get(def_id, "")
        )
        seconds[def_id][bucket] += _matchup_seconds(row)
    out: list[dict] = []
    for def_id, bucket_seconds in sorted(seconds.items()):
        total = float(sum(bucket_seconds.values()))
        row = {
            "season": season,
            "defender_id": def_id,
            "defender_name": names.get(def_id) or f"player:{def_id}",
            "matchup_sec": total,
        }
        for bucket in _BUCKETS:
            row[f"share_{bucket}"] = (
                float(bucket_seconds[bucket]) / total if total > 0.0 else 0.0
            )
        out.append(row)
    return out


def bucket_weights(
    shares: list[tuple[float, float, float] | None],
    affinity: list[float],
    bucket: str,
    *,
    observed_weight: float = 0.65,
) -> list[float]:
    """Weight the on-court defenders for one offensive bucket.

    ``shares`` is (scorer, wing, big) for each defender, or None when he has
    no history. Missing history stays on position affinity. The result sums
    to 1. Call it again next possession; nothing here locks a matchup.
    """
    index = _BUCKETS.index(bucket)
    observed = min(1.0, max(0.0, float(observed_weight)))
    raw_aff = [max(0.0, float(value)) for value in affinity]
    aff_total = sum(raw_aff)
    if aff_total <= 0.0:
        n = len(raw_aff) or 1
        norm_aff = [1.0 / n for _ in raw_aff]
    else:
        norm_aff = [value / aff_total for value in raw_aff]
    mixed: list[float] = []
    for share, base in zip(shares, norm_aff):
        if share is None:
            mixed.append(base)
            continue
        mixed.append(observed * max(0.0, float(share[index])) + (1.0 - observed) * base)
    total = sum(mixed)
    if total <= 0.0:
        n = len(mixed) or 1
        return [1.0 / n for _ in mixed]
    return [value / total for value in mixed]


def _matchup_seconds(row: dict[str, Any]) -> float:
    seconds = row.get("MATCHUP_TIME_SEC")
    if seconds is None:
        seconds = row.get("matchup_time_sec")
    if seconds is None:
        seconds = row.get("PARTIAL_POSS") or row.get("partial_poss") or 0.0
    return max(0.0, float(seconds))


def _int(value) -> int | None:
    if value is None or value == "" or str(value) == "0":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
