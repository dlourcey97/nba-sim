"""Post-sim play card. DraftKings lines are read here and never enter the sim."""

from __future__ import annotations

import json
import unicodedata
import re
from dataclasses import dataclass, field
from pathlib import Path

from outputs.sanity import SanityReport, StatBenchmark
from outputs.summarize import GameSummary, StatSummary
from projections.build import GameProjection

PROP_STATS = ("pts", "reb", "ast")
# A points prop on a top-30 usage player waits until the star gap is fixed.
STAR_USAGE_N = 30
WIDE_MARGIN = {"pts": 4.0, "reb": 3.0, "ast": 2.0}
LINE_GAP = 3.0


@dataclass
class EdgePlay:
    tier: str
    player_id: int
    player_name: str
    team_abbr: str
    opponent_abbr: str
    game_id: str
    matchup: str
    stat: str
    side: str
    line: float
    odds: int
    our_p: float
    market_p: float
    edge: float
    sim_p50: float
    sim_mean: float
    season_avg: float | None
    last10: float | None
    minutes: float
    failed: str
    stat_hit_rate: float | None
    stat_claimed: float | None


@dataclass
class PlayCard:
    tops: list[EdgePlay] = field(default_factory=list)
    leans: list[EdgePlay] = field(default_factory=list)
    avoids: list[EdgePlay] = field(default_factory=list)
    note: str = ""
    qualified_stats: tuple[str, ...] = ()

    def lines(self) -> list[str]:
        out = [
            f"Qualified stats (hit rate at or above claimed, 30+ graded picks): "
            f"{', '.join(s.upper() for s in self.qualified_stats) or 'none'}."
        ]
        out.append("")
        out.append("### Top plays")
        out.append("")
        if not self.tops:
            out.append("None passed every check.")
        else:
            out.extend(_table(self.tops))
        out.append("")
        out.append("### Leans")
        out.append("")
        if not self.leans:
            out.append("None.")
        else:
            out.extend(_table(self.leans, failed=True))
        out.append("")
        out.append("### Avoid")
        out.append("")
        if not self.avoids:
            out.append("No large raw edge was skipped.")
        else:
            out.extend(_table(self.avoids, failed=True))
        if self.note:
            out.append("")
            out.append(self.note)
        return out


def _table(rows: list[EdgePlay], *, failed: bool = False) -> list[str]:
    header = (
        "| Player | Prop | Odds | Our % | Market % | Edge | Sim | Season | Last 10 | Stat hit |"
    )
    rule = "| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |"
    if failed:
        header = header[:-1] + " | Failed |"
        rule = rule[:-1] + " --- |"
    lines = [header, rule]
    for row in rows:
        sim = f"{row.sim_p50:.1f} ({row.sim_mean:.1f})"
        season = "—" if row.season_avg is None else f"{row.season_avg:.1f}"
        last = "—" if row.last10 is None else f"{row.last10:.1f}"
        hit = "—" if row.stat_hit_rate is None else f"{100 * row.stat_hit_rate:.0f}%"
        base = (
            f"| {row.player_name} | {row.team_abbr} {row.stat.upper()} {row.side} {row.line:g} "
            f"| {row.odds:+d} | {100 * row.our_p:.0f}% | {100 * row.market_p:.0f}% "
            f"| {100 * row.edge:+.1f}pp | {sim} | {season} | {last} | {hit} |"
        )
        if failed:
            base = base[:-1] + f" {row.failed} |"
        lines.append(base)
    return lines


def norm_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower().replace("'", "").replace(".", "")
    text = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", text)
    text = re.sub(r"[^a-z ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def implied(price: int) -> float:
    if price < 0:
        return -price / (-price + 100.0)
    return 100.0 / (price + 100.0)


def no_vig(over_price: int, under_price: int) -> tuple[float, float]:
    over_p = implied(over_price)
    under_p = implied(under_price)
    total = over_p + under_p
    if total <= 0:
        return 0.5, 0.5
    return over_p / total, under_p / total


def p_over(line: float, summary: StatSummary) -> float:
    """P(stat > line) from the published percentile curve, capped at the 10th/90th."""
    knots = (
        (0.10, summary.p10),
        (0.25, summary.p25),
        (0.50, summary.p50),
        (0.75, summary.p75),
        (0.90, summary.p90),
    )
    if line <= knots[0][1]:
        return 0.90
    if line >= knots[-1][1]:
        return 0.10
    for (p0, x0), (p1, x1) in zip(knots, knots[1:]):
        lo, hi = (x0, x1) if x1 >= x0 else (x1, x0)
        plo, phi = (p0, p1) if x1 >= x0 else (p1, p0)
        if lo <= line <= hi:
            if hi == lo:
                return 1.0 - phi
            t = (line - lo) / (hi - lo)
            return 1.0 - (plo + t * (phi - plo))
    return 0.10


def calibrated_stats(history_rows: list[dict]) -> dict[str, tuple[float, float, int]]:
    """Stat -> (hit rate, claimed, n) when n >= 30 and hit rate >= claimed."""
    buckets: dict[str, list[tuple[bool, float]]] = {}
    for row in history_rows:
        if str(row.get("row_kind") or "").split(":", 1)[0] != "pick":
            continue
        stat = str(row.get("pick_stat") or "").lower()
        if stat.startswith("dd") or row.get("actual_pick_hit") is None:
            continue
        buckets.setdefault(stat, []).append(
            (bool(row["actual_pick_hit"]), float(row.get("pick_confidence") or 0.0))
        )
    qualified: dict[str, tuple[float, float, int]] = {}
    for stat, rows in buckets.items():
        if len(rows) < 30:
            continue
        hit = sum(1 for flag, _ in rows if flag) / len(rows)
        claimed = sum(conf for _, conf in rows) / len(rows)
        if hit + 1e-9 >= claimed:
            qualified[stat] = (hit, claimed, len(rows))
    return qualified


def load_prop_cache(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text())
    return list(payload.get("props") or [])


def _season_avg(logs: list[dict], player_id: int, stat: str, season: str) -> float | None:
    column = "minutes" if stat == "min" else stat
    values = [
        float(row.get(column) or 0.0)
        for row in logs
        if int(row.get("player_id") or -1) == player_id
        and str(row.get("season") or "") == season
        and float(row.get("minutes") or 0.0) > 0
    ]
    if not values:
        return None
    return sum(values) / len(values)


def _top_usage(projections: list[GameProjection]) -> set[int]:
    ranked = []
    for projection in projections:
        for player in projection.players:
            ranked.append((float(player.rates.usage), player.player_id))
    ranked.sort(reverse=True)
    return {player_id for _usage, player_id in ranked[:STAR_USAGE_N]}


def _is_big(projection_player, season_reb: float | None) -> bool:
    position = (projection_player.position or "").upper()
    bucket = (getattr(projection_player, "offensive_bucket", "") or "").lower()
    if "C" in position or bucket == "big":
        return True
    return season_reb is not None and season_reb >= 8.0


def _bias_direction(stat: str, side: str, is_big: bool) -> bool:
    if stat == "pts" and side == "under":
        return True
    if stat == "reb" and side == "over" and is_big:
        return True
    return False


def _same_side(line: float, sim: float, season: float | None, last10: float | None) -> str | None:
    if season is None or last10 is None:
        return None
    if sim > line and season > line and last10 > line:
        return "over"
    if sim < line and season < line and last10 < line:
        return "under"
    return None


def select_plays(
    summaries: list[GameSummary],
    projections: list[GameProjection],
    *,
    props: list[dict],
    benchmarks: dict[int, dict[str, StatBenchmark]],
    logs: list[dict],
    season: str,
    history_rows: list[dict],
    sanity: SanityReport,
    questionable_ids: set[int],
) -> PlayCard:
    qualified = calibrated_stats(history_rows)
    stars = _top_usage(projections)
    by_id = {}
    proj_by_id = {}
    for summary in summaries:
        for player in summary.players:
            by_id[(norm_name(player.player_name), summary.game_id)] = (summary, player)
    game_by_teams = {
        (summary.away_abbr, summary.home_abbr): summary for summary in summaries
    }
    for projection in projections:
        for player in projection.players:
            proj_by_id[player.player_id] = player

    quarantined = sanity.quarantined_ids
    candidates: list[EdgePlay] = []
    for block in props:
        summary = game_by_teams.get((block.get("away"), block.get("home")))
        if summary is None:
            continue
        grouped: dict[str, dict] = {}
        for row in block.get("players") or []:
            grouped.setdefault(row["player"], {})[row["market"]] = row
        for dk_name, markets in grouped.items():
            key = norm_name(dk_name)
            match = None
            for player in summary.players:
                if norm_name(player.player_name) == key:
                    match = player
                    break
            if match is None:
                continue
            bench = benchmarks.get(match.player_id, {})
            for stat in PROP_STATS:
                offer = markets.get(stat)
                if not offer or offer.get("point") is None:
                    continue
                if offer.get("over") is None or offer.get("under") is None:
                    continue
                line = float(offer["point"])
                over_price = int(offer["over"])
                under_price = int(offer["under"])
                over_m, under_m = no_vig(over_price, under_price)
                our_over = p_over(line, match.stats[stat])
                our_under = 1.0 - our_over
                sim = float(match.stats[stat].p50)
                mean = float(match.stats[stat].mean)
                season_avg = _season_avg(logs, match.player_id, stat, season)
                last10 = None if bench.get(stat) is None else bench[stat].last10
                minutes = float(match.stats["min"].p50)
                agreed = _same_side(line, sim, season_avg, last10)
                # Raw side follows the sim median. Agreed side is the card side.
                raw_side = "over" if sim >= line else "under"
                side = agreed or raw_side
                our_p = our_over if side == "over" else our_under
                market_p = over_m if side == "over" else under_m
                odds = over_price if side == "over" else under_price
                edge = our_p - market_p
                proj = proj_by_id.get(match.player_id)
                is_big = _is_big(proj, _season_avg(logs, match.player_id, "reb", season)) if proj else False
                failed = _failed_checks(
                    stat=stat,
                    side=side,
                    agreed=agreed,
                    edge=edge,
                    line=line,
                    season_avg=season_avg,
                    last10=last10,
                    sim=sim,
                    minutes=minutes,
                    player_id=match.player_id,
                    qualified=qualified,
                    stars=stars,
                    quarantined=quarantined,
                    questionable=match.player_id in questionable_ids,
                    is_big=is_big,
                    explanation=_line_explanation(sanity, match.player_id, stat),
                )
                hit = qualified.get(stat)
                candidates.append(
                    EdgePlay(
                        tier="",
                        player_id=match.player_id,
                        player_name=match.player_name,
                        team_abbr=match.team_abbr,
                        opponent_abbr=match.opponent_abbr,
                        game_id=summary.game_id,
                        matchup=f"{summary.away_abbr}@{summary.home_abbr}",
                        stat=stat,
                        side=side,
                        line=line,
                        odds=odds,
                        our_p=our_p,
                        market_p=market_p,
                        edge=edge,
                        sim_p50=sim,
                        sim_mean=mean,
                        season_avg=season_avg,
                        last10=last10,
                        minutes=minutes,
                        failed=failed,
                        stat_hit_rate=None if hit is None else hit[0],
                        stat_claimed=None if hit is None else hit[1],
                    )
                )
    tops = [row for row in candidates if row.failed == ""]
    tops.sort(key=lambda row: -row.edge)
    tops = tops[:5]
    for row in tops:
        row.tier = "top"
    top_ids = {(row.player_id, row.stat, row.side) for row in tops}
    leans = [
        row
        for row in candidates
        if row.failed.count(";") == 0
        and row.failed != ""
        and (row.player_id, row.stat, row.side) not in top_ids
        and row.edge >= 0.0
    ]
    leans.sort(key=lambda row: -row.edge)
    leans = leans[:8]
    for row in leans:
        row.tier = "lean"
    lean_ids = {(row.player_id, row.stat, row.side) for row in leans}
    avoids = [
        row
        for row in candidates
        if row.edge >= 0.08
        and (row.player_id, row.stat, row.side) not in top_ids
        and (row.player_id, row.stat, row.side) not in lean_ids
    ]
    avoids.sort(key=lambda row: -row.edge)
    avoids = avoids[:8]
    for row in avoids:
        row.tier = "avoid"
    note = _correlation_note(tops)
    return PlayCard(
        tops=tops,
        leans=leans,
        avoids=avoids,
        note=note,
        qualified_stats=tuple(sorted(qualified)),
    )


def _line_explanation(sanity: SanityReport, player_id: int, stat: str) -> str | None:
    for flag in sanity.flags:
        if flag.player_id == player_id and flag.stat == stat and flag.explanation:
            return flag.explanation
    return None


def _failed_checks(
    *,
    stat: str,
    side: str,
    agreed: str | None,
    edge: float,
    line: float,
    season_avg: float | None,
    last10: float | None,
    sim: float,
    minutes: float,
    player_id: int,
    qualified: dict[str, tuple[float, float, int]],
    stars: set[int],
    quarantined: set[int],
    questionable: bool,
    is_big: bool,
    explanation: str | None,
) -> str:
    failures: list[str] = []
    if edge < 0.05:
        failures.append(f"a edge {100 * edge:+.1f}pp")
    if agreed is None:
        failures.append("b sim, season, and last-10 are not on the same side")
    if stat not in qualified:
        failures.append("c stat is not calibrated on 30+ graded picks")
    gates = []
    if player_id in quarantined:
        gates.append("sanity quarantine")
    if questionable:
        gates.append("questionable")
    if minutes < 24.0:
        gates.append(f"{minutes:.0f} minutes")
    if stat == "pts" and player_id in stars:
        gates.append("top-30 usage, star points still light")
    if gates:
        failures.append("d " + ", ".join(gates))
    if season_avg is None or abs(line - season_avg) > LINE_GAP:
        if not explanation:
            gap = "no season average" if season_avg is None else f"line is {abs(line - season_avg):.1f} from the season average"
            failures.append(f"e {gap}")
    if _bias_direction(stat, side, is_big):
        anchors = [value for value in (sim, season_avg, last10) if value is not None]
        if side == "over":
            margin = min((value - line) for value in anchors) if anchors else 0.0
        else:
            margin = min((line - value) for value in anchors) if anchors else 0.0
        if agreed is None or margin < WIDE_MARGIN[stat]:
            failures.append("f same direction as a known bias")
    return "; ".join(failures)


def _correlation_note(tops: list[EdgePlay]) -> str:
    if len(tops) < 2:
        return ""
    counts: dict[tuple[str, str], int] = {}
    for row in tops:
        counts[(row.stat, row.side)] = counts.get((row.stat, row.side), 0) + 1
    shared = [f"{stat.upper()} {side} ×{n}" for (stat, side), n in counts.items() if n >= 2]
    if not shared:
        return ""
    return (
        "Correlated risk: " + ", ".join(shared) + " share a side. "
        "A miss on that stat moves them together."
    )


def close_line_value(side: str, open_line: float, close_line: float) -> float:
    """Points the number moved toward the play. Positive is toward us."""
    if side == "over":
        return close_line - open_line
    return open_line - close_line
