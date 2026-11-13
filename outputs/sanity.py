"""Plausibility checks on a slate's projected medians. Does not change the sim."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ingest.injuries import InjuryEntry
from outputs.summarize import GameSummary

CHECK_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "min")
# An unexplained flag on these removes the player from the post-sim play card.
QUARANTINE_STATS = frozenset({"pts", "reb", "ast", "min"})
# Percent test is noise when the recent average is a fraction of a stat.
_MIN_RECENT = {"pts": 2.0, "reb": 1.5, "ast": 1.0, "fg3m": 0.8, "stl": 0.8, "blk": 0.8, "min": 8.0}
_TEAMMATE_OUT = {
    "pts": 10.0,
    "reb": 5.0,
    "ast": 3.0,
    "fg3m": 1.5,
    "stl": 1.0,
    "blk": 1.0,
    "min": 18.0,
}


@dataclass
class StatBenchmark:
    last10: float | None = None
    per_minute: float | None = None
    career_per36: float | None = None
    n: int = 0


@dataclass
class SanityFlag:
    player_id: int
    player_name: str
    team_abbr: str
    stat: str
    median: float
    detail: str
    explanation: str | None
    quarantined: bool


@dataclass
class SanityReport:
    flags: list[SanityFlag] = field(default_factory=list)

    @property
    def quarantined_ids(self) -> set[int]:
        return {flag.player_id for flag in self.flags if flag.quarantined}

    def lines(self) -> list[str]:
        if not self.flags:
            return ["No projection failed the plausibility check."]
        out: list[str] = []
        for flag in self.flags:
            mark = "QUARANTINE" if flag.quarantined else "FLAG"
            why = flag.explanation or "no injury or role change explains it"
            out.append(
                f"{mark} {flag.team_abbr} {flag.player_name} {flag.stat.upper()} "
                f"median {flag.median:.1f}: {flag.detail}. {why}."
            )
        return out


def benchmarks_from_logs(logs: list[dict]) -> dict[int, dict[str, StatBenchmark]]:
    """Last-10 average, per-minute rate, and career high per 36 from box logs."""
    by_player: dict[int, list[dict]] = {}
    for row in logs:
        minutes = float(row.get("minutes") or 0.0)
        if minutes <= 0.0:
            continue
        by_player.setdefault(int(row["player_id"]), []).append(row)
    out: dict[int, dict[str, StatBenchmark]] = {}
    for player_id, rows in by_player.items():
        rows.sort(key=lambda item: str(item.get("game_date") or ""))
        recent = rows[-10:]
        bench: dict[str, StatBenchmark] = {}
        recent_minutes = sum(float(item.get("minutes") or 0.0) for item in recent)
        for stat in CHECK_STATS:
            column = "minutes" if stat == "min" else stat
            values = [float(item.get(column) or 0.0) for item in recent]
            last10 = sum(values) / len(values) if values else None
            per_minute = None
            if stat != "min" and recent_minutes > 0:
                per_minute = sum(values) / recent_minutes
            career = None
            for item in rows:
                played = float(item.get("minutes") or 0.0)
                if played < 15.0:
                    continue
                if stat == "min":
                    per = played
                else:
                    per = float(item.get(column) or 0.0) * 36.0 / played
                career = per if career is None else max(career, per)
            bench[stat] = StatBenchmark(
                last10=last10, per_minute=per_minute, career_per36=career, n=len(recent)
            )
        out[player_id] = bench
    return out


def _out_statuses(injuries: list[InjuryEntry], game_date: date) -> dict[int, InjuryEntry]:
    out: dict[int, InjuryEntry] = {}
    for entry in injuries:
        if entry.game_date != game_date or entry.player_id is None:
            continue
        status = (entry.status or "").upper()
        if "OUT" in status or "DOUBT" in status:
            out[int(entry.player_id)] = entry
    return out


def _own_status(injuries: list[InjuryEntry], game_date: date) -> dict[int, InjuryEntry]:
    found: dict[int, InjuryEntry] = {}
    for entry in injuries:
        if entry.game_date == game_date and entry.player_id is not None:
            found[int(entry.player_id)] = entry
    return found


def _teammate_explanation(
    *,
    stat: str,
    high: bool,
    team_abbr: str,
    player_id: int,
    summaries: list[GameSummary],
    outs: dict[int, InjuryEntry],
    benchmarks: dict[int, dict[str, StatBenchmark]],
) -> str | None:
    if not high:
        return None
    threshold = _TEAMMATE_OUT[stat]
    names: list[str] = []
    for summary in summaries:
        for player in summary.players:
            if player.team_abbr != team_abbr or player.player_id == player_id:
                continue
            if player.player_id not in outs:
                continue
            bench = benchmarks.get(player.player_id, {}).get(stat)
            recent = None if bench is None else bench.last10
            if recent is None or recent < threshold:
                continue
            names.append(f"{player.player_name} out (last-10 {stat.upper()} {recent:.1f})")
    # Outs who are not in the projection still count.
    projected = {
        player.player_id
        for summary in summaries
        for player in summary.players
        if player.team_abbr == team_abbr
    }
    for pid, entry in outs.items():
        if pid in projected or pid == player_id:
            continue
        if (entry.team_abbr or "") != team_abbr:
            continue
        bench = benchmarks.get(pid, {}).get(stat)
        recent = None if bench is None else bench.last10
        if recent is None or recent < threshold:
            continue
        names.append(f"{entry.player_name} out (last-10 {stat.upper()} {recent:.1f})")
    if not names:
        return None
    return "teammate absence: " + "; ".join(names[:3])


def check_slate(
    summaries: list[GameSummary],
    *,
    benchmarks: dict[int, dict[str, StatBenchmark]],
    injuries: list[InjuryEntry],
    game_date: date,
) -> SanityReport:
    outs = _out_statuses(injuries, game_date)
    own = _own_status(injuries, game_date)
    flags: list[SanityFlag] = []
    for summary in summaries:
        for player in summary.players:
            minutes = player.stats["min"].p50
            if minutes < 1.0:
                continue
            bench = benchmarks.get(player.player_id, {})
            for stat in CHECK_STATS:
                median = float(player.stats[stat].p50)
                stat_bench = bench.get(stat) or StatBenchmark()
                reasons: list[str] = []
                high = False
                low = False
                recent = stat_bench.last10
                floor = _MIN_RECENT[stat]
                if recent is not None and recent >= floor and recent > 0:
                    ratio = median / recent
                    if ratio > 1.40:
                        high = True
                        reasons.append(f"{(ratio - 1) * 100:.0f}% above last-10 {recent:.1f}")
                    elif ratio < 0.60:
                        low = True
                        reasons.append(f"{(1 - ratio) * 100:.0f}% below last-10 {recent:.1f}")
                if stat != "min" and stat_bench.per_minute is not None and minutes > 0:
                    rate_line = stat_bench.per_minute * minutes
                    if rate_line >= floor:
                        ratio = median / rate_line
                        if ratio > 1.40:
                            high = True
                            reasons.append(
                                f"{(ratio - 1) * 100:.0f}% above recent per-minute × minutes ({rate_line:.1f})"
                            )
                        elif ratio < 0.60:
                            low = True
                            reasons.append(
                                f"{(1 - ratio) * 100:.0f}% below recent per-minute × minutes ({rate_line:.1f})"
                            )
                if (
                    stat != "min"
                    and stat_bench.career_per36 is not None
                    and minutes >= 15.0
                    and stat_bench.career_per36 > 0
                ):
                    per36 = median * 36.0 / minutes
                    if per36 > stat_bench.career_per36 * 1.001:
                        high = True
                        reasons.append(
                            f"per-36 {per36:.1f} above career high {stat_bench.career_per36:.1f}"
                        )
                if stat == "min" and stat_bench.career_per36 is not None:
                    if median > stat_bench.career_per36 * 1.40 and stat_bench.career_per36 >= 8:
                        high = True
                        reasons.append(
                            f"minutes {median:.1f} are 40% above his career high game ({stat_bench.career_per36:.1f})"
                        )
                if not reasons:
                    continue
                explanation = _teammate_explanation(
                    stat=stat,
                    high=high and not low,
                    team_abbr=player.team_abbr,
                    player_id=player.player_id,
                    summaries=summaries,
                    outs=outs,
                    benchmarks=benchmarks,
                )
                entry = own.get(player.player_id)
                if explanation is None and entry is not None and low and not high:
                    status = (entry.status or "").upper()
                    if "QUESTION" in status or entry.minutes_cap is not None or "OUT" in status:
                        explanation = f"own status {entry.status}"
                quarantined = explanation is None and stat in QUARANTINE_STATS
                flags.append(
                    SanityFlag(
                        player_id=player.player_id,
                        player_name=player.player_name,
                        team_abbr=player.team_abbr,
                        stat=stat,
                        median=median,
                        detail="; ".join(reasons),
                        explanation=explanation,
                        quarantined=quarantined,
                    )
                )
    flags.sort(key=lambda item: (not item.quarantined, item.team_abbr, item.player_name, item.stat))
    return SanityReport(flags=flags)
