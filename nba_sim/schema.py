"""Parquet table contracts.

SCHEMA.md is rendered from this module. Change columns here, regenerate
SCHEMA.md, and keep the two in sync. Agents should read SCHEMA.md instead
of opening data files.
"""

from __future__ import annotations

from dataclasses import dataclass

import pyarrow as pa

SEASON_PATTERN = r"^\d{4}-\d{2}$"

# Internal season_type labels (partition values). NBA stats API uses "Pre Season".
SEASON_TYPE_REGULAR = "Regular Season"
SEASON_TYPE_PLAYOFFS = "Playoffs"
SEASON_TYPE_PLAYIN = "PlayIn"
SEASON_TYPE_PRESEASON = "Preseason"
SEASON_TYPES = (
    SEASON_TYPE_REGULAR,
    SEASON_TYPE_PLAYOFFS,
    SEASON_TYPE_PLAYIN,
    SEASON_TYPE_PRESEASON,
)
# Map internal label -> stats.nba.com SeasonType query value.
API_SEASON_TYPE = {
    SEASON_TYPE_REGULAR: "Regular Season",
    SEASON_TYPE_PLAYOFFS: "Playoffs",
    SEASON_TYPE_PLAYIN: "PlayIn",
    SEASON_TYPE_PRESEASON: "Pre Season",
}
ZONES = (
    "restricted_area",
    "paint_non_ra",
    "midrange",
    "left_corner_3",
    "right_corner_3",
    "above_break_3",
)
# Traditional positions for opponent defense allowed-to-position stats.
POSITIONS_5 = ("PG", "SG", "SF", "PF", "C")
PLAYER_STATS = (
    "pts",
    "reb",
    "ast",
    "fg3m",
    "stl",
    "blk",
    "tov",
    "min",
    "pra",
    "pr",
    "pa",
    "ra",
)
PERCENTILES = ("mean", "p10", "p25", "p50", "p75", "p90")
GAME_DISTRIBUTIONS = ("home_pts", "away_pts", "margin", "total")

ARROW_TYPES = {
    "VARCHAR": pa.string(),
    "INTEGER": pa.int32(),
    "DOUBLE": pa.float64(),
    "BOOLEAN": pa.bool_(),
    "DATE": pa.date32(),
    "TIMESTAMP": pa.timestamp("us"),
}


@dataclass(frozen=True)
class Column:
    name: str
    type_name: str
    nullable: bool
    description: str

    def __post_init__(self) -> None:
        if self.type_name not in ARROW_TYPES:
            raise ValueError(f"unknown type {self.type_name} on {self.name}")

    def field(self) -> pa.Field:
        return pa.field(self.name, ARROW_TYPES[self.type_name], nullable=self.nullable)


@dataclass(frozen=True)
class Table:
    name: str
    policy: str
    key: tuple[str, ...]
    grain: str
    description: str
    columns: tuple[Column, ...]

    def __post_init__(self) -> None:
        if self.policy not in {"incremental_current", "replace", "upsert_current"}:
            raise ValueError(f"{self.name} has unknown policy {self.policy}")
        names = [column.name for column in self.columns]
        if len(names) != len(set(names)):
            raise ValueError(f"{self.name} has duplicate columns")
        if "season" not in names:
            raise ValueError(f"{self.name} must include season")
        missing = [key for key in self.key if key not in names]
        if missing:
            raise ValueError(f"{self.name} key columns missing: {missing}")

    def arrow_schema(self) -> pa.Schema:
        return pa.schema([column.field() for column in self.columns])


def _col(name: str, type_name: str, nullable: bool, description: str) -> Column:
    return Column(name, type_name, nullable, description)


def _season_cols() -> tuple[Column, ...]:
    return (
        _col("season", "VARCHAR", False, "NBA season label, such as 2025-26. Partition key."),
    )


def _zone_columns(prefix_note: str) -> tuple[Column, ...]:
    columns: list[Column] = []
    for zone in ZONES:
        label = zone.replace("_", " ")
        columns.append(
            _col(
                f"{zone}_fga",
                "DOUBLE",
                False,
                f"{prefix_note} field-goal attempts from {label}.",
            )
        )
        columns.append(
            _col(
                f"{zone}_fgm",
                "DOUBLE",
                False,
                f"{prefix_note} field goals made from {label}.",
            )
        )
    return tuple(columns)


def _player_distribution_columns() -> tuple[Column, ...]:
    columns: list[Column] = []
    for stat in PLAYER_STATS:
        for percentile in PERCENTILES:
            columns.append(
                _col(
                    f"pred_{stat}_{percentile}",
                    "DOUBLE",
                    True,
                    f"Predicted {stat} {percentile}. Null on game rows.",
                )
            )
        columns.append(
            _col(
                f"actual_{stat}",
                "DOUBLE",
                True,
                f"Actual {stat} after the game. Null until the game is final, and null on game rows.",
            )
        )
    return tuple(columns)


def _game_distribution_columns() -> tuple[Column, ...]:
    columns: list[Column] = []
    for stat in GAME_DISTRIBUTIONS:
        for percentile in PERCENTILES:
            columns.append(
                _col(
                    f"pred_{stat}_{percentile}",
                    "DOUBLE",
                    True,
                    f"Predicted {stat} {percentile}. Margin is home minus away. Null on player rows.",
                )
            )
    return tuple(columns)


def _tables() -> dict[str, Table]:
    player_game_logs = Table(
        name="player_game_logs",
        policy="incremental_current",
        key=("game_id", "player_id"),
        grain="one row per player per game",
        description=(
            "Compact box score for every player appearance. "
            "Completed seasons are frozen with a _COMPLETE marker and are never rewritten. "
            "The current season accepts new keys only. "
            "starter and position come from the live box score when that feed is available."
        ),
        columns=_season_cols()
        + (
            _col("game_id", "VARCHAR", False, "NBA game id."),
            _col("game_date", "DATE", False, "Game date in the NBA schedule."),
            _col("player_id", "INTEGER", False, "NBA player id."),
            _col("player_name", "VARCHAR", False, "Player display name."),
            _col("team_id", "INTEGER", False, "Team the player appeared for."),
            _col("team_abbr", "VARCHAR", False, "Team abbreviation."),
            _col("opponent_team_id", "INTEGER", False, "Opposing team id."),
            _col("opponent_abbr", "VARCHAR", False, "Opposing team abbreviation."),
            _col("home_away", "VARCHAR", False, "H or A from this team's perspective."),
            _col("win", "BOOLEAN", False, "True when the player's team won."),
            _col("started", "BOOLEAN", False, "True when the player started."),
            _col("position", "VARCHAR", True, "Listed position when known."),
            _col("minutes", "DOUBLE", False, "Minutes played."),
            _col("pts", "INTEGER", False, "Points."),
            _col("reb", "INTEGER", False, "Rebounds."),
            _col("ast", "INTEGER", False, "Assists."),
            _col("fg3m", "INTEGER", False, "Three-pointers made."),
            _col("stl", "INTEGER", False, "Steals."),
            _col("blk", "INTEGER", False, "Blocks."),
            _col("tov", "INTEGER", False, "Turnovers."),
            _col("fgm", "INTEGER", False, "Field goals made."),
            _col("fga", "INTEGER", False, "Field goals attempted."),
            _col("fg3a", "INTEGER", False, "Three-pointers attempted."),
            _col("ftm", "INTEGER", False, "Free throws made."),
            _col("fta", "INTEGER", False, "Free throws attempted."),
            _col("oreb", "INTEGER", False, "Offensive rebounds."),
            _col("dreb", "INTEGER", False, "Defensive rebounds."),
            _col("plus_minus", "INTEGER", True, "Plus-minus when the source provides it."),
        ),
    )
    team_game_results = Table(
        name="team_game_results",
        policy="incremental_current",
        key=("game_id", "team_id"),
        grain="one row per team per game",
        description=(
            "Final team result and pace. Two rows per game. "
            "Same freeze and incremental rules as player_game_logs."
        ),
        columns=_season_cols()
        + (
            _col("game_id", "VARCHAR", False, "NBA game id."),
            _col("game_date", "DATE", False, "Game date."),
            _col("team_id", "INTEGER", False, "Team id."),
            _col("team_abbr", "VARCHAR", False, "Team abbreviation."),
            _col("opponent_team_id", "INTEGER", False, "Opposing team id."),
            _col("opponent_abbr", "VARCHAR", False, "Opposing team abbreviation."),
            _col("home_away", "VARCHAR", False, "H or A."),
            _col("win", "BOOLEAN", False, "True when this team won."),
            _col("pts", "INTEGER", False, "Points scored by this team."),
            _col("opp_pts", "INTEGER", False, "Points allowed."),
            _col("pace", "DOUBLE", True, "Offensive possessions in this game when play-by-play is available."),
            _col("overtime_periods", "INTEGER", False, "Number of overtime periods. 0 if regulation."),
        ),
    )
    schedule = Table(
        name="schedule",
        policy="upsert_current",
        key=("game_id",),
        grain="one row per game",
        description=(
            "Season schedule. The current season is upserted so a scheduled game can be updated to final "
            "with scores, still as one row. Completed seasons are frozen with _COMPLETE and never rewritten."
        ),
        columns=_season_cols()
        + (
            _col("game_id", "VARCHAR", False, "NBA game id."),
            _col("game_date", "DATE", False, "Scheduled date."),
            _col("home_team_id", "INTEGER", False, "Home team id."),
            _col("away_team_id", "INTEGER", False, "Away team id."),
            _col("home_abbr", "VARCHAR", False, "Home abbreviation."),
            _col("away_abbr", "VARCHAR", False, "Away abbreviation."),
            _col("status", "VARCHAR", False, "scheduled or final."),
            _col("home_pts", "INTEGER", True, "Home points once final."),
            _col("away_pts", "INTEGER", True, "Away points once final."),
        ),
    )
    player_game_rates = Table(
        name="player_game_rates",
        policy="replace",
        key=("game_id", "player_id"),
        grain="one row per player per game",
        description=(
            "Per-player, per-game rates derived from play-by-play. "
            "Historical seasons use PlayByPlayV3; the current season uses the live feed, "
            "which is also the fallback. Shot zones use the same cutoffs either way: "
            "at the rim inside 4 feet, short midrange inside 14 feet, long midrange, "
            "corner threes at or below 8.7 feet split by court side, and above-the-break threes. "
            "The season file is rewritten in place when new games are added, not appended as a new copy."
        ),
        columns=_season_cols()
        + (
            _col("game_id", "VARCHAR", False, "NBA game id."),
            _col("game_date", "DATE", False, "Game date."),
            _col("player_id", "INTEGER", False, "NBA player id."),
            _col("team_id", "INTEGER", False, "Team id for this appearance."),
            _col("minutes", "DOUBLE", False, "Minutes played."),
            _col("possessions", "DOUBLE", False, "Team possessions while the player was on the court."),
            _col("usage", "DOUBLE", False, "Share of on-court possessions the player used."),
            _col("oreb_chances", "DOUBLE", False, "Offensive rebound chances."),
            _col("dreb_chances", "DOUBLE", False, "Defensive rebound chances."),
            _col("ast_chances", "DOUBLE", False, "Assist chances."),
            _col("fta", "DOUBLE", False, "Free throws attempted."),
            _col("ftm", "DOUBLE", False, "Free throws made."),
        )
        + _zone_columns("This game's"),
    )
    player_season_aggregates = Table(
        name="player_season_aggregates",
        policy="replace",
        key=("player_id", "team_id"),
        grain="one row per player per team per season",
        description="Season totals and rates. Overwritten each run. A traded player has one row per team.",
        columns=_season_cols()
        + (
            _col("player_id", "INTEGER", False, "NBA player id."),
            _col("team_id", "INTEGER", False, "Team id."),
            _col("player_name", "VARCHAR", False, "Player display name."),
            _col("position", "VARCHAR", True, "Position used for regression priors."),
            _col("games", "INTEGER", False, "Games played for this team."),
            _col("minutes", "DOUBLE", False, "Total minutes."),
            _col("possessions", "DOUBLE", False, "On-court possessions."),
            _col("usage", "DOUBLE", False, "Season usage rate."),
            _col("oreb_chances", "DOUBLE", False, "Offensive rebound chances."),
            _col("dreb_chances", "DOUBLE", False, "Defensive rebound chances."),
            _col("ast_chances", "DOUBLE", False, "Assist chances."),
            _col("pts", "INTEGER", False, "Points total."),
            _col("reb", "INTEGER", False, "Rebounds total."),
            _col("ast", "INTEGER", False, "Assists total."),
            _col("fg3m", "INTEGER", False, "Three-pointers made."),
            _col("stl", "INTEGER", False, "Steals total."),
            _col("blk", "INTEGER", False, "Blocks total."),
            _col("tov", "INTEGER", False, "Turnovers total."),
            _col("fta", "DOUBLE", False, "Free throws attempted."),
            _col("ftm", "DOUBLE", False, "Free throws made."),
        )
        + _zone_columns("Season"),
    )
    team_season_aggregates = Table(
        name="team_season_aggregates",
        policy="replace",
        key=("team_id",),
        grain="one row per team per season",
        description="Team pace and scoring environment. Overwritten each run.",
        columns=_season_cols()
        + (
            _col("team_id", "INTEGER", False, "Team id."),
            _col("team_abbr", "VARCHAR", False, "Team abbreviation."),
            _col("games", "INTEGER", False, "Games played."),
            _col("pace", "DOUBLE", False, "Average possessions per game."),
            _col("possessions_for", "DOUBLE", False, "Offensive possessions."),
            _col("possessions_against", "DOUBLE", False, "Defensive possessions."),
            _col("points_for", "INTEGER", False, "Points scored."),
            _col("points_against", "INTEGER", False, "Points allowed."),
        ),
    )
    team_zone_defense = Table(
        name="team_zone_defense",
        policy="replace",
        key=("team_id", "zone"),
        grain="one row per team per shot zone per season",
        description=(
            "Opponent shot-zone defense. zone is one of restricted_area, paint_non_ra, "
            "midrange, left_corner_3, right_corner_3, above_break_3. Overwritten each run."
        ),
        columns=_season_cols()
        + (
            _col("team_id", "INTEGER", False, "Defending team id."),
            _col("zone", "VARCHAR", False, "Shot zone name."),
            _col("fga", "DOUBLE", False, "Opponent attempts allowed in this zone."),
            _col("fgm", "DOUBLE", False, "Opponent makes allowed in this zone."),
            _col("possessions", "DOUBLE", False, "Defensive possessions in the sample."),
        ),
    )
    team_position_defense = Table(
        name="team_position_defense",
        policy="replace",
        key=("team_id", "position"),
        grain="one row per team per position (PG/SG/SF/PF/C) per season",
        description=(
            "Opponent defense by position: box-score stats allowed to opposing "
            "PG/SG/SF/PF/C, derived from player game logs. Position labels are "
            "normalized from listed G/F/C (and None) using that game's reb/ast. "
            "Overwritten each run."
        ),
        columns=_season_cols()
        + (
            _col("team_id", "INTEGER", False, "Defending team id."),
            _col("position", "VARCHAR", False, "Opponent position: PG, SG, SF, PF, or C."),
            _col("player_games", "INTEGER", False, "Opponent player-games at this position."),
            _col("minutes", "DOUBLE", False, "Opponent minutes at this position."),
            _col("pts", "DOUBLE", False, "Points allowed to this position."),
            _col("reb", "DOUBLE", False, "Rebounds allowed to this position."),
            _col("ast", "DOUBLE", False, "Assists allowed to this position."),
            _col("fg3m", "DOUBLE", False, "Threes made allowed to this position."),
            _col("stl", "DOUBLE", False, "Steals allowed to this position."),
            _col("blk", "DOUBLE", False, "Blocks allowed to this position."),
            _col("tov", "DOUBLE", False, "Turnovers forced from this position."),
        ),
    )
    team_rosters = Table(
        name="team_rosters",
        policy="replace",
        key=("team_id", "player_id", "from_date"),
        grain="one row per player stint on a team within a season",
        description=(
            "As-of-date team membership for projections and walk-forward backtests. "
            "Built primarily from player_game_logs: consecutive appearances for the "
            "same team become a stint with from_date equal to the first game date and "
            "to_date equal to the first game date on a different team (exclusive end), "
            "or null when the player is still on that team at season rebuild time. "
            "The current season may also merge CommonTeamRoster so signed/traded "
            "players appear before their first box score. "
            "Roster as of date D uses only rows with from_date < D and "
            "(to_date is null or D < to_date); never use future game logs. "
            "CommonTeamRoster is a current snapshot only — historical accuracy comes "
            "from game-log stints. Overwritten each derived rewrite."
        ),
        columns=_season_cols()
        + (
            _col("team_id", "INTEGER", False, "Team id for this stint."),
            _col("team_abbr", "VARCHAR", False, "Team abbreviation."),
            _col("player_id", "INTEGER", False, "NBA player id."),
            _col("player_name", "VARCHAR", False, "Player display name."),
            _col("position", "VARCHAR", True, "Listed position when known."),
            _col("from_date", "DATE", False, "First date the player is known on this team (exclusive lower bound for as-of: from_date < D)."),
            _col("to_date", "DATE", True, "First date no longer on this team (exclusive). Null if still on the team."),
            _col("jersey", "VARCHAR", True, "Jersey number when known from CommonTeamRoster."),
            _col("roster_status", "VARCHAR", True, "Optional roster status from the API when available."),
            _col("source", "VARCHAR", False, "game_log or common_roster."),
        ),
    )
    current_rosters = Table(
        name="current_rosters",
        policy="replace",
        key=("team_id", "player_id"),
        grain="one row per player on a team's live CommonTeamRoster",
        description=(
            "Live snapshot of every team's roster for season.current from "
            "stats.nba.com CommonTeamRoster. Refreshed on every daily.py run. "
            "Also notes whether the player has appeared in that team's Preseason "
            "box scores this season (preseason_appeared). Current-season projections "
            "must use this table and must not include anyone absent from it. "
            "Historical walk-forward continues to use team_rosters stints."
        ),
        columns=_season_cols()
        + (
            _col("team_id", "INTEGER", False, "Team id."),
            _col("team_abbr", "VARCHAR", False, "Team abbreviation."),
            _col("player_id", "INTEGER", False, "NBA player id."),
            _col("player_name", "VARCHAR", False, "Player display name."),
            _col("position", "VARCHAR", True, "Listed position when known."),
            _col("jersey", "VARCHAR", True, "Jersey number when known."),
            _col("preseason_appeared", "BOOLEAN", False, "True if the player logged minutes for this team in a 2026-27 Preseason box score."),
            _col("refreshed_at", "TIMESTAMP", False, "UTC time this snapshot was written."),
        ),
    )
    prediction_history = Table(
        name="prediction_history",
        policy="upsert_current",
        key=("row_kind", "game_id", "player_id", "pick_stat"),
        grain=(
            "one player row per player per game, one game row per game, "
            "and optional pick rows (row_kind=pick) for top confident stat lines"
        ),
        description=(
            "Summary of a simulation, not the raw runs. "
            "row_kind is player, game, or pick. Player rows leave the game distribution null. "
            "Game rows leave player_id and the player distributions null. "
            "Pick rows store claimed confidence ranges for tonight's top lines; "
            "actual_pick_hit is filled after the game. "
            "pick_stat is '' on player/game rows and the stat code (pts/reb/…) on pick rows. "
            "Actuals are filled by a later upsert. Only the current season is writable "
            "unless a backfill passes allow_historical. A _COMPLETE marker freezes the season."
        ),
        columns=_season_cols()
        + (
            _col("game_id", "VARCHAR", False, "NBA game id."),
            _col("game_date", "DATE", False, "Game date."),
            _col("row_kind", "VARCHAR", False, "player, game, or pick."),
            _col("player_id", "INTEGER", True, "Player id on player/pick rows. Null on game rows."),
            _col("team_abbr", "VARCHAR", True, "Player's team, or null on game rows."),
            _col("opponent_abbr", "VARCHAR", True, "Opponent abbreviation on player/pick rows."),
            _col("home_abbr", "VARCHAR", True, "Home team on game rows."),
            _col("away_abbr", "VARCHAR", True, "Away team on game rows."),
            _col("simulated_at", "TIMESTAMP", False, "UTC time the summary was produced."),
            _col("runs", "INTEGER", False, "Number of simulations summarized into this row."),
            _col("seed", "INTEGER", True, "Seed used for the run, when one was set."),
            _col("home_win_prob", "DOUBLE", True, "Probability the home team wins. Game rows only."),
            _col("overtime_prob", "DOUBLE", True, "Probability the game reaches overtime. Game rows only."),
            _col("actual_home_pts", "INTEGER", True, "Actual home points. Game rows only, null before final."),
            _col("actual_away_pts", "INTEGER", True, "Actual away points. Game rows only, null before final."),
            _col("actual_overtime", "BOOLEAN", True, "True when the game reached overtime."),
            _col(
                "pick_stat",
                "VARCHAR",
                False,
                "Empty on player/game rows; pts/reb/ast/stl/blk or dd_<pair> on pick rows (part of key).",
            ),
            _col("pick_lo", "DOUBLE", True, "Claimed range low on pick rows."),
            _col("pick_hi", "DOUBLE", True, "Claimed range high on pick rows."),
            _col("pick_median", "DOUBLE", True, "Claimed median on pick rows."),
            _col("pick_confidence", "DOUBLE", True, "Claimed in-sim confidence 0–1 on pick rows."),
            _col("pick_proj_min", "DOUBLE", True, "Projected median minutes at pick time."),
            _col(
                "actual_pick_hit",
                "BOOLEAN",
                True,
                "True when actual stat landed in [pick_lo, pick_hi]. Null before final.",
            ),
        )
        + _player_distribution_columns()
        + _game_distribution_columns(),
    )
    lineup_stints = Table(
        name="lineup_stints",
        policy="replace",
        key=("game_id", "team_id", "period", "p1", "p2", "p3", "p4", "p5", "duration_sec"),
        grain="one row per on-court lineup stretch",
        description=(
            "Compact lineup stints from PlayByPlayV3. Duration, possessions, and "
            "score-margin bucket support substitution models without storing raw PBP. "
            "Players are stored sorted ascending so the composite key is stable."
        ),
        columns=_season_cols()
        + (
            _col("game_id", "VARCHAR", False, "NBA game id."),
            _col("game_date", "DATE", False, "Game date."),
            _col("team_id", "INTEGER", False, "Team on the floor."),
            _col("opponent_team_id", "INTEGER", False, "Opposing team id."),
            _col("home_away", "VARCHAR", False, "H or A."),
            _col("period", "INTEGER", False, "Period number (1–4 regulation, 5+ OT)."),
            _col("duration_sec", "DOUBLE", False, "Seconds this lineup stayed on the floor."),
            _col("possessions", "INTEGER", False, "Possession endings while this lineup was out."),
            _col("margin_bucket", "VARCHAR", False, "close / moderate / blowout from team margin."),
            _col("team_margin", "INTEGER", False, "Team points minus opponent at stint midpoint."),
            _col("plus_minus", "INTEGER", True, "Team scoring differential change during this stint."),
            _col("p1", "INTEGER", False, "On-court player id (sorted)."),
            _col("p2", "INTEGER", False, "On-court player id (sorted)."),
            _col("p3", "INTEGER", False, "On-court player id (sorted)."),
            _col("p4", "INTEGER", False, "On-court player id (sorted)."),
            _col("p5", "INTEGER", False, "On-court player id (sorted)."),
        ),
    )
    assist_edges = Table(
        name="assist_edges",
        policy="replace",
        key=("game_id", "team_id", "passer_id", "shooter_id"),
        grain="one row per passer→shooter pair with assists in a game",
        description=(
            "Compact assist network from play-by-play: who assisted whom. "
            "Only rows with assists > 0. Never stores raw PBP. Walk-forward "
            "filters by game_date < as_of."
        ),
        columns=_season_cols()
        + (
            _col("game_id", "VARCHAR", False, "NBA game id."),
            _col("game_date", "DATE", False, "Game date."),
            _col("team_id", "INTEGER", False, "Offense team id."),
            _col("passer_id", "INTEGER", False, "Player who recorded the assist."),
            _col("shooter_id", "INTEGER", False, "Player who made the assisted field goal."),
            _col("assists", "INTEGER", False, "Assisted makes from passer to shooter in this game."),
        ),
    )
    defender_impact = Table(
        name="defender_impact",
        policy="replace",
        key=("defender_id",),
        grain="one row per defender per season",
        description=(
            "Compact per-defender matchup defense from LeagueSeasonMatchups: "
            "FG%/3P% allowed and sample size. Never stores raw OFF×DEF rows. "
            "Walk-forward uses only prior-season partitions (same-season "
            "LeagueSeasonMatchups would leak)."
        ),
        columns=_season_cols()
        + (
            _col("defender_id", "INTEGER", False, "Defending player id."),
            _col("defender_name", "VARCHAR", False, "Defender display name."),
            _col("possessions", "DOUBLE", False, "Sum of partial matchup possessions."),
            _col("fga", "DOUBLE", False, "Matchup field-goal attempts faced."),
            _col("fgm", "DOUBLE", False, "Matchup field goals allowed."),
            _col("fg3a", "DOUBLE", False, "Matchup three-point attempts faced."),
            _col("fg3m", "DOUBLE", False, "Matchup threes allowed."),
            _col("pts", "DOUBLE", False, "Points allowed to the matched-up scorer."),
            _col("matchup_sec", "DOUBLE", False, "Seconds matched up."),
            _col("fg_pct", "DOUBLE", True, "Allowed FG% (fgm/fga)."),
            _col("fg3_pct", "DOUBLE", True, "Allowed 3P% (fg3m/fg3a)."),
        ),
    )
    play_types = Table(
        name="play_types",
        policy="replace",
        key=("entity_kind", "entity_id", "play_type", "side"),
        grain="one row per player-or-team × play type × offense/defense per season",
        description=(
            "Compact Synergy play-type rates from nba_api SynergyPlayTypes "
            "(possessions, frequency, PPP, TOV%/FT%/score%). Never stores raw "
            "API payloads. Walk-forward uses only the PREVIOUS season; live "
            "projections may blend current with prior (regressed to league)."
        ),
        columns=_season_cols()
        + (
            _col("entity_kind", "VARCHAR", False, "player or team."),
            _col("entity_id", "INTEGER", False, "player_id or team_id."),
            _col("entity_name", "VARCHAR", False, "Display name / team abbreviation."),
            _col("team_id", "INTEGER", True, "Team id (players: primary team; teams: same as entity_id)."),
            _col("play_type", "VARCHAR", False, "Canonical play type label (Isolation, Spot Up, …)."),
            _col("side", "VARCHAR", False, "offense or defense."),
            _col("possessions", "DOUBLE", False, "Synergy possessions sample."),
            _col("frequency", "DOUBLE", False, "Share of entity possessions of this type (0–1)."),
            _col("ppp", "DOUBLE", False, "Points per possession."),
            _col("tov_pct", "DOUBLE", False, "Turnover rate on these possessions (0–1)."),
            _col("ft_pct", "DOUBLE", False, "Free-throw / foul rate on these possessions (0–1)."),
            _col("score_pct", "DOUBLE", False, "Score rate on these possessions (0–1)."),
            _col("gp", "DOUBLE", False, "Games played in the Synergy sample."),
            _col("fetched_at", "VARCHAR", False, "UTC ISO timestamp of the fetch that wrote this partition."),
        ),
    )
    tables = (
        player_game_logs,
        team_game_results,
        schedule,
        player_game_rates,
        player_season_aggregates,
        team_season_aggregates,
        team_zone_defense,
        team_position_defense,
        team_rosters,
        current_rosters,
        prediction_history,
        lineup_stints,
        assist_edges,
        defender_impact,
        play_types,
    )
    return {table.name: table for table in tables}


TABLES: dict[str, Table] = _tables()


def render_schema_markdown() -> str:
    """Render SCHEMA.md from the table contracts."""
    lines = [
        "# Schema",
        "",
        "All analytical data is DuckDB-readable Parquet under `DATA_DIR`.",
        "Do not open data files to remember the layout. Use this document.",
        "",
        "Partition path: `{DATA_DIR}/{table}/season={season}/data.parquet`.",
        "One Parquet file per season. `season` looks like `2025-26`.",
        "",
        "Write policies:",
        "",
        "- `incremental_current`: add rows whose key is not already stored. Existing rows stay as written. Nightly runs may only touch `season.current` in config.yaml. Backfill passes `allow_historical` and, when a season is done, calls `mark_season_complete`. The `_COMPLETE` marker freezes that partition.",
        "- `replace`: delete the season partition and write it again. Used for derived rates and aggregates so they are never appended or versioned.",
        "- `upsert_current`: insert or replace rows by key in the current season. Used so prediction actuals can be filled without keeping every simulation draw.",
        "",
        "Not stored: raw API responses, raw play-by-play (optional compressed copy under `ARCHIVE_DIR` only, never read back), individual simulation runs, odds, lines, or betting edges. Official injury PDFs are downloaded, parsed in memory, and discarded in the same run. `overrides.yaml` in the repo supplies manual injury and minutes-cap changes; those rows are not written to `DATA_DIR`.",
        "",
        "Display JSON in `results/latest/` is overwritten each run and is not part of `DATA_DIR`.",
        "",
        "DuckDB is opened in memory. This project does not keep a `.duckdb` database.",
        "",
    ]
    for table in TABLES.values():
        key = ", ".join(f"`{column}`" for column in table.key)
        lines.extend(
            [
                f"## {table.name}",
                "",
                table.description,
                "",
                f"Policy: `{table.policy}`",
                "",
                f"Grain: {table.grain}",
                "",
                f"Key: {key}",
                "",
                "| column | type | null | description |",
                "| --- | --- | --- | --- |",
            ]
        )
        for column in table.columns:
            null = "yes" if column.nullable else "no"
            lines.append(
                f"| {column.name} | {column.type_name} | {null} | {column.description} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
