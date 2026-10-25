"""Report top-usage stars' expected PPP vs top-5 / bottom-5 play-type defenses.

Uses PREVIOUS-season play_types for the given --season (leakage-safe), matching
walk-forward. Prints projected points-per-possession under each defense profile.

Usage:
  PYTHONPATH=. python scripts/play_type_star_report.py --season 2025-26
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.play_types import (
    DEFAULT_REGRESSION_POSS,
    PLAY_TYPES,
    league_baselines,
    load_entity_rates,
    rows_for_season,
)
from ingest.rosters import prior_season_label
from nba_sim.settings import load_settings


def expected_ppp(player_off, team_def, league_def) -> float:
    total = 0.0
    for pt, w in player_off.mix.items():
        if w <= 0:
            continue
        lg = league_def.get(pt) or {"ppp": 1.0}
        lg_ppp = max(0.5, float(lg["ppp"]))
        def_ppp = max(0.5, float(team_def.ppp.get(pt, lg_ppp)))
        p_ppp = max(0.5, float(player_off.ppp.get(pt, lg_ppp)))
        total += w * p_ppp * (def_ppp / lg_ppp)
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", default="2025-26")
    parser.add_argument("--top-n", type=int, default=10)
    args = parser.parse_args(argv)
    settings = load_settings()
    season = args.season
    # Force walk-forward season selection even if season == current.
    prior = prior_season_label(season)
    if prior is None:
        print(f"no prior season for {season}", file=sys.stderr)
        return 1
    rows = rows_for_season(settings, prior)
    if not rows:
        print(f"no play_types for {prior}", file=sys.stderr)
        return 1

    reg = float(
        (settings.config.get("context") or {}).get(
            "play_types_regression_possessions", DEFAULT_REGRESSION_POSS
        )
    )
    lg_off = league_baselines(rows, entity_kind="player", side="offense")
    lg_def = league_baselines(rows, entity_kind="team", side="defense")

    # Rank players by total offensive possessions.
    poss_by_player: dict[int, float] = {}
    name_by_player: dict[int, str] = {}
    for row in rows:
        if row.get("entity_kind") != "player" or row.get("side") != "offense":
            continue
        pid = int(row["entity_id"])
        poss_by_player[pid] = poss_by_player.get(pid, 0.0) + float(row["possessions"])
        name_by_player[pid] = str(row.get("entity_name") or pid)
    stars = sorted(poss_by_player, key=lambda p: -poss_by_player[p])[: args.top_n]

    # Team D ranking by possession-weighted PPP allowed (lower = tougher).
    team_ids = sorted(
        {
            int(r["entity_id"])
            for r in rows
            if r.get("entity_kind") == "team" and r.get("side") == "defense"
        }
    )
    team_scores: list[tuple[float, int, str]] = []
    team_defs = {}
    for tid in team_ids:
        td = load_entity_rates(
            rows,
            entity_kind="team",
            entity_id=tid,
            side="defense",
            league=lg_def,
            regression_possessions=reg,
        )
        if td is None:
            continue
        team_defs[tid] = td
        # Overall allowed PPP = mix-weighted? Use league offense mix as weights.
        mix = {pt: float((lg_off.get(pt) or {}).get("frequency", 1 / len(PLAY_TYPES))) for pt in PLAY_TYPES}
        s = sum(mix.values()) or 1.0
        score = sum((mix[pt] / s) * td.ppp.get(pt, 1.0) for pt in PLAY_TYPES)
        name = next(
            (
                str(r.get("entity_name"))
                for r in rows
                if r.get("entity_kind") == "team" and int(r["entity_id"]) == tid
            ),
            str(tid),
        )
        team_scores.append((score, tid, name))
    team_scores.sort()
    top5 = team_scores[:5]
    bot5 = team_scores[-5:][::-1]

    print(f"Play-type season used (prior of {season}): {prior}")
    print(f"Top {args.top_n} stars by Synergy offensive possessions\n")
    header = (
        f"{'Player':28} {'Poss':>7} {'BasePPP':>8}  "
        + " ".join(f"{n:>6}" for _, _, n in top5)
        + " | "
        + " ".join(f"{n:>6}" for _, _, n in bot5)
    )
    print(header)
    print("-" * len(header))
    for pid in stars:
        off = load_entity_rates(
            rows,
            entity_kind="player",
            entity_id=pid,
            side="offense",
            league=lg_off,
            regression_possessions=reg,
        )
        if off is None:
            continue
        base = sum(off.mix[pt] * off.ppp[pt] for pt in PLAY_TYPES)
        top_vals = [
            f"{expected_ppp(off, team_defs[tid], lg_def):6.3f}" for _, tid, _ in top5
        ]
        bot_vals = [
            f"{expected_ppp(off, team_defs[tid], lg_def):6.3f}" for _, tid, _ in bot5
        ]
        print(
            f"{name_by_player[pid][:28]:28} {poss_by_player[pid]:7.0f} {base:8.3f}  "
            + " ".join(top_vals)
            + " | "
            + " ".join(bot_vals)
        )
    print("\nTop-5 = toughest play-type defenses (lowest allowed PPP); bottom-5 = softest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
