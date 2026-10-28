# Morning post-game update

Run this the morning after a slate. Grade every completed game that is not yet graded, through yesterday. Do not re-simulate. Do not use sportsbook lines, odds, or props.

Read `PROJECT_SPEC.md`, `PROGRESS.md`, and `results/season_scorecard.md` first.

1. Ingest completed 2026-27 games only (incremental). Snapshot `current_rosters`, refresh all 30 teams, and print adds and removes. `NbaSource` requires `log=`.
2. Fill actual results in `prediction_history` for every game that was simulated.
3. Grade each night separately: predicted vs actual winner, score, spread, and total; per-player predicted median vs actual for MIN, PTS, REB, AST, STL, and BLK; and whether each actual landed inside the 10th–90th range. Finals that were never simulated stay off the scorecard.
4. Grade the top confident stat lines on their own: hit rate next to average claimed confidence. Do not mix these with double-double rows.
5. Grade the double-double picks on their own: actual hit rate vs average claimed P(DD), and list each pick with its result. A double-double hit means two of PTS, REB, AST, STL, and BLK were 10 or more.
6. Reconcile last night's simulated games: sum predicted means against the box scores and report any of MIN, PTS, REB, AST, STL, BLK, or TOV off by more than 3%. Also report the season-to-date average total bias (predicted median total minus actual).
7. Update `results/season_scorecard.md` with season-to-date totals and a per-night row. Show the full per-night table.
8. Print the storage report. Update `PROGRESS.md`, commit, and push. Leave `results/latest/slate_report.md` and `.env` uncommitted.
