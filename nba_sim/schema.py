"""Parquet table contracts.

SCHEMA.md is rendered from this module. Change columns here, regenerate
SCHEMA.md, and keep the two in sync. Agents should read SCHEMA.md instead
of opening data files.
"""

from __future__ import annotations

from dataclasses import dataclass

import pyarrow as pa

SEASON_PATTERN = r"^\d{4}-\d{2}$"
ZONES = (
    "restricted_area",
    "paint_non_ra",
    "midrange",
    "left_corner_3",
    "right_corner_3",
    "above_break_3",
)
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
    prediction_history = Table(
        name="prediction_history",
        policy="upsert_current",
        key=("row_kind", "game_id", "player_id"),
        grain="one player row per player per game, plus one game row per game",
        description=(
            "Summary of a simulation, not the raw runs. "
            "row_kind is player or game. Player rows leave the game distribution null. "
            "Game rows leave player_id and the player distributions null. "
            "Actuals are filled by a later upsert. Only the current season is writable "
            "unless a backfill passes allow_historical. A _COMPLETE marker freezes the season."
        ),
        columns=_season_cols()
        + (
            _col("game_id", "VARCHAR", False, "NBA game id."),
            _col("game_date", "DATE", False, "Game date."),
            _col("row_kind", "VARCHAR", False, "player or game."),
            _col("player_id", "INTEGER", True, "Player id on player rows. Null on game rows."),
            _col("team_abbr", "VARCHAR", True, "Player's team, or null on game rows."),
            _col("opponent_abbr", "VARCHAR", True, "Opponent abbreviation on player rows."),
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
        )
        + _player_distribution_columns()
        + _game_distribution_columns(),
    )
    tables = (
        player_game_logs,
        team_game_results,
        schedule,
        player_game_rates,
        player_season_aggregates,
        team_season_aggregates,
        team_zone_defense,
        prediction_history,
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
