"""Build per-game player projections from stored rates and injuries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence

from ingest.injuries import InjuryEntry, active_absences, minutes_caps
from nba_sim.settings import Settings
from nba_sim.storage import read_rows

from projections.blend import (
    available_season_window,
    build_position_priors,
    load_player_meta,
    load_season_bundle,
    player_baseline_and_form,
)
from projections.context import (
    apply_opponent_defense,
    expected_possessions,
    league_zone_fg_pct,
    match_injury_player_ids,
    opponent_zone_fg_pct,
    redistribute_for_absences,
    rest_days_before,
    team_pace_map,
)
from projections.minutes import MinutesProjection, project_minutes, recent_minutes
from projections.rates import RateVector


@dataclass
class PlayerProjection:
    player_id: int
    player_name: str
    team_id: int
    team_abbr: str
    opponent_team_id: int
    opponent_abbr: str
    home_away: str
    position: str | None
    started: bool
    rates: RateVector
    minutes: MinutesProjection
    expected_team_possessions: float
    rest_days: int
    status: str


@dataclass
class GameProjection:
    season: str
    game_id: str
    game_date: date
    home_team_id: int
    away_team_id: int
    home_abbr: str
    away_abbr: str
    home_possessions: float
    away_possessions: float
    players: list[PlayerProjection]


def build_game_projections(
    settings: Settings,
    *,
    season: str,
    game_id: str,
    injuries: Sequence[InjuryEntry] | None = None,
    as_of: date | None = None,
) -> GameProjection:
    """Project both teams for one schedule game using only data before as_of."""
    schedule = next(
        (row for row in read_rows(settings, "schedule", season) if row["game_id"] == game_id),
        None,
    )
    if schedule is None:
        raise ValueError(f"game {game_id} not in schedule for {season}")
    game_date = schedule["game_date"]
    cutoff = as_of or game_date
    return _build(
        settings,
        season=season,
        game_id=str(schedule["game_id"]),
        game_date=game_date,
        home_team_id=int(schedule["home_team_id"]),
        away_team_id=int(schedule["away_team_id"]),
        home_abbr=str(schedule["home_abbr"]),
        away_abbr=str(schedule["away_abbr"]),
        injuries=list(injuries or []),
        as_of=cutoff,
    )


def build_slate_projections(
    settings: Settings,
    *,
    season: str,
    game_date: date,
    injuries: Sequence[InjuryEntry] | None = None,
) -> list[GameProjection]:
    games = [
        row
        for row in read_rows(settings, "schedule", season)
        if row["game_date"] == game_date
    ]
    return [
        build_game_projections(
            settings,
            season=season,
            game_id=str(row["game_id"]),
            injuries=injuries,
            as_of=game_date,
        )
        for row in sorted(games, key=lambda item: item["game_id"])
    ]


def _build(
    settings: Settings,
    *,
    season: str,
    game_id: str,
    game_date: date,
    home_team_id: int,
    away_team_id: int,
    home_abbr: str,
    away_abbr: str,
    injuries: list[InjuryEntry],
    as_of: date,
) -> GameProjection:
    config = settings.config
    seasons_back = list(config["blending"]["season_weights"]["seasons_back"])
    window = available_season_window(settings, season, seasons_back)
    if season not in window:
        window = [season] + window
    bundles = [load_season_bundle(settings, label) for label in window]
    priors = build_position_priors(bundles)
    meta = load_player_meta(bundles)
    injuries = match_injury_player_ids(injuries, meta)
    injury_by_id = {
        int(entry.player_id): entry
        for entry in injuries
        if entry.player_id is not None and entry.game_date == game_date
    }
    caps = minutes_caps(injuries)
    out_ids = {
        int(entry.player_id)
        for entry in active_absences(injuries)
        if entry.player_id is not None and entry.game_date == game_date
    }

    pace = team_pace_map(settings, season)
    # Fall back across window if current season aggregates are thin.
    if len(pace) < 2:
        for bundle in bundles:
            pace.update(team_pace_map(settings, bundle.season))
    league_zones = league_zone_fg_pct(settings, season)
    if not league_zones:
        for bundle in bundles:
            league_zones = league_zone_fg_pct(settings, bundle.season)
            if league_zones:
                break

    home_opp_zones = opponent_zone_fg_pct(settings, season, away_team_id) or league_zones
    away_opp_zones = opponent_zone_fg_pct(settings, season, home_team_id) or league_zones
    defense_weight = float(config["context"]["opponent_defense_weight"])
    usage_share = float(config["context"]["teammate_absence_usage_share"])

    home_ids = _roster_for_team(bundles, home_team_id, as_of)
    away_ids = _roster_for_team(bundles, away_team_id, as_of)

    def project_side(
        team_id: int,
        team_abbr: str,
        opp_id: int,
        opp_abbr: str,
        home_away: str,
        roster: list[int],
        opp_zones: dict[str, float],
    ) -> tuple[float, dict[int, PlayerProjection]]:
        raw_rates: dict[int, RateVector] = {}
        minute_bases: dict[int, tuple[float, float, list[date], bool, str | None]] = {}
        for player_id in roster:
            info = meta.get(player_id, {})
            position = info.get("position")
            rates = player_baseline_and_form(
                bundles,
                player_id=player_id,
                as_of=as_of,
                current_season=season,
                config=config,
                priors=priors,
                position=position,
            )
            rates = apply_opponent_defense(
                rates,
                opp_zone_pct=opp_zones,
                league_zone_pct=league_zones,
                weight=defense_weight,
            )
            raw_rates[player_id] = rates
            mean_min, sd_min, dates = recent_minutes(
                bundles,
                player_id=player_id,
                team_id=team_id,
                as_of=as_of,
                current_season=season,
            )
            started = _usually_starts(bundles, player_id, team_id, as_of)
            minute_bases[player_id] = (mean_min, sd_min, dates, started, position)

        adjusted = redistribute_for_absences(
            raw_rates,
            out_player_ids={pid for pid in out_ids if pid in raw_rates},
            usage_share=usage_share,
        )
        # Normalize on-court usage among players expected to play.
        playing = {
            pid: rates
            for pid, rates in adjusted.items()
            if pid not in out_ids and minute_bases[pid][0] > 0
        }
        usage_total = sum(rates.usage for rates in playing.values())
        if usage_total > 0:
            for pid, rates in playing.items():
                adjusted[pid] = RateVector.from_dict(
                    {**rates.as_dict(), "usage": rates.usage / usage_total},
                    sample_possessions=rates.sample_possessions,
                    sample_games=rates.sample_games,
                )

        team_pace = pace.get(team_id, 100.0)
        opp_pace = pace.get(opp_id, 100.0)
        # Rest from the busiest recent rotation player dates; use team game dates.
        team_dates = _team_game_dates(bundles, team_id, as_of)
        rest = rest_days_before(team_dates, game_date)
        team_poss = expected_possessions(
            team_pace=team_pace,
            opp_pace=opp_pace,
            home_away=home_away,
            rest_days=rest,
            config=config,
        )
        players: dict[int, PlayerProjection] = {}
        for player_id, rates in adjusted.items():
            mean_min, sd_min, _dates, started, position = minute_bases[player_id]
            entry = injury_by_id.get(player_id)
            status = entry.status if entry is not None else "Available"
            minutes = project_minutes(
                base_mean=mean_min,
                base_sd=sd_min,
                config=config,
                status=status,
                minutes_cap=caps.get(player_id),
                started=started,
            )
            info = meta.get(player_id, {})
            players[player_id] = PlayerProjection(
                player_id=player_id,
                player_name=str(info.get("player_name") or f"player:{player_id}"),
                team_id=team_id,
                team_abbr=team_abbr,
                opponent_team_id=opp_id,
                opponent_abbr=opp_abbr,
                home_away=home_away,
                position=position,
                started=started,
                rates=rates,
                minutes=minutes,
                expected_team_possessions=team_poss,
                rest_days=rest,
                status=status,
            )
        return team_poss, players

    home_poss, home_players = project_side(
        home_team_id, home_abbr, away_team_id, away_abbr, "H", home_ids, home_opp_zones
    )
    away_poss, away_players = project_side(
        away_team_id, away_abbr, home_team_id, home_abbr, "A", away_ids, away_opp_zones
    )
    players = sorted(
        list(home_players.values()) + list(away_players.values()),
        key=lambda row: (row.home_away != "H", -row.minutes.mean, row.player_name),
    )
    return GameProjection(
        season=season,
        game_id=game_id,
        game_date=game_date,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_abbr=home_abbr,
        away_abbr=away_abbr,
        home_possessions=home_poss,
        away_possessions=away_poss,
        players=players,
    )


def _roster_for_team(bundles: list, team_id: int, as_of: date) -> list[int]:
    """Players who appeared for the team before as_of.

    Prefer the newest season that has appearances so a partial current season
    is not diluted by ancient roster leftovers from sample backfills.
    """
    for bundle in sorted(bundles, key=lambda item: item.season, reverse=True):
        counts: dict[int, int] = {}
        for player_id, rows in bundle.logs_by_player.items():
            for row in rows:
                if int(row["team_id"]) == team_id and row["game_date"] < as_of:
                    counts[player_id] = counts.get(player_id, 0) + 1
        if counts:
            ranked = sorted(counts, key=lambda pid: (-counts[pid], pid))
            return ranked[:15]
    return []


def _usually_starts(bundles: list, player_id: int, team_id: int, as_of: date) -> bool:
    flags = []
    for bundle in bundles:
        for row in bundle.logs_by_player.get(player_id, []):
            if int(row["team_id"]) == team_id and row["game_date"] < as_of:
                flags.append(bool(row["started"]))
    if not flags:
        return False
    return sum(1 for flag in flags[-5:] if flag) >= 3


def _team_game_dates(bundles: list, team_id: int, as_of: date) -> list[date]:
    dates: set[date] = set()
    for bundle in bundles:
        for rows in bundle.logs_by_player.values():
            for row in rows:
                if int(row["team_id"]) == team_id and row["game_date"] < as_of:
                    dates.add(row["game_date"])
    return sorted(dates)
