# Schema

All analytical data is DuckDB-readable Parquet under `DATA_DIR`.
Do not open data files to remember the layout. Use this document.

Partition path: `{DATA_DIR}/{table}/season={season}/data.parquet`.
One Parquet file per season. `season` looks like `2025-26`.

Write policies:

- `incremental_current`: add rows whose key is not already stored. Existing rows stay as written. Nightly runs may only touch `season.current` in config.yaml. Backfill passes `allow_historical` and, when a season is done, calls `mark_season_complete`. The `_COMPLETE` marker freezes that partition.
- `replace`: delete the season partition and write it again. Used for derived rates and aggregates so they are never appended or versioned.
- `upsert_current`: insert or replace rows by key in the current season. Used so prediction actuals can be filled without keeping every simulation draw.

Not stored: raw API responses, raw play-by-play (optional compressed copy under `ARCHIVE_DIR` only, never read back), individual simulation runs, odds, lines, or betting edges. Official injury PDFs are downloaded, parsed in memory, and discarded in the same run. `overrides.yaml` in the repo supplies manual injury and minutes-cap changes; those rows are not written to `DATA_DIR`.

Display JSON in `results/latest/` is overwritten each run and is not part of `DATA_DIR`.

DuckDB is opened in memory. This project does not keep a `.duckdb` database.

## player_game_logs

Compact box score for every player appearance. Completed seasons are frozen with a _COMPLETE marker and are never rewritten. The current season accepts new keys only. starter and position come from the live box score when that feed is available.

Policy: `incremental_current`

Grain: one row per player per game

Key: `game_id`, `player_id`

| column | type | null | description |
| --- | --- | --- | --- |
| season | VARCHAR | no | NBA season label, such as 2025-26. Partition key. |
| game_id | VARCHAR | no | NBA game id. |
| game_date | DATE | no | Game date in the NBA schedule. |
| player_id | INTEGER | no | NBA player id. |
| player_name | VARCHAR | no | Player display name. |
| team_id | INTEGER | no | Team the player appeared for. |
| team_abbr | VARCHAR | no | Team abbreviation. |
| opponent_team_id | INTEGER | no | Opposing team id. |
| opponent_abbr | VARCHAR | no | Opposing team abbreviation. |
| home_away | VARCHAR | no | H or A from this team's perspective. |
| win | BOOLEAN | no | True when the player's team won. |
| started | BOOLEAN | no | True when the player started. |
| position | VARCHAR | yes | Listed position when known. |
| minutes | DOUBLE | no | Minutes played. |
| pts | INTEGER | no | Points. |
| reb | INTEGER | no | Rebounds. |
| ast | INTEGER | no | Assists. |
| fg3m | INTEGER | no | Three-pointers made. |
| stl | INTEGER | no | Steals. |
| blk | INTEGER | no | Blocks. |
| tov | INTEGER | no | Turnovers. |
| fgm | INTEGER | no | Field goals made. |
| fga | INTEGER | no | Field goals attempted. |
| fg3a | INTEGER | no | Three-pointers attempted. |
| ftm | INTEGER | no | Free throws made. |
| fta | INTEGER | no | Free throws attempted. |
| oreb | INTEGER | no | Offensive rebounds. |
| dreb | INTEGER | no | Defensive rebounds. |
| plus_minus | INTEGER | yes | Plus-minus when the source provides it. |

## team_game_results

Final team result and pace. Two rows per game. Same freeze and incremental rules as player_game_logs.

Policy: `incremental_current`

Grain: one row per team per game

Key: `game_id`, `team_id`

| column | type | null | description |
| --- | --- | --- | --- |
| season | VARCHAR | no | NBA season label, such as 2025-26. Partition key. |
| game_id | VARCHAR | no | NBA game id. |
| game_date | DATE | no | Game date. |
| team_id | INTEGER | no | Team id. |
| team_abbr | VARCHAR | no | Team abbreviation. |
| opponent_team_id | INTEGER | no | Opposing team id. |
| opponent_abbr | VARCHAR | no | Opposing team abbreviation. |
| home_away | VARCHAR | no | H or A. |
| win | BOOLEAN | no | True when this team won. |
| pts | INTEGER | no | Points scored by this team. |
| opp_pts | INTEGER | no | Points allowed. |
| pace | DOUBLE | yes | Offensive possessions in this game when play-by-play is available. |
| overtime_periods | INTEGER | no | Number of overtime periods. 0 if regulation. |

## schedule

Season schedule. The current season is upserted so a scheduled game can be updated to final with scores, still as one row. Completed seasons are frozen with _COMPLETE and never rewritten.

Policy: `upsert_current`

Grain: one row per game

Key: `game_id`

| column | type | null | description |
| --- | --- | --- | --- |
| season | VARCHAR | no | NBA season label, such as 2025-26. Partition key. |
| game_id | VARCHAR | no | NBA game id. |
| game_date | DATE | no | Scheduled date. |
| home_team_id | INTEGER | no | Home team id. |
| away_team_id | INTEGER | no | Away team id. |
| home_abbr | VARCHAR | no | Home abbreviation. |
| away_abbr | VARCHAR | no | Away abbreviation. |
| status | VARCHAR | no | scheduled or final. |
| home_pts | INTEGER | yes | Home points once final. |
| away_pts | INTEGER | yes | Away points once final. |

## player_game_rates

Per-player, per-game rates derived from play-by-play. Historical seasons use PlayByPlayV3; the current season uses the live feed, which is also the fallback. Shot zones use the same cutoffs either way: at the rim inside 4 feet, short midrange inside 14 feet, long midrange, corner threes at or below 8.7 feet split by court side, and above-the-break threes. The season file is rewritten in place when new games are added, not appended as a new copy.

Policy: `replace`

Grain: one row per player per game

Key: `game_id`, `player_id`

| column | type | null | description |
| --- | --- | --- | --- |
| season | VARCHAR | no | NBA season label, such as 2025-26. Partition key. |
| game_id | VARCHAR | no | NBA game id. |
| game_date | DATE | no | Game date. |
| player_id | INTEGER | no | NBA player id. |
| team_id | INTEGER | no | Team id for this appearance. |
| minutes | DOUBLE | no | Minutes played. |
| possessions | DOUBLE | no | Team possessions while the player was on the court. |
| usage | DOUBLE | no | Share of on-court possessions the player used. |
| oreb_chances | DOUBLE | no | Offensive rebound chances. |
| dreb_chances | DOUBLE | no | Defensive rebound chances. |
| ast_chances | DOUBLE | no | Assist chances. |
| fta | DOUBLE | no | Free throws attempted. |
| ftm | DOUBLE | no | Free throws made. |
| restricted_area_fga | DOUBLE | no | This game's field-goal attempts from restricted area. |
| restricted_area_fgm | DOUBLE | no | This game's field goals made from restricted area. |
| paint_non_ra_fga | DOUBLE | no | This game's field-goal attempts from paint non ra. |
| paint_non_ra_fgm | DOUBLE | no | This game's field goals made from paint non ra. |
| midrange_fga | DOUBLE | no | This game's field-goal attempts from midrange. |
| midrange_fgm | DOUBLE | no | This game's field goals made from midrange. |
| left_corner_3_fga | DOUBLE | no | This game's field-goal attempts from left corner 3. |
| left_corner_3_fgm | DOUBLE | no | This game's field goals made from left corner 3. |
| right_corner_3_fga | DOUBLE | no | This game's field-goal attempts from right corner 3. |
| right_corner_3_fgm | DOUBLE | no | This game's field goals made from right corner 3. |
| above_break_3_fga | DOUBLE | no | This game's field-goal attempts from above break 3. |
| above_break_3_fgm | DOUBLE | no | This game's field goals made from above break 3. |

## player_season_aggregates

Season totals and rates. Overwritten each run. A traded player has one row per team.

Policy: `replace`

Grain: one row per player per team per season

Key: `player_id`, `team_id`

| column | type | null | description |
| --- | --- | --- | --- |
| season | VARCHAR | no | NBA season label, such as 2025-26. Partition key. |
| player_id | INTEGER | no | NBA player id. |
| team_id | INTEGER | no | Team id. |
| player_name | VARCHAR | no | Player display name. |
| position | VARCHAR | yes | Position used for regression priors. |
| games | INTEGER | no | Games played for this team. |
| minutes | DOUBLE | no | Total minutes. |
| possessions | DOUBLE | no | On-court possessions. |
| usage | DOUBLE | no | Season usage rate. |
| oreb_chances | DOUBLE | no | Offensive rebound chances. |
| dreb_chances | DOUBLE | no | Defensive rebound chances. |
| ast_chances | DOUBLE | no | Assist chances. |
| pts | INTEGER | no | Points total. |
| reb | INTEGER | no | Rebounds total. |
| ast | INTEGER | no | Assists total. |
| fg3m | INTEGER | no | Three-pointers made. |
| stl | INTEGER | no | Steals total. |
| blk | INTEGER | no | Blocks total. |
| tov | INTEGER | no | Turnovers total. |
| fta | DOUBLE | no | Free throws attempted. |
| ftm | DOUBLE | no | Free throws made. |
| restricted_area_fga | DOUBLE | no | Season field-goal attempts from restricted area. |
| restricted_area_fgm | DOUBLE | no | Season field goals made from restricted area. |
| paint_non_ra_fga | DOUBLE | no | Season field-goal attempts from paint non ra. |
| paint_non_ra_fgm | DOUBLE | no | Season field goals made from paint non ra. |
| midrange_fga | DOUBLE | no | Season field-goal attempts from midrange. |
| midrange_fgm | DOUBLE | no | Season field goals made from midrange. |
| left_corner_3_fga | DOUBLE | no | Season field-goal attempts from left corner 3. |
| left_corner_3_fgm | DOUBLE | no | Season field goals made from left corner 3. |
| right_corner_3_fga | DOUBLE | no | Season field-goal attempts from right corner 3. |
| right_corner_3_fgm | DOUBLE | no | Season field goals made from right corner 3. |
| above_break_3_fga | DOUBLE | no | Season field-goal attempts from above break 3. |
| above_break_3_fgm | DOUBLE | no | Season field goals made from above break 3. |

## team_season_aggregates

Team pace and scoring environment. Overwritten each run.

Policy: `replace`

Grain: one row per team per season

Key: `team_id`

| column | type | null | description |
| --- | --- | --- | --- |
| season | VARCHAR | no | NBA season label, such as 2025-26. Partition key. |
| team_id | INTEGER | no | Team id. |
| team_abbr | VARCHAR | no | Team abbreviation. |
| games | INTEGER | no | Games played. |
| pace | DOUBLE | no | Average possessions per game. |
| possessions_for | DOUBLE | no | Offensive possessions. |
| possessions_against | DOUBLE | no | Defensive possessions. |
| points_for | INTEGER | no | Points scored. |
| points_against | INTEGER | no | Points allowed. |

## team_zone_defense

Opponent shot-zone defense. zone is one of restricted_area, paint_non_ra, midrange, left_corner_3, right_corner_3, above_break_3. Overwritten each run.

Policy: `replace`

Grain: one row per team per shot zone per season

Key: `team_id`, `zone`

| column | type | null | description |
| --- | --- | --- | --- |
| season | VARCHAR | no | NBA season label, such as 2025-26. Partition key. |
| team_id | INTEGER | no | Defending team id. |
| zone | VARCHAR | no | Shot zone name. |
| fga | DOUBLE | no | Opponent attempts allowed in this zone. |
| fgm | DOUBLE | no | Opponent makes allowed in this zone. |
| possessions | DOUBLE | no | Defensive possessions in the sample. |

## team_position_defense

Opponent defense by position: box-score stats allowed to opposing PG/SG/SF/PF/C, derived from player game logs. Position labels are normalized from listed G/F/C (and None) using that game's reb/ast. Overwritten each run.

Policy: `replace`

Grain: one row per team per position (PG/SG/SF/PF/C) per season

Key: `team_id`, `position`

| column | type | null | description |
| --- | --- | --- | --- |
| season | VARCHAR | no | NBA season label, such as 2025-26. Partition key. |
| team_id | INTEGER | no | Defending team id. |
| position | VARCHAR | no | Opponent position: PG, SG, SF, PF, or C. |
| player_games | INTEGER | no | Opponent player-games at this position. |
| minutes | DOUBLE | no | Opponent minutes at this position. |
| pts | DOUBLE | no | Points allowed to this position. |
| reb | DOUBLE | no | Rebounds allowed to this position. |
| ast | DOUBLE | no | Assists allowed to this position. |
| fg3m | DOUBLE | no | Threes made allowed to this position. |
| stl | DOUBLE | no | Steals allowed to this position. |
| blk | DOUBLE | no | Blocks allowed to this position. |
| tov | DOUBLE | no | Turnovers forced from this position. |

## team_rosters

As-of-date team membership for projections and walk-forward backtests. Built primarily from player_game_logs: consecutive appearances for the same team become a stint with from_date equal to the first game date and to_date equal to the first game date on a different team (exclusive end), or null when the player is still on that team at season rebuild time. The current season may also merge CommonTeamRoster so signed/traded players appear before their first box score. Roster as of date D uses only rows with from_date < D and (to_date is null or D < to_date); never use future game logs. CommonTeamRoster is a current snapshot only — historical accuracy comes from game-log stints. Overwritten each derived rewrite.

Policy: `replace`

Grain: one row per player stint on a team within a season

Key: `team_id`, `player_id`, `from_date`

| column | type | null | description |
| --- | --- | --- | --- |
| season | VARCHAR | no | NBA season label, such as 2025-26. Partition key. |
| team_id | INTEGER | no | Team id for this stint. |
| team_abbr | VARCHAR | no | Team abbreviation. |
| player_id | INTEGER | no | NBA player id. |
| player_name | VARCHAR | no | Player display name. |
| position | VARCHAR | yes | Listed position when known. |
| from_date | DATE | no | First date the player is known on this team (exclusive lower bound for as-of: from_date < D). |
| to_date | DATE | yes | First date no longer on this team (exclusive). Null if still on the team. |
| jersey | VARCHAR | yes | Jersey number when known from CommonTeamRoster. |
| roster_status | VARCHAR | yes | Optional roster status from the API when available. |
| source | VARCHAR | no | game_log or common_roster. |

## current_rosters

Live snapshot of every team's roster for season.current from stats.nba.com CommonTeamRoster. Refreshed on every daily.py run. Also notes whether the player has appeared in that team's Preseason box scores this season (preseason_appeared). Current-season projections must use this table and must not include anyone absent from it. Historical walk-forward continues to use team_rosters stints.

Policy: `replace`

Grain: one row per player on a team's live CommonTeamRoster

Key: `team_id`, `player_id`

| column | type | null | description |
| --- | --- | --- | --- |
| season | VARCHAR | no | NBA season label, such as 2025-26. Partition key. |
| team_id | INTEGER | no | Team id. |
| team_abbr | VARCHAR | no | Team abbreviation. |
| player_id | INTEGER | no | NBA player id. |
| player_name | VARCHAR | no | Player display name. |
| position | VARCHAR | yes | Listed position when known. |
| jersey | VARCHAR | yes | Jersey number when known. |
| preseason_appeared | BOOLEAN | no | True if the player logged minutes for this team in a 2026-27 Preseason box score. |
| refreshed_at | TIMESTAMP | no | UTC time this snapshot was written. |

## prediction_history

Summary of a simulation, not the raw runs. row_kind is player, game, or pick. Player rows leave the game distribution null. Game rows leave player_id and the player distributions null. Pick rows store claimed confidence ranges for tonight's top lines; actual_pick_hit is filled after the game. pick_stat is '' on player/game rows, a stat code (pts/reb/…) on confident-line rows, and dd_<pair> on double-double rows. Actuals are filled by a later upsert. Only the current season is writable unless a backfill passes allow_historical. A _COMPLETE marker freezes the season.

Policy: `upsert_current`

Grain: one player row per player per game, one game row per game, and optional pick rows (row_kind=pick) for top confident stat lines

Key: `row_kind`, `game_id`, `player_id`, `pick_stat`

| column | type | null | description |
| --- | --- | --- | --- |
| season | VARCHAR | no | NBA season label, such as 2025-26. Partition key. |
| game_id | VARCHAR | no | NBA game id. |
| game_date | DATE | no | Game date. |
| row_kind | VARCHAR | no | player, game, or pick. |
| player_id | INTEGER | yes | Player id on player/pick rows. Null on game rows. |
| team_abbr | VARCHAR | yes | Player's team, or null on game rows. |
| opponent_abbr | VARCHAR | yes | Opponent abbreviation on player/pick rows. |
| home_abbr | VARCHAR | yes | Home team on game rows. |
| away_abbr | VARCHAR | yes | Away team on game rows. |
| simulated_at | TIMESTAMP | no | UTC time the summary was produced. |
| runs | INTEGER | no | Number of simulations summarized into this row. |
| seed | INTEGER | yes | Seed used for the run, when one was set. |
| home_win_prob | DOUBLE | yes | Probability the home team wins. Game rows only. |
| overtime_prob | DOUBLE | yes | Probability the game reaches overtime. Game rows only. |
| actual_home_pts | INTEGER | yes | Actual home points. Game rows only, null before final. |
| actual_away_pts | INTEGER | yes | Actual away points. Game rows only, null before final. |
| actual_overtime | BOOLEAN | yes | True when the game reached overtime. |
| pick_stat | VARCHAR | no | Empty on player/game rows; pts/reb/ast/stl/blk or dd_<pair> on pick rows (part of key). |
| pick_lo | DOUBLE | yes | Claimed range low on pick rows. |
| pick_hi | DOUBLE | yes | Claimed range high on pick rows. |
| pick_median | DOUBLE | yes | Claimed median on pick rows. |
| pick_confidence | DOUBLE | yes | Claimed in-sim confidence 0–1 on pick rows. |
| pick_proj_min | DOUBLE | yes | Projected median minutes at pick time. |
| actual_pick_hit | BOOLEAN | yes | True when actual stat landed in [pick_lo, pick_hi]. Null before final. |
| pred_pts_mean | DOUBLE | yes | Predicted pts mean. Null on game rows. |
| pred_pts_p10 | DOUBLE | yes | Predicted pts p10. Null on game rows. |
| pred_pts_p25 | DOUBLE | yes | Predicted pts p25. Null on game rows. |
| pred_pts_p50 | DOUBLE | yes | Predicted pts p50. Null on game rows. |
| pred_pts_p75 | DOUBLE | yes | Predicted pts p75. Null on game rows. |
| pred_pts_p90 | DOUBLE | yes | Predicted pts p90. Null on game rows. |
| actual_pts | DOUBLE | yes | Actual pts after the game. Null until the game is final, and null on game rows. |
| pred_reb_mean | DOUBLE | yes | Predicted reb mean. Null on game rows. |
| pred_reb_p10 | DOUBLE | yes | Predicted reb p10. Null on game rows. |
| pred_reb_p25 | DOUBLE | yes | Predicted reb p25. Null on game rows. |
| pred_reb_p50 | DOUBLE | yes | Predicted reb p50. Null on game rows. |
| pred_reb_p75 | DOUBLE | yes | Predicted reb p75. Null on game rows. |
| pred_reb_p90 | DOUBLE | yes | Predicted reb p90. Null on game rows. |
| actual_reb | DOUBLE | yes | Actual reb after the game. Null until the game is final, and null on game rows. |
| pred_ast_mean | DOUBLE | yes | Predicted ast mean. Null on game rows. |
| pred_ast_p10 | DOUBLE | yes | Predicted ast p10. Null on game rows. |
| pred_ast_p25 | DOUBLE | yes | Predicted ast p25. Null on game rows. |
| pred_ast_p50 | DOUBLE | yes | Predicted ast p50. Null on game rows. |
| pred_ast_p75 | DOUBLE | yes | Predicted ast p75. Null on game rows. |
| pred_ast_p90 | DOUBLE | yes | Predicted ast p90. Null on game rows. |
| actual_ast | DOUBLE | yes | Actual ast after the game. Null until the game is final, and null on game rows. |
| pred_fg3m_mean | DOUBLE | yes | Predicted fg3m mean. Null on game rows. |
| pred_fg3m_p10 | DOUBLE | yes | Predicted fg3m p10. Null on game rows. |
| pred_fg3m_p25 | DOUBLE | yes | Predicted fg3m p25. Null on game rows. |
| pred_fg3m_p50 | DOUBLE | yes | Predicted fg3m p50. Null on game rows. |
| pred_fg3m_p75 | DOUBLE | yes | Predicted fg3m p75. Null on game rows. |
| pred_fg3m_p90 | DOUBLE | yes | Predicted fg3m p90. Null on game rows. |
| actual_fg3m | DOUBLE | yes | Actual fg3m after the game. Null until the game is final, and null on game rows. |
| pred_stl_mean | DOUBLE | yes | Predicted stl mean. Null on game rows. |
| pred_stl_p10 | DOUBLE | yes | Predicted stl p10. Null on game rows. |
| pred_stl_p25 | DOUBLE | yes | Predicted stl p25. Null on game rows. |
| pred_stl_p50 | DOUBLE | yes | Predicted stl p50. Null on game rows. |
| pred_stl_p75 | DOUBLE | yes | Predicted stl p75. Null on game rows. |
| pred_stl_p90 | DOUBLE | yes | Predicted stl p90. Null on game rows. |
| actual_stl | DOUBLE | yes | Actual stl after the game. Null until the game is final, and null on game rows. |
| pred_blk_mean | DOUBLE | yes | Predicted blk mean. Null on game rows. |
| pred_blk_p10 | DOUBLE | yes | Predicted blk p10. Null on game rows. |
| pred_blk_p25 | DOUBLE | yes | Predicted blk p25. Null on game rows. |
| pred_blk_p50 | DOUBLE | yes | Predicted blk p50. Null on game rows. |
| pred_blk_p75 | DOUBLE | yes | Predicted blk p75. Null on game rows. |
| pred_blk_p90 | DOUBLE | yes | Predicted blk p90. Null on game rows. |
| actual_blk | DOUBLE | yes | Actual blk after the game. Null until the game is final, and null on game rows. |
| pred_tov_mean | DOUBLE | yes | Predicted tov mean. Null on game rows. |
| pred_tov_p10 | DOUBLE | yes | Predicted tov p10. Null on game rows. |
| pred_tov_p25 | DOUBLE | yes | Predicted tov p25. Null on game rows. |
| pred_tov_p50 | DOUBLE | yes | Predicted tov p50. Null on game rows. |
| pred_tov_p75 | DOUBLE | yes | Predicted tov p75. Null on game rows. |
| pred_tov_p90 | DOUBLE | yes | Predicted tov p90. Null on game rows. |
| actual_tov | DOUBLE | yes | Actual tov after the game. Null until the game is final, and null on game rows. |
| pred_min_mean | DOUBLE | yes | Predicted min mean. Null on game rows. |
| pred_min_p10 | DOUBLE | yes | Predicted min p10. Null on game rows. |
| pred_min_p25 | DOUBLE | yes | Predicted min p25. Null on game rows. |
| pred_min_p50 | DOUBLE | yes | Predicted min p50. Null on game rows. |
| pred_min_p75 | DOUBLE | yes | Predicted min p75. Null on game rows. |
| pred_min_p90 | DOUBLE | yes | Predicted min p90. Null on game rows. |
| actual_min | DOUBLE | yes | Actual min after the game. Null until the game is final, and null on game rows. |
| pred_pra_mean | DOUBLE | yes | Predicted pra mean. Null on game rows. |
| pred_pra_p10 | DOUBLE | yes | Predicted pra p10. Null on game rows. |
| pred_pra_p25 | DOUBLE | yes | Predicted pra p25. Null on game rows. |
| pred_pra_p50 | DOUBLE | yes | Predicted pra p50. Null on game rows. |
| pred_pra_p75 | DOUBLE | yes | Predicted pra p75. Null on game rows. |
| pred_pra_p90 | DOUBLE | yes | Predicted pra p90. Null on game rows. |
| actual_pra | DOUBLE | yes | Actual pra after the game. Null until the game is final, and null on game rows. |
| pred_pr_mean | DOUBLE | yes | Predicted pr mean. Null on game rows. |
| pred_pr_p10 | DOUBLE | yes | Predicted pr p10. Null on game rows. |
| pred_pr_p25 | DOUBLE | yes | Predicted pr p25. Null on game rows. |
| pred_pr_p50 | DOUBLE | yes | Predicted pr p50. Null on game rows. |
| pred_pr_p75 | DOUBLE | yes | Predicted pr p75. Null on game rows. |
| pred_pr_p90 | DOUBLE | yes | Predicted pr p90. Null on game rows. |
| actual_pr | DOUBLE | yes | Actual pr after the game. Null until the game is final, and null on game rows. |
| pred_pa_mean | DOUBLE | yes | Predicted pa mean. Null on game rows. |
| pred_pa_p10 | DOUBLE | yes | Predicted pa p10. Null on game rows. |
| pred_pa_p25 | DOUBLE | yes | Predicted pa p25. Null on game rows. |
| pred_pa_p50 | DOUBLE | yes | Predicted pa p50. Null on game rows. |
| pred_pa_p75 | DOUBLE | yes | Predicted pa p75. Null on game rows. |
| pred_pa_p90 | DOUBLE | yes | Predicted pa p90. Null on game rows. |
| actual_pa | DOUBLE | yes | Actual pa after the game. Null until the game is final, and null on game rows. |
| pred_ra_mean | DOUBLE | yes | Predicted ra mean. Null on game rows. |
| pred_ra_p10 | DOUBLE | yes | Predicted ra p10. Null on game rows. |
| pred_ra_p25 | DOUBLE | yes | Predicted ra p25. Null on game rows. |
| pred_ra_p50 | DOUBLE | yes | Predicted ra p50. Null on game rows. |
| pred_ra_p75 | DOUBLE | yes | Predicted ra p75. Null on game rows. |
| pred_ra_p90 | DOUBLE | yes | Predicted ra p90. Null on game rows. |
| actual_ra | DOUBLE | yes | Actual ra after the game. Null until the game is final, and null on game rows. |
| pred_home_pts_mean | DOUBLE | yes | Predicted home_pts mean. Margin is home minus away. Null on player rows. |
| pred_home_pts_p10 | DOUBLE | yes | Predicted home_pts p10. Margin is home minus away. Null on player rows. |
| pred_home_pts_p25 | DOUBLE | yes | Predicted home_pts p25. Margin is home minus away. Null on player rows. |
| pred_home_pts_p50 | DOUBLE | yes | Predicted home_pts p50. Margin is home minus away. Null on player rows. |
| pred_home_pts_p75 | DOUBLE | yes | Predicted home_pts p75. Margin is home minus away. Null on player rows. |
| pred_home_pts_p90 | DOUBLE | yes | Predicted home_pts p90. Margin is home minus away. Null on player rows. |
| pred_away_pts_mean | DOUBLE | yes | Predicted away_pts mean. Margin is home minus away. Null on player rows. |
| pred_away_pts_p10 | DOUBLE | yes | Predicted away_pts p10. Margin is home minus away. Null on player rows. |
| pred_away_pts_p25 | DOUBLE | yes | Predicted away_pts p25. Margin is home minus away. Null on player rows. |
| pred_away_pts_p50 | DOUBLE | yes | Predicted away_pts p50. Margin is home minus away. Null on player rows. |
| pred_away_pts_p75 | DOUBLE | yes | Predicted away_pts p75. Margin is home minus away. Null on player rows. |
| pred_away_pts_p90 | DOUBLE | yes | Predicted away_pts p90. Margin is home minus away. Null on player rows. |
| pred_margin_mean | DOUBLE | yes | Predicted margin mean. Margin is home minus away. Null on player rows. |
| pred_margin_p10 | DOUBLE | yes | Predicted margin p10. Margin is home minus away. Null on player rows. |
| pred_margin_p25 | DOUBLE | yes | Predicted margin p25. Margin is home minus away. Null on player rows. |
| pred_margin_p50 | DOUBLE | yes | Predicted margin p50. Margin is home minus away. Null on player rows. |
| pred_margin_p75 | DOUBLE | yes | Predicted margin p75. Margin is home minus away. Null on player rows. |
| pred_margin_p90 | DOUBLE | yes | Predicted margin p90. Margin is home minus away. Null on player rows. |
| pred_total_mean | DOUBLE | yes | Predicted total mean. Margin is home minus away. Null on player rows. |
| pred_total_p10 | DOUBLE | yes | Predicted total p10. Margin is home minus away. Null on player rows. |
| pred_total_p25 | DOUBLE | yes | Predicted total p25. Margin is home minus away. Null on player rows. |
| pred_total_p50 | DOUBLE | yes | Predicted total p50. Margin is home minus away. Null on player rows. |
| pred_total_p75 | DOUBLE | yes | Predicted total p75. Margin is home minus away. Null on player rows. |
| pred_total_p90 | DOUBLE | yes | Predicted total p90. Margin is home minus away. Null on player rows. |

## lineup_stints

Compact lineup stints from PlayByPlayV3. Duration, possessions, and score-margin bucket support substitution models without storing raw PBP. Players are stored sorted ascending so the composite key is stable.

Policy: `replace`

Grain: one row per on-court lineup stretch

Key: `game_id`, `team_id`, `period`, `p1`, `p2`, `p3`, `p4`, `p5`, `duration_sec`

| column | type | null | description |
| --- | --- | --- | --- |
| season | VARCHAR | no | NBA season label, such as 2025-26. Partition key. |
| game_id | VARCHAR | no | NBA game id. |
| game_date | DATE | no | Game date. |
| team_id | INTEGER | no | Team on the floor. |
| opponent_team_id | INTEGER | no | Opposing team id. |
| home_away | VARCHAR | no | H or A. |
| period | INTEGER | no | Period number (1–4 regulation, 5+ OT). |
| duration_sec | DOUBLE | no | Seconds this lineup stayed on the floor. |
| possessions | INTEGER | no | Possession endings while this lineup was out. |
| margin_bucket | VARCHAR | no | close / moderate / blowout from team margin. |
| team_margin | INTEGER | no | Team points minus opponent at stint midpoint. |
| plus_minus | INTEGER | yes | Team scoring differential change during this stint. |
| p1 | INTEGER | no | On-court player id (sorted). |
| p2 | INTEGER | no | On-court player id (sorted). |
| p3 | INTEGER | no | On-court player id (sorted). |
| p4 | INTEGER | no | On-court player id (sorted). |
| p5 | INTEGER | no | On-court player id (sorted). |

## assist_edges

Compact assist network from play-by-play: who assisted whom. Only rows with assists > 0. Never stores raw PBP. Walk-forward filters by game_date < as_of.

Policy: `replace`

Grain: one row per passer→shooter pair with assists in a game

Key: `game_id`, `team_id`, `passer_id`, `shooter_id`

| column | type | null | description |
| --- | --- | --- | --- |
| season | VARCHAR | no | NBA season label, such as 2025-26. Partition key. |
| game_id | VARCHAR | no | NBA game id. |
| game_date | DATE | no | Game date. |
| team_id | INTEGER | no | Offense team id. |
| passer_id | INTEGER | no | Player who recorded the assist. |
| shooter_id | INTEGER | no | Player who made the assisted field goal. |
| assists | INTEGER | no | Assisted makes from passer to shooter in this game. |

## defender_impact

Compact per-defender matchup defense from LeagueSeasonMatchups: FG%/3P% allowed and sample size. Never stores raw OFF×DEF rows. Walk-forward uses only prior-season partitions (same-season LeagueSeasonMatchups would leak).

Policy: `replace`

Grain: one row per defender per season

Key: `defender_id`

| column | type | null | description |
| --- | --- | --- | --- |
| season | VARCHAR | no | NBA season label, such as 2025-26. Partition key. |
| defender_id | INTEGER | no | Defending player id. |
| defender_name | VARCHAR | no | Defender display name. |
| possessions | DOUBLE | no | Sum of partial matchup possessions. |
| fga | DOUBLE | no | Matchup field-goal attempts faced. |
| fgm | DOUBLE | no | Matchup field goals allowed. |
| fg3a | DOUBLE | no | Matchup three-point attempts faced. |
| fg3m | DOUBLE | no | Matchup threes allowed. |
| pts | DOUBLE | no | Points allowed to the matched-up scorer. |
| matchup_sec | DOUBLE | no | Seconds matched up. |
| fg_pct | DOUBLE | yes | Allowed FG% (fgm/fga). |
| fg3_pct | DOUBLE | yes | Allowed 3P% (fg3m/fg3a). |

## play_types

Compact Synergy play-type rates from nba_api SynergyPlayTypes (possessions, frequency, PPP, TOV%/FT%/score%). Never stores raw API payloads. Walk-forward uses only the PREVIOUS season; live projections may blend current with prior (regressed to league).

Policy: `replace`

Grain: one row per player-or-team × play type × offense/defense per season

Key: `entity_kind`, `entity_id`, `play_type`, `side`

| column | type | null | description |
| --- | --- | --- | --- |
| season | VARCHAR | no | NBA season label, such as 2025-26. Partition key. |
| entity_kind | VARCHAR | no | player or team. |
| entity_id | INTEGER | no | player_id or team_id. |
| entity_name | VARCHAR | no | Display name / team abbreviation. |
| team_id | INTEGER | yes | Team id (players: primary team; teams: same as entity_id). |
| play_type | VARCHAR | no | Canonical play type label (Isolation, Spot Up, …). |
| side | VARCHAR | no | offense or defense. |
| possessions | DOUBLE | no | Synergy possessions sample. |
| frequency | DOUBLE | no | Share of entity possessions of this type (0–1). |
| ppp | DOUBLE | no | Points per possession. |
| tov_pct | DOUBLE | no | Turnover rate on these possessions (0–1). |
| ft_pct | DOUBLE | no | Free-throw / foul rate on these possessions (0–1). |
| score_pct | DOUBLE | no | Score rate on these possessions (0–1). |
| gp | DOUBLE | no | Games played in the Synergy sample. |
| fetched_at | VARCHAR | no | UTC ISO timestamp of the fetch that wrote this partition. |

**Leakage:** For walk-forward season S, load only season S−1. For live `current_season`, blend current with prior (possession half-life). Rates are regressed to league averages by play type using possessions.

**Play types stored:** Isolation, P&R Ball Handler, P&R Roll Man, Post Up, Spot Up, Handoff, Cut, Off Screen, Transition, Putbacks, Misc.

## external/referees/ (NBA officials)

Not a season-partitioned engine table. Compact Parquet under `{DATA_DIR}/external/referees/`, written by `ingest/referees.py`. The live crew (crew chief, referee, umpire) is parsed from the public assignments table at [official.nba.com/referee-assignments](https://official.nba.com/referee-assignments/), at most once per day. Historical crews come from stats.nba.com `boxscoresummaryv3` (the officials list on each game's box score summary), one game at a time, for 2023-24 through the current season. Personal fouls are the sum of both teams' `PF` from `leaguegamelog`, one request per season. Raw HTML and JSON are not stored. Credit: NBA.com.

Files (latest + `.prev.parquet` fallback):

- `assignments.parquet` — today's NBA crews (date, away, home, role, name, jersey). The WNBA table on the same page is ignored.
- `game_officials.parquet` — one row per official per game (`official_id`, name, jersey, role). Box scores do not label the role, so the first three names are stored as crew chief, referee, and umpire in listed order. Alternates are dropped.
- `officials_gaps.parquet` — game ids whose summary had no crew, so they are not requested again.
- `game_fouls.parquet` — game id and combined personal fouls.
- `game_environment.parquet` — regulation pace, possessions, free throws, fouls, and points joined from our logs.
- `referees_meta.parquet` — fetch time and row counts.

**Leakage:** A slate on date D uses only games with `game_date < D`. Each official's residual (fouls and FTA per 100 possessions, pace, points versus the league mean of those prior games) is shrunk toward zero with `referees_prior_games` pseudo-games. The three-official mean scales expected possessions and `ft_rate`, clipped by `referees_factor_clip`. The points residual is recorded and not applied. The sim uses this only when `referees_enabled` is true.

## external/injuries/ (historical injury reports)

Not a season-partitioned engine table. Compact Parquet under `{DATA_DIR}/external/injuries/`, written by `ingest/injury_archive.py`. 2024-25 and 2025-26 reports use hour-only CDN names (`Injury-Report_YYYY-MM-DD_05PM.pdf`). The PDF is parsed in memory and not stored. Credit: NBA.com.

- `reports.parquet` — one row per player on the latest report whose clock time is strictly before that game's tip. Both times come from the PDF.
- `dates.parquet` — game dates already attempted, so a rerun does not download them again.

The live slate still uses `ingest/injuries.py`, which looks up the current season's `HH_MMPM` files and does not write them. Walk-forward does not read `reports.parquet` until that wiring is turned on.

## external/bballindex/ (Basketball Index)

Not a season-partitioned engine table. Compact Parquet under `{DATA_DIR}/external/bballindex/`, written by `ingest/bball_index.py`. The leaderboard tool fills its grid from a DataTables JSON POST (`session/.../dataobj/query_table`); we request that same JSON and do not parse page HTML. Credit: [Basketball Index](https://www.bball-index.com/). Personal use only — these files are gitignored and must not be redistributed.

Auth is the `BBALL_INDEX_COOKIE` environment variable (a browser session cookie). It is never written to logs, config, or git. 2024-25 and 2025-26 are fetched once. 2026-27 is fetched at most every `bball_index_fetch_interval_days` (default 7). A failed fetch keeps the previous parquet.

Files (latest + `.prev.parquet` fallback):

- `roles_{season}.parquet` — rotation / offensive / defensive role, offense position (PG–C), opportunity rates
- `defense_{season}.parquet` — perimeter and interior defense grades
- `play_types_{season}.parquet` — stable play-type points per possession
- `matchup_{season}.parquet` — matchup difficulty and share of time guarding each position
- `playmaking_{season}.parquet` — playmaking grades
- `rebounding_{season}.parquet` — offensive and defensive rebounding grades
- `bball_index_meta.parquet` — fetch time, row count, status

**Leakage:** Walk-forward of season S loads only season S−1. The live current season may use its own weekly file when one exists. Offense position replaces the G/F/C heuristic only when `bball_roles_enabled` is true. Defense grades and play-type PPP adjust FG% only when their flags are true. When `bball_matchups_enabled` is true, prior-season time spent guarding each position chooses the primary defender.

Identity columns on every dataset: `player_id`, `player_name`, `season`, `age`, `team_abbr`, `minutes`, `rotation_role`, `offensive_role`, `defensive_role`, plus the dataset's metric columns (snake_case of the tool's labels). The roles table also stores `offense_position` (PG/SG/SF/PF/C) from the Offense Position metric.

## external/ (nbarapm.com RAPM)

Not a season-partitioned table. Compact Parquet under `{DATA_DIR}/external/`, refreshed by `ingest/rapm_fetch.py` at most every 7 days from the published JSON data files the nbarapm dataset pages load (`/load/timedecay`, `/load/SCALEDOUTPUT_SMALLER`). The site's "Download CSV" button builds a CSV in-browser from those same files — we never scrape HTML. Credit: [nbarapm.com](https://nbarapm.com).

Files (latest overwrite + `.prev.parquet` fallback):

- `nbarapm_timedecay.parquet` — current time-decay RAPM (one row per player)
- `nbarapm_six_factor.parquet` — six-factor splits (`Year_Interval` in TD/3Y/5Y)
- `nbarapm_meta.parquet` — last fetch / site `as_of` stamps

**Leakage rules:** Time-decay (`as_of_date` on the file) may only be used when the projected season's Oct 1 start is strictly after that date (live post-snapshot seasons). Walk-forward / earlier seasons load six-factor rows with `latest_year <= season_start_year` (prior completed season), preferring `3Y` then `5Y`. Do not use six-factor `TD` / timedecay for 2025-26 backtests — those vintages include 2025-26.

**Six-factor grain:** one row per `(player_id, latest_year, year_interval)`. `latest_year` is the end-year of the window (2025 ≈ through 2024-25). Intervals: rolling `3Y` and `5Y` for years ~1999–2026; `TD` only on the newest vintage (currently 2026, same family as timedecay).
### nbarapm_timedecay columns

| column | type | null | description |
| --- | --- | --- | --- |
| player_id | INTEGER | no | NBA player id (`nba_id`). |
| player_name | VARCHAR | no | Display name. |
| team_abbr | VARCHAR | no | Team abbreviation when provided. |
| year | INTEGER | yes | Latest year on the rating. |
| year_interval | VARCHAR | no | Usually `TD`. |
| rapm | DOUBLE | no | Net RAPM (pts/100). |
| orapm | DOUBLE | yes | Offensive RAPM. |
| drapm | DOUBLE | yes | Defensive RAPM. |
| off_poss | INTEGER | yes | Offensive possessions sample. |
| minutes | DOUBLE | yes | Minutes sample (`MP2`). |
| half_life_days | DOUBLE | yes | Time-decay half-life. |
| source_updated | VARCHAR | yes | Site `as_of_date` (YYYY-MM-DD). |
| fetched_at | VARCHAR | no | UTC ISO timestamp of our download. |
| source | VARCHAR | no | URL label (`nbarapm.com/load/timedecay`). |

### nbarapm_six_factor columns

| column | type | null | description |
| --- | --- | --- | --- |
| player_id | INTEGER | no | NBA player id. |
| player_name | VARCHAR | no | Display name. |
| latest_year | INTEGER | no | End year of the window. |
| year_interval | VARCHAR | no | `TD`, `3Y`, or `5Y`. |
| rapm / orapm / drapm | DOUBLE | mixed | Overall / off / def RAPM. |
| sc_off_ts, sc_off_tov, sc_off_reb, sc_def_ts, sc_def_tov, sc_def_reb, sc_poss | DOUBLE | yes | Six-factor components. |
| source_updated | VARCHAR | yes | Derived from max `Latest_Year` when the file has no `as_of`. |
| fetched_at | VARCHAR | no | UTC ISO timestamp of our download. |
| source | VARCHAR | no | URL label. |
