"""Sanity flags and the post-sim play card."""

from datetime import date

from outputs.calibration import CalibrationCell, CalibrationTable
from outputs.edge_plays import calibrated_stats, close_line_value, select_plays
from outputs.sanity import SanityReport, benchmarks_from_logs, check_slate
from outputs.summarize import GameSummary, PlayerSummary, StatSummary
from projections.build import GameProjection, PlayerProjection
from projections.minutes import MinutesProjection
from projections.rates import RateVector


def _stat(p50: float, mean: float | None = None) -> StatSummary:
    mid = p50 if mean is None else mean
    return StatSummary(mean=mid, p10=p50 - 4, p25=p50 - 2, p50=p50, p75=p50 + 2, p90=p50 + 4)


def _player(pid: int, name: str, team: str, opp: str, **stats) -> PlayerSummary:
    base = {key: _stat(0.5) for key in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "min", "pra", "pr", "pa", "ra")}
    base["min"] = _stat(stats.pop("min", 30))
    for key, value in stats.items():
        base[key] = value if isinstance(value, StatSummary) else _stat(value)
    return PlayerSummary(
        player_id=pid,
        player_name=name,
        team_abbr=team,
        opponent_abbr=opp,
        home_away="H",
        stats=base,
        thresholds={},
    )


def _summary(players) -> GameSummary:
    score = _stat(110)
    return GameSummary(
        season="2026-27",
        game_id="0022600035",
        game_date=date(2026, 11, 13),
        home_abbr="ORL",
        away_abbr="MIL",
        runs=100,
        seed=1,
        simulated_at=date(2026, 11, 13),
        home_win_prob=0.6,
        overtime_prob=0.05,
        home_pts=score,
        away_pts=score,
        margin=_stat(4),
        total=_stat(220),
        players=players,
    )


def test_rebound_spike_without_an_absence_is_quarantined():
    player = _player(1, "Wendell Carter Jr.", "ORL", "MIL", reb=20, pts=12, ast=3)
    logs = []
    for day in range(1, 11):
        logs.append(
            {
                "player_id": 1,
                "season": "2026-27",
                "game_date": date(2026, 11, day),
                "minutes": 32,
                "pts": 12,
                "reb": 9.7,
                "ast": 2,
                "fg3m": 0,
                "stl": 1,
                "blk": 1,
            }
        )
    report = check_slate(
        [_summary([player])],
        benchmarks=benchmarks_from_logs(logs),
        injuries=[],
        game_date=date(2026, 11, 13),
    )
    reb = [flag for flag in report.flags if flag.stat == "reb"]
    assert reb and reb[0].quarantined
    assert 1 in report.quarantined_ids


def test_live_pick_record_still_scores_a_stat():
    rows = []
    for stat, hit, n, claimed in (("ast", True, 40, 0.60), ("reb", False, 40, 0.55), ("pts", True, 10, 0.50)):
        for i in range(n):
            rows.append(
                {
                    "row_kind": "pick",
                    "pick_stat": stat,
                    "actual_pick_hit": hit if i < int(n * (0.70 if stat == "ast" else 0.40)) else False,
                    "pick_confidence": claimed,
                }
            )
    qualified = calibrated_stats(rows)
    assert "ast" in qualified
    assert "reb" not in qualified
    assert "pts" not in qualified


def test_assist_agreement_is_a_top_play_and_a_point_under_is_not():
    player = _player(7, "Draymond Green", "GSW", "SAS", ast=7, pts=8, reb=6, min=28)
    summary = _summary([player])
    summary.home_abbr = "SAS"
    summary.away_abbr = "GSW"
    player.team_abbr = "GSW"
    logs = []
    for day in range(1, 12):
        logs.append(
            {
                "player_id": 7,
                "season": "2026-27",
                "game_date": date(2026, 10, day),
                "minutes": 30,
                "pts": 8,
                "reb": 6,
                "ast": 7.5,
                "fg3m": 1,
                "stl": 1,
                "blk": 1,
            }
        )
    history = [
        {
            "row_kind": "pick",
            "pick_stat": "ast",
            "actual_pick_hit": True,
            "pick_confidence": 0.60,
        }
        for _ in range(35)
    ]
    props = [
        {
            "away": "GSW",
            "home": "SAS",
            "players": [
                {
                    "player": "Draymond Green",
                    "market": "ast",
                    "point": 5.5,
                    "over": -110,
                    "under": -110,
                }
            ],
        }
    ]
    projection = GameProjection(
        season="2026-27",
        game_id=summary.game_id,
        game_date=summary.game_date,
        home_team_id=1,
        away_team_id=2,
        home_abbr="SAS",
        away_abbr="GSW",
        home_possessions=100,
        away_possessions=100,
        players=[
            PlayerProjection(
                player_id=7,
                player_name="Draymond Green",
                team_id=2,
                team_abbr="GSW",
                opponent_team_id=1,
                opponent_abbr="SAS",
                home_away="A",
                position="PF",
                started=True,
                rates=RateVector(usage=0.18),
                minutes=MinutesProjection(
                    mean=28, sd=4, min_minutes=0, max_minutes=40, out=False
                ),
                expected_team_possessions=100,
                rest_days=1,
                status="Active",
            )
        ],
    )
    from outputs.sanity import SanityReport

    card = select_plays(
        [summary],
        [projection],
        props=props,
        benchmarks=benchmarks_from_logs(logs),
        logs=logs,
        season="2026-27",
        history_rows=history,
        sanity=SanityReport(),
        questionable_ids=set(),
        calibration=_flat_table(),
    )
    assert card.tops
    assert card.tops[0].stat == "ast"
    assert card.tops[0].side == "over"
    assert close_line_value("over", 5.5, 6.5) == 1.0
    assert close_line_value("under", 5.5, 4.5) == 1.0


def _flat_table(**quality: str) -> CalibrationTable:
    cells = {}
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "pra"):
        for tier in ("top", "starter", "bench"):
            label = quality.get(f"{stat}:{tier}", "strong")
            cells[(stat, tier)] = CalibrationCell(stat, tier, (0.02, 0.98), (0.02, 0.98), label, 300, 0.0, 300)
    return CalibrationTable(cells=cells, source="test")


def test_weak_cell_needs_a_bigger_edge_and_star_points_stay_off():
    from outputs.calibration import CalibrationCell, CalibrationTable

    cells = {}
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "pra"):
        for tier in ("top", "starter", "bench"):
            cells[(stat, tier)] = CalibrationCell(stat, tier, (0.02, 0.98), (0.57, 0.57), "weak", 100, 0.05, 100)
    cells[("ast", "top")] = CalibrationCell("ast", "top", (0.02, 0.98), (0.57, 0.57), "strong", 300, 0.0, 300)
    cells[("pts", "top")] = CalibrationCell("pts", "top", (0.02, 0.98), (0.62, 0.62), "weak", 100, 0.08, 100)
    table = CalibrationTable(cells=cells, source="test")
    player = _player(7, "Draymond Green", "GSW", "SAS", ast=7, pts=20, reb=6, min=28)
    summary = _summary([player])
    summary.home_abbr = "SAS"
    summary.away_abbr = "GSW"
    logs = [
        {
            "player_id": 7,
            "season": "2026-27",
            "game_date": date(2026, 10, day),
            "minutes": 30,
            "pts": 20,
            "reb": 6,
            "ast": 7.5,
            "fg3m": 1,
            "stl": 1,
            "blk": 1,
        }
        for day in range(1, 12)
    ]
    props = [
        {
            "away": "GSW",
            "home": "SAS",
            "players": [
                {"player": "Draymond Green", "market": "ast", "point": 5.5, "over": -110, "under": -110},
                {"player": "Draymond Green", "market": "pts", "point": 16.5, "over": -110, "under": -110},
            ],
        }
    ]
    projection = GameProjection(
        season="2026-27",
        game_id=summary.game_id,
        game_date=summary.game_date,
        home_team_id=1,
        away_team_id=2,
        home_abbr="SAS",
        away_abbr="GSW",
        home_possessions=100,
        away_possessions=100,
        players=[
            PlayerProjection(
                player_id=7,
                player_name="Draymond Green",
                team_id=2,
                team_abbr="GSW",
                opponent_team_id=1,
                opponent_abbr="SAS",
                home_away="A",
                position="PF",
                started=True,
                rates=RateVector(usage=0.28),
                minutes=MinutesProjection(mean=28, sd=4, min_minutes=0, max_minutes=40, out=False),
                expected_team_possessions=100,
                rest_days=1,
                status="Active",
            )
        ],
    )
    card = select_plays(
        [summary],
        [projection],
        props=props,
        benchmarks=benchmarks_from_logs(logs),
        logs=logs,
        season="2026-27",
        history_rows=[],
        sanity=SanityReport(),
        questionable_ids=set(),
        calibration=table,
    )
    # Calibrated assist probability is 57% against a 50% market: 7 points.
    # Strong cell clears 5. The same 7 points on a weak cell would not.
    assert [row.stat for row in card.tops] == ["ast"]
    assert card.tops[0].our_p == 0.57
    point_rows = [row for row in card.leans + card.avoids + card.tops if row.stat == "pts"]
    assert point_rows
    assert "under-projection" in point_rows[0].failed


def test_benchmark_last10_uses_the_recent_games():
    logs = [
        {"player_id": 3, "game_date": date(2026, 11, day), "minutes": 20, "pts": day, "reb": 1, "ast": 1, "fg3m": 0, "stl": 0, "blk": 0}
        for day in range(1, 15)
    ]
    bench = benchmarks_from_logs(logs)[3]["pts"]
    assert bench.n == 10
    assert bench.last10 == sum(range(5, 15)) / 10
