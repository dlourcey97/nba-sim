"""Compact passer→shooter assist edges from play-by-play actions.

Never stores raw PBP — only (passer_id, shooter_id, assists) aggregates.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Iterable

from ingest.parse import CourtEvent, PossessionView


def assist_edges_from_possessions(
    *,
    season: str,
    game_id: str,
    game_date: date,
    possessions: list[PossessionView],
) -> list[dict]:
    """Sparse rows: one per (team, passer, shooter) with assists > 0."""
    counts: dict[tuple[int, int, int], int] = defaultdict(int)
    for possession in possessions:
        team_id = int(possession.offense_team_id)
        for event in possession.events:
            if event.kind != "field_goal" or not event.made:
                continue
            shooter = event.player_id
            passer = getattr(event, "assist_player_id", None)
            if shooter is None or passer is None:
                continue
            if int(passer) == int(shooter):
                continue
            counts[(team_id, int(passer), int(shooter))] += 1
    rows: list[dict] = []
    for (team_id, passer_id, shooter_id), assists in sorted(counts.items()):
        rows.append(
            {
                "season": season,
                "game_id": game_id,
                "game_date": game_date,
                "team_id": team_id,
                "passer_id": passer_id,
                "shooter_id": shooter_id,
                "assists": int(assists),
            }
        )
    return rows


def assist_edges_from_actions(
    *,
    season: str,
    game_id: str,
    game_date: date,
    actions: list[dict],
    home_team_id: int,
    away_team_id: int,
) -> list[dict]:
    """Extract assist edges directly from PlayByPlayV3 / live action dicts.

    ``assistPersonId`` is only present on assisted makes, so its presence is
    sufficient — no need to re-parse shotResult.
    """
    counts: dict[tuple[int, int, int], int] = defaultdict(int)
    valid_teams = {int(home_team_id), int(away_team_id)}
    for action in actions:
        passer = _int_id(action.get("assistPersonId") or action.get("assist_person_id"))
        if passer is None:
            # Traditional stats PBP: PLAYER2_ID on assisted makes.
            desc = str(action.get("description") or action.get("desc") or "")
            if "AST)" not in desc.upper() and " AST" not in desc.upper():
                passer = _int_id(action.get("PLAYER2_ID"))
            else:
                passer = _int_id(action.get("PLAYER2_ID") or action.get("player2_id"))
        if passer is None:
            continue
        shooter = _int_id(
            action.get("personId")
            or action.get("PLAYER1_ID")
            or action.get("player1_id")
        )
        if shooter is None or passer == shooter:
            continue
        team_id = _int_id(action.get("teamId") or action.get("TEAM_ID"))
        if team_id is None or team_id not in valid_teams:
            continue
        counts[(int(team_id), int(passer), int(shooter))] += 1
    rows: list[dict] = []
    for (team_id, passer_id, shooter_id), assists in sorted(counts.items()):
        rows.append(
            {
                "season": season,
                "game_id": game_id,
                "game_date": game_date,
                "team_id": team_id,
                "passer_id": passer_id,
                "shooter_id": shooter_id,
                "assists": int(assists),
            }
        )
    return rows


def season_assist_matrix(
    edges: Iterable[dict],
    *,
    as_of: date | None = None,
    team_id: int | None = None,
) -> dict[tuple[int, int], float]:
    """Sum assists to (passer_id, shooter_id) → weight, optionally as-of / team."""
    matrix: dict[tuple[int, int], float] = defaultdict(float)
    for row in edges:
        if team_id is not None and int(row["team_id"]) != int(team_id):
            continue
        if as_of is not None and row.get("game_date") is not None and row["game_date"] >= as_of:
            continue
        key = (int(row["passer_id"]), int(row["shooter_id"]))
        matrix[key] += float(row["assists"])
    return dict(matrix)


def _int_id(value) -> int | None:
    if value is None or value == "" or str(value) == "0":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
