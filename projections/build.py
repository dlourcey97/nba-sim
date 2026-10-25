"""Build per-game player projections from stored rates and injuries."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any, Sequence

from ingest.injuries import InjuryEntry, active_absences, minutes_caps
from ingest.rosters import (
    active_roster_player_ids,
    current_roster_player_ids,
    prior_season_label,
)
from nba_sim.schema import SEASON_TYPE_PRESEASON
from nba_sim.settings import Settings
from nba_sim.storage import is_isolated_season_type, read_rows

from projections.blend import (
    available_season_window,
    build_position_priors,
    load_player_meta,
    load_season_bundle,
    player_baseline_and_form,
)
from projections.context import (
    apply_opponent_defense,
    apply_opponent_position_defense,
    apply_team_strength_and_hca,
    apply_tov_stl_league_scale,
    expected_possessions,
    kalman_blend_weight,
    league_strength,
    league_tov_stl_scales,
    league_zone_fg_pct,
    match_injury_player_ids,
    opponent_zone_fg_pct,
    position_defense_from_bundles,
    prior_strength_after_absences,
    redistribute_for_absences,
    rest_days_before,
    roster_team_strength,
    team_pace_map,
    team_strength_as_of,
    team_strength_map,
    zone_defense_from_bundles,
)
from projections.minutes import (
    MinutesProjection,
    allocate_team_minutes,
    depth_prior_minutes,
    effective_minutes_gap_close,
    naive_last10_minutes,
    project_minutes,
    recent_minutes_detail,
    rotation_base_minutes,
)
from projections.rates import RateVector
from projections.game_state import GameStateModel, load_game_state_model
from projections.kalman import (
    KalmanTracker,
    make_kalman_tracker,
    prior_nets_from_strength,
    rest_hca_points,
)
from projections.rapm import RapmModel, load_rapm_model
from projections.rotations import (
    RotationModel,
    expected_abs_margin_from_strength,
    load_rotation_model,
    redistribute_minutes_for_absences,
)


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
    depth_rank: int = 99


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
    expected_abs_margin: float = 8.0
    rotation: RotationModel | None = None
    game_state: GameStateModel | None = None
    rapm: RapmModel | None = None
    # Effective minutes normalize_gap_close for this slate (early vs mid season).
    minutes_gap_close: float = 0.0
    # Passer→shooter assist counts: shooter_id → {passer_id: assists}.
    # Empty when assist_edges are missing; sim falls back to ast_rate.
    assist_network: dict[int, dict[int, float]] = field(default_factory=dict)
    # Defender id → FG% multiplier vs league (regressed; 1.0 = average).
    defender_fg_factor: dict[int, float] = field(default_factory=dict)
    defender_fg3_factor: dict[int, float] = field(default_factory=dict)


@dataclass
class ProjectionCache:
    """Reuse priors / league defense across games that share the same as_of date."""

    as_of: date | None = None
    priors: dict | None = None
    meta: dict | None = None
    league_zones: dict[str, float] | None = None
    league_pos: dict[str, dict[str, float]] | None = None
    zone_by_team: dict[int, dict[str, float]] = field(default_factory=dict)
    pos_by_team: dict[int, dict[str, dict[str, float]]] = field(default_factory=dict)
    # Season roster stints — reused across the whole slate (not cleared on as_of).
    roster_rows_by_season: dict[str, list] = field(default_factory=dict)
    current_roster_rows: list | None = None
    # as_of-scoped indexes built once per date for all teams
    appearances_by_team: dict[int, dict[int, int]] | None = None
    last_team_by_player: dict[int, int] | None = None
    rotation: RotationModel | None = None
    game_state: GameStateModel | None = None
    rapm: RapmModel | None = None
    rapm_season: str | None = None
    kalman_tracker: KalmanTracker | None = None
    # Shared stint rows by season (loaded once; date-filtered by consumers).
    stint_rows_by_season: dict[str, list] = field(default_factory=dict)
    assist_edge_rows_by_season: dict[str, list] = field(default_factory=dict)
    defender_impact_by_season: dict[str, list] = field(default_factory=dict)

    def reset_if_needed(self, as_of: date) -> None:
        if self.as_of != as_of:
            self.as_of = as_of
            self.priors = None
            self.meta = None
            self.league_zones = None
            self.league_pos = None
            self.zone_by_team.clear()
            self.pos_by_team.clear()
            self.appearances_by_team = None
            self.last_team_by_player = None
            # Keep rotation / game_state across as_of dates: priors are fit from
            # prior-season stints and re-fitting every slate date is too slow.

    def roster_rows(self, settings: Settings, season: str) -> list:
        if season not in self.roster_rows_by_season:
            self.roster_rows_by_season[season] = read_rows(settings, "team_rosters", season)
        return self.roster_rows_by_season[season]

    def current_rosters(self, settings: Settings, season: str) -> list:
        if self.current_roster_rows is None:
            self.current_roster_rows = read_rows(settings, "current_rosters", season)
        return self.current_roster_rows

    def assist_edges(self, settings: Settings, season: str) -> list:
        if season not in self.assist_edge_rows_by_season:
            self.assist_edge_rows_by_season[season] = read_rows(
                settings, "assist_edges", season
            )
        return self.assist_edge_rows_by_season[season]

    def defender_impact(self, settings: Settings, season: str) -> list:
        if season not in self.defender_impact_by_season:
            self.defender_impact_by_season[season] = read_rows(
                settings, "defender_impact", season
            )
        return self.defender_impact_by_season[season]

    def ensure_roster_indexes(self, bundles: list, as_of: date) -> None:
        if self.appearances_by_team is not None and self.last_team_by_player is not None:
            return
        appearances: dict[int, dict[int, int]] = {}
        last: dict[int, tuple[date, int]] = {}
        for bundle in bundles:
            for player_id, rows in bundle.logs_by_player.items():
                for row in rows:
                    game_date = row["game_date"]
                    if game_date >= as_of:
                        break  # logs are date-sorted
                    team_id = int(row["team_id"])
                    team_counts = appearances.setdefault(team_id, {})
                    team_counts[player_id] = team_counts.get(player_id, 0) + 1
                    prev = last.get(player_id)
                    if prev is None or game_date >= prev[0]:
                        last[player_id] = (game_date, team_id)
        self.appearances_by_team = appearances
        self.last_team_by_player = {pid: tid for pid, (_when, tid) in last.items()}


def build_game_projections(
    settings: Settings,
    *,
    season: str,
    game_id: str,
    injuries: Sequence[InjuryEntry] | None = None,
    as_of: date | None = None,
    bundles: list | None = None,
    minutes_bundles: list | None = None,
    cache: ProjectionCache | None = None,
    season_type: str | None = None,
    minutes_recent_decay: float | None = None,
) -> GameProjection:
    """Project both teams for one schedule game using only data before as_of.

    ``season_type`` selects the schedule partition (e.g. Preseason). Rate
    blending always uses Regular Season history unless ``bundles`` overrides.
    When ``minutes_bundles`` is set (typically Preseason logs), minutes and
    rotation use those games instead of the rate bundles.
    """
    schedule = next(
        (
            row
            for row in read_rows(settings, "schedule", season, season_type=season_type)
            if row["game_id"] == game_id
        ),
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
        bundles=bundles,
        minutes_bundles=minutes_bundles,
        cache=cache,
        minutes_recent_decay=minutes_recent_decay,
        season_type=season_type,
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
    bundles: list | None = None,
    minutes_bundles: list | None = None,
    cache: ProjectionCache | None = None,
    minutes_recent_decay: float | None = None,
    season_type: str | None = None,
) -> GameProjection:
    config = settings.config
    finals_before = sum(
        1
        for row in read_rows(settings, "schedule", season)
        if row.get("status") == "final" and row["game_date"] < as_of
    )
    minutes_gap = effective_minutes_gap_close(
        current_season_games_before=finals_before,
        config=config,
    )
    if minutes_gap != float(config["minutes"].get("normalize_gap_close", 0.0)):
        minutes_cfg = dict(config["minutes"])
        minutes_cfg["normalize_gap_close"] = minutes_gap
        config = {**config, "minutes": minutes_cfg}
    seasons_back = list(config["blending"]["season_weights"]["seasons_back"])
    window = available_season_window(settings, season, seasons_back)
    if season not in window:
        window = [season] + window
    if bundles is None:
        bundles = [load_season_bundle(settings, label) for label in window]
    else:
        # Keep only the seasons in the blend window, preserving caller order.
        wanted = set(window)
        bundles = [bundle for bundle in bundles if bundle.season in wanted]
        if not bundles:
            bundles = [load_season_bundle(settings, label) for label in window]
    minute_source = minutes_bundles if minutes_bundles is not None else bundles
    min_decay = (
        float(minutes_recent_decay)
        if minutes_recent_decay is not None
        else float(config["minutes"].get("recent_decay", 0.0))
    )
    if cache is None:
        cache = ProjectionCache()
    cache.reset_if_needed(as_of)
    if cache.priors is None:
        cache.priors = build_position_priors(bundles, as_of=as_of)
    if cache.meta is None:
        cache.meta = load_player_meta(bundles, as_of=as_of)
    priors = cache.priors
    meta = cache.meta
    # Ensure current-roster names/teams/positions exist for rookies and trades.
    # Live CommonTeamRoster wins over last-season log team for injury matching.
    if season == settings.current_season:
        for row in cache.current_rosters(settings, season):
            pid = int(row["player_id"])
            info = meta.setdefault(pid, {})
            info["player_name"] = str(row["player_name"])
            info["team_abbr"] = str(row.get("team_abbr") or info.get("team_abbr") or "")
            if row.get("position"):
                info["position"] = str(row["position"])
    injuries = match_injury_player_ids(injuries, meta)
    # Preseason: official PDF is empty — also mark roster players who sat out
    # every team preseason game unless overrides.yaml says available.
    if is_isolated_season_type(season_type) or season_type == SEASON_TYPE_PRESEASON:
        injuries = _merge_preseason_sitouts(
            settings,
            season=season,
            game_date=game_date,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            injuries=injuries,
            cache=cache,
            meta=meta,
        )
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
    # Zone + position defense from game logs before as_of (no future leakage).
    if cache.league_zones is None:
        cache.league_zones = zone_defense_from_bundles(bundles, as_of=as_of)
        if not any(cache.league_zones.values()):
            fallback = league_zone_fg_pct(settings, season)
            if not fallback:
                for bundle in bundles:
                    fallback = league_zone_fg_pct(settings, bundle.season)
                    if fallback:
                        break
            cache.league_zones = fallback or cache.league_zones
    league_zones = cache.league_zones

    def _opp_zones(team_id: int) -> dict[str, float]:
        if team_id not in cache.zone_by_team:
            cache.zone_by_team[team_id] = (
                zone_defense_from_bundles(bundles, as_of=as_of, defender_team_id=team_id)
                or opponent_zone_fg_pct(settings, season, team_id)
                or league_zones
            )
        return cache.zone_by_team[team_id]

    home_opp_zones = _opp_zones(away_team_id)
    away_opp_zones = _opp_zones(home_team_id)
    if cache.league_pos is None:
        cache.league_pos = position_defense_from_bundles(bundles, as_of=as_of)
    league_pos = cache.league_pos

    def _opp_pos(team_id: int) -> dict[str, dict[str, float]]:
        if team_id not in cache.pos_by_team:
            cache.pos_by_team[team_id] = position_defense_from_bundles(
                bundles, as_of=as_of, defender_team_id=team_id
            )
        return cache.pos_by_team[team_id]

    home_opp_pos = _opp_pos(away_team_id)
    away_opp_pos = _opp_pos(home_team_id)
    defense_weight = float(config["context"]["opponent_defense_weight"])
    position_weight = float(
        config["context"].get("opponent_position_defense_weight", 0.5)
    )
    usage_share = float(config["context"]["teammate_absence_usage_share"])
    play_threshold = float(config["minutes"].get("play_threshold", 1.0))
    recent_window = int(config["minutes"].get("recent_window", 10))

    home_ids = _roster_for_team(
        settings, season, bundles, home_team_id, as_of, cache=cache, minute_source=minute_source
    )
    away_ids = _roster_for_team(
        settings, season, bundles, away_team_id, as_of, cache=cache, minute_source=minute_source
    )

    # Prior-season team map is a fallback / DRtg anchor; primary strength is
    # roster-weighted (after minutes) blended with as-of current-season results.
    prior_strength: dict = {}
    prior_label = prior_season_label(season)
    if prior_label:
        prior_strength.update(team_strength_map(settings, prior_label))
    for bundle in bundles:
        if bundle.season == season or bundle.season == prior_label:
            continue
        for tid, value in team_strength_map(settings, bundle.season).items():
            prior_strength.setdefault(tid, value)
    league_str = league_strength(prior_strength) if prior_strength else league_strength({})
    if cache.rotation is None:
        cache.rotation = load_rotation_model(
            settings,
            bundles,
            as_of=as_of,
            config=config,
            stint_cache=cache.stint_rows_by_season,
        )
    rotation = cache.rotation
    if cache.game_state is None:
        cache.game_state = load_game_state_model(
            settings,
            bundles,
            as_of=as_of,
            config=config,
            stint_cache=cache.stint_rows_by_season,
        )
    game_state = cache.game_state
    if cache.rapm is None or cache.rapm_season != season:
        cache.rapm = load_rapm_model(
            settings,
            bundles,
            as_of=as_of,
            config=config,
            stint_cache=cache.stint_rows_by_season,
            season=season,
        )
        cache.rapm_season = season
    rapm = cache.rapm
    if cache.kalman_tracker is None or cache.kalman_tracker.season != season:
        cache.kalman_tracker = make_kalman_tracker(
            settings,
            season=season,
            config=config,
            prior_nets=prior_nets_from_strength(prior_strength, league_str),
        )
    kalman = cache.kalman_tracker.advance_to(as_of)
    home_prior = prior_strength.get(home_team_id)
    away_prior = prior_strength.get(away_team_id)
    if home_prior is not None and away_prior is not None:
        expected_abs_margin = expected_abs_margin_from_strength(
            home_prior.ortg,
            home_prior.drtg,
            away_prior.ortg,
            away_prior.drtg,
        )
    else:
        expected_abs_margin = 8.0

    def project_side(
        team_id: int,
        team_abbr: str,
        opp_id: int,
        opp_abbr: str,
        home_away: str,
        roster: list[int],
        opp_zones: dict[str, float],
        opp_pos: dict[str, dict[str, float]],
    ) -> tuple[float, dict[int, PlayerProjection], object]:
        raw_rates: dict[int, RateVector] = {}
        # depth_rank follows as-of roster order (minutes history / appearances).
        minute_bases: dict[int, tuple[float, float, bool, str | None, int]] = {}
        team_dates_for_minutes = _team_game_dates(minute_source, team_id, as_of)
        for depth_rank, player_id in enumerate(roster):
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
            rates = apply_opponent_position_defense(
                rates,
                position=position,
                opp_allowed=opp_pos,
                league_allowed=league_pos,
                weight=position_weight,
            )
            # Team strength / HCA applied after minutes allocation (roster-based).
            raw_rates[player_id] = rates
            mean_min, sd_min, _dates, recent_n = recent_minutes_detail(
                minute_source,
                player_id=player_id,
                team_id=team_id,
                as_of=as_of,
                current_season=season,
                window=recent_window,
                recent_decay=min_decay,
                team_game_dates=team_dates_for_minutes,
            )
            started = _usually_starts(minute_source, player_id, team_id, as_of)
            base = rotation_base_minutes(
                recent_mean=mean_min,
                recent_n=recent_n,
                depth_rank=depth_rank,
                started=started,
                config=config,
            )
            # Override "available" with no same-team sample (e.g. preseason sitout
            # cleared for tonight) still gets a mid-rotation minutes prior.
            entry_preview = injury_by_id.get(player_id)
            if (
                entry_preview is not None
                and entry_preview.source == "override"
                and entry_preview.status.lower() == "available"
                and recent_n <= 0
                and base <= 0
            ):
                debut_rank = min(
                    depth_rank,
                    int(config["minutes"].get("min_rotation_size", 8)) - 2,
                )
                base = max(depth_prior_minutes(max(debut_rank, 6), config), 14.0)
                sd_min = max(sd_min, 4.0)
            # Optional naive / blend minutes (bakeoff + production switch).
            minutes_model = str(
                (config.get("features") or {}).get("minutes_model", "engine")
            ).lower()
            if minutes_model in {"naive_last10", "naive", "blend"}:
                naive_mean, naive_sd, naive_n = naive_last10_minutes(
                    minute_source,
                    player_id=player_id,
                    as_of=as_of,
                    window=recent_window,
                    recent_decay=min_decay,
                    current_season=season,
                    early_season_games=int(
                        config["minutes"].get("early_season_games", 10)
                    ),
                )
                if minutes_model == "blend":
                    blend = float((config.get("features") or {}).get("naive_blend", 0.5))
                    blend = max(0.0, min(1.0, blend))
                    base = (1.0 - blend) * float(base) + blend * float(naive_mean)
                    sd_min = max(float(sd_min), float(naive_sd))
                    recent_n = max(recent_n, naive_n)
                else:
                    base = float(naive_mean)
                    sd_min = float(naive_sd) if naive_n > 0 else float(sd_min)
                    recent_n = naive_n
            # Appear rate over the aligned team window (DNPs count as misses).
            appear_rate = 1.0
            if team_dates_for_minutes:
                window_dates = sorted(
                    d for d in team_dates_for_minutes if d < as_of
                )[-recent_window:]
                if window_dates:
                    date_set = set(window_dates)
                    played_dates: set = set()
                    for bundle in minute_source:
                        for row in bundle.logs_by_player.get(player_id, []):
                            if (
                                row["game_date"] in date_set
                                and int(row["team_id"]) == team_id
                                and float(row.get("minutes") or 0.0) > 0
                            ):
                                played_dates.add(row["game_date"])
                    appear_rate = len(played_dates) / max(len(window_dates), 1)
            minute_bases[player_id] = (
                base,
                sd_min,
                started,
                position,
                depth_rank,
                float(appear_rate),
            )

        adjusted = redistribute_for_absences(
            raw_rates,
            out_player_ids={pid for pid in out_ids if pid in raw_rates},
            usage_share=usage_share,
        )

        team_pace = pace.get(team_id, 100.0)
        opp_pace = pace.get(opp_id, 100.0)
        # Rest from team game dates (already collected for minutes alignment).
        team_dates = team_dates_for_minutes
        rest = rest_days_before(team_dates, game_date)
        team_poss = expected_possessions(
            team_pace=team_pace,
            opp_pace=opp_pace,
            home_away=home_away,
            rest_days=rest,
            config=config,
        )

        # Project minutes, redistribute OUT minutes to historical replacements
        # (Step F), then force the healthy roster to sum to 240.
        ordered_ids = list(roster)
        raw_minutes: list[MinutesProjection] = []
        depth_ranks: list[int] = []
        for player_id in ordered_ids:
            base_mean, sd_min, started, _position, depth_rank, appear_rate = minute_bases[
                player_id
            ]
            entry = injury_by_id.get(player_id)
            status = entry.status if entry is not None else "Available"
            raw_minutes.append(
                project_minutes(
                    base_mean=base_mean,
                    base_sd=sd_min,
                    config=config,
                    status=status,
                    minutes_cap=caps.get(player_id),
                    started=started,
                    appear_rate=appear_rate,
                    depth_rank=depth_rank,
                )
            )
            depth_ranks.append(depth_rank)
        # Step F: give OUT minutes to who historically replaces them, not evenly.
        # Pure naive_last10 skips replacement graph + margin adjust (injuries/caps only).
        minutes_model = str(
            (config.get("features") or {}).get("minutes_model", "engine")
        ).lower()
        pure_naive = minutes_model in {"naive_last10", "naive"}
        team_out = {pid for pid in out_ids if pid in set(ordered_ids)}
        if pure_naive:
            # Even redistrib of OUT minutes among active naive means (no Step F graph).
            means0 = [p.mean for p in raw_minutes]
            freed = sum(means0[i] for i, pid in enumerate(ordered_ids) if pid in team_out)
            active_sum = sum(
                means0[i] for i, pid in enumerate(ordered_ids) if pid not in team_out
            ) or 1.0
            redistributed = []
            for i, pid in enumerate(ordered_ids):
                if pid in team_out or raw_minutes[i].out:
                    redistributed.append(0.0)
                else:
                    redistributed.append(means0[i] + freed * (means0[i] / active_sum))
        else:
            redistributed = redistribute_minutes_for_absences(
                ordered_ids,
                [p.mean for p in raw_minutes],
                team_id=team_id,
                out_ids=team_out,
                caps={pid: caps[pid] for pid in caps if pid in set(ordered_ids)},
                model=rotation,
                config=config,
            )
        raw_minutes = [
            (
                MinutesProjection(0.0, 0.0, 0.0, 0.0, True, play_prob=0.0)
                if raw_minutes[i].out or ordered_ids[i] in team_out
                else MinutesProjection(
                    mean=float(redistributed[i]),
                    sd=raw_minutes[i].sd,
                    min_minutes=raw_minutes[i].min_minutes,
                    max_minutes=(
                        min(raw_minutes[i].max_minutes, float(caps[ordered_ids[i]]))
                        if ordered_ids[i] in caps
                        else raw_minutes[i].max_minutes
                    ),
                    out=False,
                    play_prob=float(raw_minutes[i].play_prob),
                )
            )
            for i in range(len(ordered_ids))
        ]
        allocated = allocate_team_minutes(
            raw_minutes,
            config=config,
            depth_ranks=depth_ranks,
        )
        # Margin-conditioned rotation: close games shorten the rotation;
        # blowouts push minutes to the bench. Preserve team minute total.
        means = [p.mean for p in allocated]
        if pure_naive:
            adjusted_means = list(means)
        else:
            adjusted_means = rotation.adjust_means(
                means,
                depth_ranks,
                expected_abs_margin=expected_abs_margin,
                config=config,
                player_ids=ordered_ids,
                team_id=team_id,
            )
        prev_total = sum(means)
        new_total = sum(adjusted_means)
        if prev_total > 1e-9 and new_total > 1e-9:
            scale = prev_total / new_total
            adjusted_means = [m * scale for m in adjusted_means]
        # Re-apply caps after rotation adjust. Margin adjust can otherwise push
        # stars past both allocate output and max_minutes (Cade 35 → 41).
        max_min = float(config["minutes"]["max_minutes"])
        star_cap = float(config["minutes"].get("post_rotation_star_cap", 36.0))
        clipped = []
        for i, prev in enumerate(allocated):
            if prev.out:
                clipped.append(0.0)
                continue
            m = float(adjusted_means[i])
            m = min(m, max_min, max(float(prev.mean), star_cap))
            clipped.append(m)
        allocated = [
            (
                MinutesProjection(0.0, 0.0, 0.0, 0.0, True, play_prob=0.0)
                if prev.out
                else MinutesProjection(
                    mean=float(clipped[i]),
                    sd=prev.sd,
                    min_minutes=prev.min_minutes,
                    max_minutes=prev.max_minutes,
                    out=False,
                    play_prob=float(prev.play_prob),
                )
            )
            for i, prev in enumerate(allocated)
        ]
        minutes_by_id = dict(zip(ordered_ids, allocated))

        # Usage among players expected to play (post-allocation minutes).
        adjusted = _normalize_usage_for_minutes(
            adjusted,
            minutes_by_id=minutes_by_id,
            out_ids=out_ids,
            play_threshold=play_threshold,
        )

        # Roster-weighted strength: prefer ridge RAPM when available.
        roster_parts = [
            (adjusted[pid], minutes_by_id[pid].mean)
            for pid in ordered_ids
            if pid in adjusted
            and not minutes_by_id[pid].out
            and minutes_by_id[pid].mean > play_threshold
        ]
        rapm_parts = [
            (pid, minutes_by_id[pid].mean)
            for pid in ordered_ids
            if not minutes_by_id[pid].out and minutes_by_id[pid].mean > play_threshold
        ]
        current_str, current_games = team_strength_as_of(
            settings,
            season,
            team_id,
            as_of,
            opponent_strength=prior_strength,
            league=league_str,
            sos_weight=float(
                config.get("context", {}).get("current_sos_weight", 1.0)
            ),
        )
        prior = prior_strength.get(team_id)
        # Season prior assumes a healthy club. Pull it down when players are OUT
        # (RAPM gap when positive + minutes-based starter hit — ridge RAPM often
        # rates stars near zero/negative so gap alone is not enough).
        if team_out:
            healthy_parts = [
                (pid, float(minute_bases[pid][0]))
                for pid in ordered_ids
                if float(minute_bases[pid][0]) > play_threshold
            ]
            out_base = sum(
                float(minute_bases[pid][0])
                for pid in team_out
                if pid in minute_bases and float(minute_bases[pid][0]) > 0
            )
            healthy_net = (
                rapm.roster_net(healthy_parts) if rapm.ratings and healthy_parts else 0.0
            )
            available_net = (
                rapm.roster_net(rapm_parts) if rapm.ratings and rapm_parts else 0.0
            )
            prior = prior_strength_after_absences(
                prior,
                healthy_net=healthy_net,
                available_net=available_net,
                weight=float(
                    config.get("context", {}).get("absence_prior_weight", 1.0)
                ),
                out_base_minutes=out_base,
                minutes_net_per_36=float(
                    config.get("context", {}).get("absence_minutes_net_per_36", 3.5)
                ),
            )
        if rapm.ratings:
            team_str = rapm.team_strength(
                rapm_parts,
                league=league_str,
                prior=prior,
                current=current_str,
                current_games=current_games,
                config=config,
            )
        else:
            team_str = roster_team_strength(
                roster_parts,
                prior=prior,
                current=current_str,
                current_games=current_games,
                league=league_str,
                config=config,
            )
        # Blend dynamic Kalman net rating into ORtg/DRtg — sample-size scaled so
        # opening-week results cannot erase prior-season gaps.
        kalman_w = kalman_blend_weight(
            float(config.get("context", {}).get("kalman_strength_weight", 0.45)),
            current_games,
            half_life=float(
                config.get("context", {}).get("kalman_blend_half_life", 15.0)
            ),
        )
        if kalman_w > 0 and team_id in kalman.ratings:
            k_str = kalman.team_strength(team_id, league_str)
            team_str = type(team_str)(
                ortg=(1.0 - kalman_w) * team_str.ortg + kalman_w * k_str.ortg,
                drtg=(1.0 - kalman_w) * team_str.drtg + kalman_w * k_str.drtg,
            )

        players: dict[int, PlayerProjection] = {}
        for player_id, rates in adjusted.items():
            _base, _sd, started, position, _depth, _appear = minute_bases[player_id]
            entry = injury_by_id.get(player_id)
            status = entry.status if entry is not None else "Available"
            minutes = minutes_by_id[player_id]
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
                depth_rank=int(_depth),
            )
        return team_poss, players, team_str, rest

    home_poss, home_players, home_str, rest_home = project_side(
        home_team_id,
        home_abbr,
        away_team_id,
        away_abbr,
        "H",
        home_ids,
        home_opp_zones,
        home_opp_pos,
    )
    away_poss, away_players, away_str, rest_away = project_side(
        away_team_id,
        away_abbr,
        home_team_id,
        home_abbr,
        "A",
        away_ids,
        away_opp_zones,
        away_opp_pos,
    )

    def _apply_strength(
        players: dict[int, PlayerProjection],
        team_str,
        opp_str,
        home_away: str,
    ) -> None:
        for pid, player in list(players.items()):
            players[pid] = replace(
                player,
                rates=apply_team_strength_and_hca(
                    player.rates,
                    team=team_str,
                    opponent=opp_str,
                    league=league_str,
                    home_away=home_away,
                    config=config,
                    rest_home=rest_home,
                    rest_away=rest_away,
                ),
            )

    _apply_strength(home_players, home_str, away_str, "H")
    _apply_strength(away_players, away_str, home_str, "A")
    # Early-season TOV/STL: lift rates toward current-season league level when
    # enough finals exist (2026-27 opened ~19% above 2025-26 TOV).
    tov_scale, stl_scale = league_tov_stl_scales(
        settings,
        season=season,
        as_of=as_of,
        prior_season=prior_label,
        min_team_games=int(
            config.get("context", {}).get("tov_stl_scale_min_team_games", 20)
        ),
    )
    if abs(tov_scale - 1.0) > 1e-6 or abs(stl_scale - 1.0) > 1e-6:
        for side in (home_players, away_players):
            for pid, player in list(side.items()):
                side[pid] = replace(
                    player,
                    rates=apply_tov_stl_league_scale(
                        player.rates, tov_scale=tov_scale, stl_scale=stl_scale
                    ),
                )
    # Expected closeness uses Kalman nets + rest HCA when available.
    if home_team_id in kalman.ratings and away_team_id in kalman.ratings:
        expected_abs_margin = abs(
            kalman.ratings[home_team_id]
            - kalman.ratings[away_team_id]
            + rest_hca_points(rest_home, rest_away, config=config)
        )
    players = sorted(
        list(home_players.values()) + list(away_players.values()),
        key=lambda row: (row.home_away != "H", -row.minutes.mean, row.player_name),
    )
    # Refine expected margin with roster-weighted nets once both sides exist.
    refined_margin = expected_abs_margin_from_strength(
        home_str.ortg,
        home_str.drtg,
        away_str.ortg,
        away_str.drtg,
        possessions=0.5 * (home_poss + away_poss),
    )
    assist_network = _assist_network_as_of(
        settings,
        season=season,
        as_of=as_of,
        team_ids=(home_team_id, away_team_id),
        bundles=bundles,
        cache=cache,
    )
    def_fg, def_fg3 = _defender_factors_prior_seasons(
        settings,
        season=season,
        bundles=bundles,
        cache=cache,
        config=config,
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
        expected_abs_margin=float(refined_margin),
        rotation=rotation,
        game_state=game_state,
        rapm=rapm,
        minutes_gap_close=minutes_gap,
        assist_network=assist_network,
        defender_fg_factor=def_fg,
        defender_fg3_factor=def_fg3,
    )


def _assist_network_as_of(
    settings: Settings,
    *,
    season: str,
    as_of: date,
    team_ids: tuple[int, int],
    bundles: Sequence,
    cache: ProjectionCache | None,
) -> dict[int, dict[int, float]]:
    """Build shooter → {passer: assists} from assist_edges with as_of cutoff."""
    seasons = []
    for bundle in bundles:
        label = getattr(bundle, "season", None)
        if label and label not in seasons:
            seasons.append(label)
    if season not in seasons:
        seasons.append(season)
    network: dict[int, dict[int, float]] = {}
    team_set = {int(t) for t in team_ids}
    for label in seasons:
        if cache is not None:
            rows = cache.assist_edges(settings, label)
        else:
            rows = read_rows(settings, "assist_edges", label)
        for row in rows:
            if int(row["team_id"]) not in team_set:
                continue
            if row.get("game_date") is not None and row["game_date"] >= as_of:
                continue
            shooter = int(row["shooter_id"])
            passer = int(row["passer_id"])
            if shooter == passer:
                continue
            bucket = network.setdefault(shooter, {})
            bucket[passer] = bucket.get(passer, 0.0) + float(row["assists"])
    return network


def _defender_factors_prior_seasons(
    settings: Settings,
    *,
    season: str,
    bundles: Sequence,
    cache: ProjectionCache | None,
    config: dict,
) -> tuple[dict[int, float], dict[int, float]]:
    """Prior-season only defender FG multipliers (no same-season leakage)."""
    ctx = config.get("context", {})
    prior_n = float(ctx.get("defender_regression_fga", 80.0))
    # Collect prior seasons only (exclude the season being projected).
    prior_labels = []
    for bundle in bundles:
        label = getattr(bundle, "season", None)
        if label and label != season and label not in prior_labels:
            prior_labels.append(label)
    # Aggregate defender stats across prior seasons (recent seasons last → overwrite
    # with a simple sum).
    totals: dict[int, dict[str, float]] = {}
    for label in prior_labels:
        rows = (
            cache.defender_impact(settings, label)
            if cache is not None
            else read_rows(settings, "defender_impact", label)
        )
        for row in rows:
            did = int(row["defender_id"])
            bucket = totals.setdefault(
                did, {"fga": 0.0, "fgm": 0.0, "fg3a": 0.0, "fg3m": 0.0}
            )
            # Weight most recent prior season more via simple accumulation;
            # walk-forward already excludes current season.
            w = 1.0
            bucket["fga"] += w * float(row.get("fga") or 0.0)
            bucket["fgm"] += w * float(row.get("fgm") or 0.0)
            bucket["fg3a"] += w * float(row.get("fg3a") or 0.0)
            bucket["fg3m"] += w * float(row.get("fg3m") or 0.0)
    if not totals:
        return {}, {}
    league_fga = sum(b["fga"] for b in totals.values())
    league_fgm = sum(b["fgm"] for b in totals.values())
    league_fg3a = sum(b["fg3a"] for b in totals.values())
    league_fg3m = sum(b["fg3m"] for b in totals.values())
    league_fg = (league_fgm / league_fga) if league_fga > 0 else 0.46
    league_fg3 = (league_fg3m / league_fg3a) if league_fg3a > 0 else 0.36
    fg_factors: dict[int, float] = {}
    fg3_factors: dict[int, float] = {}
    for did, bucket in totals.items():
        fga = bucket["fga"]
        fg3a = bucket["fg3a"]
        # Bayesian shrink toward league; factor = allowed/league so >1 means
        # weaker defense (offense shoots better).
        fg = (bucket["fgm"] + prior_n * league_fg) / (fga + prior_n) if (fga + prior_n) else league_fg
        fg3 = (
            (bucket["fg3m"] + prior_n * league_fg3) / (fg3a + prior_n)
            if (fg3a + prior_n)
            else league_fg3
        )
        raw_fg = fg / league_fg if league_fg > 0 else 1.0
        raw_fg3 = fg3 / league_fg3 if league_fg3 > 0 else 1.0
        fg_factors[did] = float(max(0.90, min(1.10, raw_fg)))
        fg3_factors[did] = float(max(0.90, min(1.10, raw_fg3)))
    return fg_factors, fg3_factors


def _roster_for_team(
    settings: Settings,
    season: str,
    bundles: list,
    team_id: int,
    as_of: date,
    *,
    cache: ProjectionCache | None = None,
    minute_source: list | None = None,
) -> list[int]:
    """Team roster as of ``as_of`` with no future leakage.

    For ``season.current``, ``current_rosters`` (CommonTeamRoster) is the only
    membership set — prior-season last-known never re-adds waived players.
    Historical seasons use ``team_rosters`` stints. Appearance counts prefer
    ``minute_source`` (preseason logs) when provided.
    """
    count_bundles = minute_source if minute_source is not None else bundles
    # Role ranking prefers regular-season minute totals from ``bundles`` so
    # preseason appearance noise (or sitouts) does not bury established players.
    if cache is not None:
        cache.ensure_roster_indexes(count_bundles, as_of)
        counts = (cache.appearances_by_team or {}).get(team_id, {})
        season_rows = cache.roster_rows(settings, season)
    else:
        counts = _appearance_counts(count_bundles, team_id, as_of)
        season_rows = read_rows(settings, "team_rosters", season)
    role_minutes = _recent_minute_totals(bundles, team_id, as_of)

    def _depth_key(pid: int) -> tuple:
        return (-role_minutes.get(pid, 0.0), -counts.get(pid, 0), pid)

    if season == settings.current_season:
        live = (
            cache.current_rosters(settings, season)
            if cache is not None
            else read_rows(settings, "current_rosters", season)
        )
        live_ids = current_roster_player_ids(live, team_id=team_id)
        # Guard: CommonTeamRoster sometimes returns nonsense for the new season
        # (stars on the wrong clubs). If overlap with prior-season open stints is
        # tiny, prefer prior open roster plus anyone who already appeared this year.
        prior = prior_season_label(season)
        prior_open: list[int] = []
        if prior:
            prior_rows = (
                cache.roster_rows(settings, prior)
                if cache is not None
                else read_rows(settings, "team_rosters", prior)
            )
            prior_open = [
                int(row["player_id"])
                for row in prior_rows
                if int(row["team_id"]) == team_id and row.get("to_date") is None
            ]
        if live_ids and prior_open:
            overlap = len(set(live_ids) & set(prior_open))
            if overlap < max(5, int(0.4 * len(prior_open))):
                # Live CommonTeamRoster is untrustworthy — use prior-season open
                # stints only (opening-week safeguard against feed corruption).
                live_ids = list(prior_open)
        if live_ids:
            # Keep the full live roster; minutes allocation / outs shrink the rotation.
            return sorted(live_ids, key=_depth_key)[:18]

    roster_ids = active_roster_player_ids(
        season_rows,
        team_id=team_id,
        as_of=as_of,
    )
    # Opening night: stints often start on game day (from_date < as_of fails).
    # Fall back to prior season's open stints — never prior-season last_known logs.
    if not roster_ids:
        prior = prior_season_label(season)
        if prior:
            prior_rows = (
                cache.roster_rows(settings, prior)
                if cache is not None
                else read_rows(settings, "team_rosters", prior)
            )
            roster_ids = [
                int(row["player_id"])
                for row in prior_rows
                if int(row["team_id"]) == team_id
                and row.get("to_date") is None
                and (
                    row["from_date"] < as_of
                    if isinstance(row["from_date"], date)
                    else date.fromisoformat(str(row["from_date"])) < as_of
                )
            ]
    if not roster_ids:
        return []
    return sorted(roster_ids, key=_depth_key)[:15]


def _merge_preseason_sitouts(
    settings: Settings,
    *,
    season: str,
    game_date: date,
    home_team_id: int,
    away_team_id: int,
    injuries: list[InjuryEntry],
    cache: ProjectionCache,
    meta: dict,
) -> list[InjuryEntry]:
    """Mark current-roster players who never appeared in team preseason as Out."""
    live = cache.current_rosters(settings, season)
    by_team: dict[int, list[dict]] = {}
    for row in live:
        by_team.setdefault(int(row["team_id"]), []).append(row)
    override_by_id = {
        int(entry.player_id): entry
        for entry in injuries
        if entry.player_id is not None and entry.source == "override"
    }
    merged = list(injuries)
    seen = {
        int(entry.player_id)
        for entry in injuries
        if entry.player_id is not None and entry.game_date == game_date
    }
    for team_id in (home_team_id, away_team_id):
        for row in by_team.get(team_id, []):
            pid = int(row["player_id"])
            if bool(row.get("preseason_appeared")):
                continue
            if pid in override_by_id or pid in seen:
                continue
            name = str(
                row.get("player_name")
                or meta.get(pid, {}).get("player_name")
                or f"player:{pid}"
            )
            merged.append(
                InjuryEntry(
                    game_date=game_date,
                    matchup=None,
                    team_name=None,
                    team_abbr=str(row.get("team_abbr") or "") or None,
                    player_name=name,
                    player_id=pid,
                    status="Out",
                    reason="sat out all preseason games",
                    minutes_cap=None,
                    source="preseason_sitout",
                )
            )
            seen.add(pid)
    return merged


def _appearance_counts(bundles: list, team_id: int, as_of: date) -> dict[int, int]:
    counts: dict[int, int] = {}
    for bundle in bundles:
        for player_id, rows in bundle.logs_by_player.items():
            for row in rows:
                if int(row["team_id"]) == team_id and row["game_date"] < as_of:
                    counts[player_id] = counts.get(player_id, 0) + 1
    return counts


def _recent_minute_totals(bundles: list, team_id: int, as_of: date) -> dict[int, float]:
    """Sum of recent minutes for depth ranking (any team, prefer later seasons)."""
    totals: dict[int, float] = {}
    for bundle in bundles:
        for player_id, rows in bundle.logs_by_player.items():
            recent = [
                float(row["minutes"] or 0.0)
                for row in rows
                if row["game_date"] < as_of
            ]
            if not recent:
                continue
            # Last up to 15 appearances; weight same-team slightly higher via
            # including all and letting current-team appearances dominate when present.
            same = [
                float(row["minutes"] or 0.0)
                for row in rows
                if row["game_date"] < as_of and int(row["team_id"]) == team_id
            ]
            sample = (same[-15:] if same else recent[-15:])
            totals[player_id] = max(totals.get(player_id, 0.0), float(sum(sample)))
    return totals


def _last_known_team_roster(bundles: list, team_id: int, as_of: date) -> list[int]:
    """Players whose most recent appearance before as_of was for ``team_id``."""
    last: dict[int, tuple[date, int]] = {}
    for bundle in bundles:
        for player_id, rows in bundle.logs_by_player.items():
            for row in rows:
                game_date = row["game_date"]
                if game_date >= as_of:
                    continue
                prev = last.get(player_id)
                if prev is None or game_date >= prev[0]:
                    last[player_id] = (game_date, int(row["team_id"]))
    return [pid for pid, (_when, tid) in last.items() if tid == team_id]


def _usually_starts(bundles: list, player_id: int, team_id: int, as_of: date) -> bool:
    flags = []
    for bundle in bundles:
        for row in bundle.logs_by_player.get(player_id, []):
            if int(row["team_id"]) == team_id and row["game_date"] < as_of:
                flags.append(bool(row["started"]))
    if not flags:
        return False
    return sum(1 for flag in flags[-5:] if flag) >= 3


def _normalize_usage_for_minutes(
    rates_by_id: dict[int, RateVector],
    *,
    minutes_by_id: dict[int, MinutesProjection],
    out_ids: set[int],
    play_threshold: float,
) -> dict[int, RateVector]:
    """Calibrate on-court usage; zero players who will not play.

    Preserve relative usage shares, but scale so the minutes-weighted mean
    usage is 0.20 (five on-court players sum to ~1). Roster-wide sum-to-1
    diluted stars to ~0.15 and inflated shot share with low-usage bench;
    raw unscaled rates often sum to >1 on the floor.
    """
    playing = {
        pid: rates
        for pid, rates in rates_by_id.items()
        if pid not in out_ids
        and not minutes_by_id[pid].out
        and minutes_by_id[pid].mean > play_threshold
    }
    if not playing:
        return rates_by_id
    updated = dict(rates_by_id)
    floored: dict[int, float] = {}
    for pid, rates in playing.items():
        mean_min = minutes_by_id[pid].mean
        usage = float(rates.usage)
        if usage <= 1e-6:
            usage = max(0.02, 0.06 * (mean_min / 36.0))
        floored[pid] = usage
    min_total = sum(minutes_by_id[pid].mean for pid in floored)
    weighted = (
        sum(floored[pid] * minutes_by_id[pid].mean for pid in floored) / min_total
        if min_total > 1e-9
        else 0.0
    )
    scale = (0.20 / weighted) if weighted > 1e-9 else 1.0
    # Keep stars from being crushed or exploded by thin rotations.
    scale = max(0.70, min(1.15, float(scale)))
    for pid, usage in floored.items():
        rates = updated[pid]
        updated[pid] = RateVector.from_dict(
            {**rates.as_dict(), "usage": usage * scale},
            sample_possessions=rates.sample_possessions,
            sample_games=rates.sample_games,
        )
    for pid, rates in list(updated.items()):
        if pid not in playing:
            updated[pid] = RateVector.from_dict(
                {**rates.as_dict(), "usage": 0.0},
                sample_possessions=rates.sample_possessions,
                sample_games=rates.sample_games,
            )
    return updated


def _team_game_dates(bundles: list, team_id: int, as_of: date) -> list[date]:
    dates: set[date] = set()
    for bundle in bundles:
        for rows in bundle.logs_by_player.values():
            for row in rows:
                if int(row["team_id"]) == team_id and row["game_date"] < as_of:
                    dates.add(row["game_date"])
    return sorted(dates)
