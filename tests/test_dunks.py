"""Dunks priors nudge minutes and rates without replacing the projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from projections.dunks import (
    EpmPrior,
    _CACHE,
    _blend_epm_rates,
    _blend_minutes,
    apply_dunks_blend,
)
from projections.context import TeamStrength
from projections.minutes import MinutesProjection
from projections.rates import RateVector


@dataclass
class _Player:
    player_id: int
    player_name: str
    team_abbr: str
    rates: RateVector
    minutes: MinutesProjection
    status: str = "active"


def _minutes(mean: float, *, out: bool = False) -> MinutesProjection:
    return MinutesProjection(
        mean=0.0 if out else mean,
        sd=2.0,
        min_minutes=0.0,
        max_minutes=42.0,
        out=out,
        play_prob=0.0 if out else 1.0,
    )


def _epm(**overrides) -> EpmPrior:
    base = dict(
        team="SAS",
        mpg=30.0,
        usg=0.40,
        oepm=3.0,
        depm=4.0,
        pts_100=30.0,
        fg2a_100=12.0,
        fg2_pct=0.60,
        fg3a_100=8.0,
        fg3_pct=0.40,
        fta_100=8.0,
        ft_pct=0.90,
        orb_100=2.0,
        drb_100=8.0,
        ast_100=6.0,
        tov_100=3.0,
        stl_100=1.5,
        blk_100=2.0,
    )
    base.update(overrides)
    return EpmPrior(**base)


def _config(**ctx) -> dict:
    context = {
        "dunks_enabled": True,
        "dunks_epm_weight": 0.30,
        "dunks_box_weight": 0.25,
        "dunks_team_weight": 0.20,
    }
    context.update(ctx)
    return {"context": context, "minutes": {"play_threshold": 1.0}}


def test_epm_usage_moves_partway():
    rates = _blend_epm_rates(RateVector(usage=0.20, ft_pct=0.70), _epm(), 0.30)
    assert rates.usage == 0.26
    assert abs(rates.ft_pct - (0.70 * 0.70 + 0.30 * 0.90)) < 1e-9


def test_minutes_follow_box_more_than_epm():
    blended = _blend_minutes(_minutes(20.0), _epm(mpg=30.0), _box(minutes=32.0), 0.30, 0.25)
    # 60% model, 25% box, 15% EPM minutes.
    assert blended.mean == 24.5


def test_out_player_is_left_out(tmp_path):
    _CACHE.clear()
    _write_epm(tmp_path, _epm())
    player = _Player(1, "Star", "SAS", RateVector(usage=0.20), _minutes(28.0, out=True), status="Out")
    bench = _Player(2, "Bench", "SAS", RateVector(usage=0.10), _minutes(12.0))
    home = {1: player, 2: bench}
    away = {3: _Player(3, "Other", "BOS", RateVector(), _minutes(30.0))}
    apply_dunks_blend(
        home,
        away,
        settings=_settings(tmp_path),
        as_of=date(2026, 11, 1),
        home_poss=100.0,
        away_poss=100.0,
        home_strength=TeamStrength(114.0, 114.0),
        away_strength=TeamStrength(114.0, 114.0),
        league=TeamStrength(114.0, 114.0),
        config=_config(),
        defender_fg_factor={},
        defender_fg3_factor={},
    )
    assert home[1].minutes.out
    assert home[1].minutes.mean == 0.0
    assert home[1].rates.usage == 0.0


def test_same_day_box_is_used_and_other_days_are_not(tmp_path):
    _CACHE.clear()
    _write_epm(tmp_path, _epm(mpg=30.0), stamp="2026-10-20")
    _write_box(tmp_path, minutes=36.0, stamp="2026-10-20")
    home, away = _two_sides()
    apply_dunks_blend(
        home,
        away,
        settings=_settings(tmp_path),
        as_of=date(2026, 10, 21),
        home_poss=100.0,
        away_poss=100.0,
        home_strength=TeamStrength(114.0, 114.0),
        away_strength=TeamStrength(114.0, 114.0),
        league=TeamStrength(114.0, 114.0),
        config=_config(dunks_team_weight=0.0),
    )
    # Oct 20 EPM still applies on Oct 21. The Oct 20 box does not.
    assert home[1].minutes.mean == 0.70 * 20.0 + 0.30 * 30.0


def test_better_dunks_offense_raises_fg(tmp_path):
    _CACHE.clear()
    _write_teams(tmp_path, ortg=6.0, drtg=0.0)
    home, away = _two_sides()
    before = home[1].rates.restricted_area_fg_pct
    apply_dunks_blend(
        home,
        away,
        settings=_settings(tmp_path),
        as_of=date(2026, 11, 1),
        home_poss=100.0,
        away_poss=100.0,
        home_strength=TeamStrength(114.0, 114.0),
        away_strength=TeamStrength(114.0, 114.0),
        league=TeamStrength(114.0, 114.0),
        config=_config(dunks_epm_weight=0.0, dunks_box_weight=0.0),
    )
    assert home[1].rates.restricted_area_fg_pct > before


def test_positive_depm_tightens_defense(tmp_path):
    _CACHE.clear()
    _write_epm(tmp_path, _epm(depm=4.0))
    home, away = _two_sides()
    fg: dict[int, float] = {1: 1.0}
    fg3: dict[int, float] = {1: 1.0}
    apply_dunks_blend(
        home,
        away,
        settings=_settings(tmp_path),
        as_of=date(2026, 11, 1),
        home_poss=100.0,
        away_poss=100.0,
        home_strength=TeamStrength(114.0, 114.0),
        away_strength=TeamStrength(114.0, 114.0),
        league=TeamStrength(114.0, 114.0),
        config=_config(dunks_box_weight=0.0, dunks_team_weight=0.0),
        defender_fg_factor=fg,
        defender_fg3_factor=fg3,
    )
    assert fg[1] < 1.0
    assert fg3[1] < 1.0


def test_wrong_team_epm_is_ignored(tmp_path):
    _CACHE.clear()
    _write_epm(tmp_path, _epm(team="BOS", mpg=40.0, usg=0.40))
    home = {
        1: _Player(1, "Star", "SAS", RateVector(usage=0.25), _minutes(24.0)),
        2: _Player(2, "Bench", "SAS", RateVector(usage=0.15), _minutes(24.0)),
    }
    away = {3: _Player(3, "Other", "BOS", RateVector(usage=0.20), _minutes(24.0))}
    apply_dunks_blend(
        home,
        away,
        settings=_settings(tmp_path),
        as_of=date(2026, 11, 1),
        home_poss=100.0,
        away_poss=100.0,
        home_strength=None,
        away_strength=None,
        league=None,
        config=_config(dunks_box_weight=0.0, dunks_team_weight=0.0),
    )
    assert home[1].minutes.mean == 24.0
    assert home[1].rates.usage == pytest.approx(0.25)


def test_zero_minutes_take_epm_when_the_player_is_active(tmp_path):
    _CACHE.clear()
    _write_epm(tmp_path, _epm(mpg=24.0))
    home = {
        1: _Player(1, "Rookie", "SAS", RateVector(usage=0.10), _minutes(0.0)),
        2: _Player(2, "Out", "SAS", RateVector(usage=0.10), _minutes(0.0, out=True), status="Out"),
    }
    away = {3: _Player(3, "Other", "BOS", RateVector(usage=0.18), _minutes(24.0))}
    events = apply_dunks_blend(
        home,
        away,
        settings=_settings(tmp_path),
        as_of=date(2026, 11, 1),
        home_poss=100.0,
        away_poss=100.0,
        home_strength=TeamStrength(114.0, 114.0),
        away_strength=TeamStrength(114.0, 114.0),
        league=TeamStrength(114.0, 114.0),
        config=_config(dunks_box_weight=0.0, dunks_team_weight=0.0),
    )
    assert home[1].minutes.mean == pytest.approx(0.30 * 24.0)
    assert home[1].minutes.play_prob >= 0.85
    assert home[2].minutes.mean == 0.0
    assert [event["player_id"] for event in events] == [1]
    assert events[0]["source"] == "epm"


def test_missing_files_leave_rates_alone(tmp_path):
    _CACHE.clear()
    home, away = _two_sides()
    apply_dunks_blend(
        home,
        away,
        settings=_settings(tmp_path),
        as_of=date(2024, 11, 2),
        home_poss=100.0,
        away_poss=100.0,
        home_strength=TeamStrength(114.0, 114.0),
        away_strength=TeamStrength(114.0, 114.0),
        league=TeamStrength(114.0, 114.0),
        config=_config(),
    )
    assert home[1].minutes.mean == 20.0
    assert home[1].rates.usage == 0.20


class _Settings:
    def __init__(self, data_dir):
        self.data_dir = data_dir


def _settings(path):
    return _Settings(path)


def _box(minutes: float):
    from projections.dunks import BoxPrior

    return BoxPrior(
        team="SAS",
        minutes=minutes,
        pts=20.0,
        reb=8.0,
        ast=4.0,
        stl=1.0,
        blk=1.0,
        tov=2.0,
        oreb=2.0,
        dreb=6.0,
        fg3a=6.0,
    )


def _two_sides():
    home = {
        1: _Player(1, "Star", "SAS", RateVector(usage=0.20), _minutes(20.0)),
        2: _Player(2, "Bench", "SAS", RateVector(usage=0.12), _minutes(16.0)),
    }
    away = {3: _Player(3, "Other", "BOS", RateVector(usage=0.18), _minutes(24.0))}
    return home, away


def _write_epm(path, row: EpmPrior, stamp: str = "2026-11-01") -> None:
    table = pa.table(
        {
            "nba_id": [1],
            "team": [row.team],
            "p_mpg": [row.mpg],
            "p_usg": [row.usg],
            "oepm": [row.oepm],
            "depm": [row.depm],
            "p_pts_100": [row.pts_100],
            "p_fg2a_100": [row.fg2a_100],
            "p_fg2pct": [row.fg2_pct],
            "p_fg3a_100": [row.fg3a_100],
            "p_fg3pct": [row.fg3_pct],
            "p_fta_100": [row.fta_100],
            "p_ftpct": [row.ft_pct],
            "p_orb_100": [row.orb_100],
            "p_drb_100": [row.drb_100],
            "p_ast_100": [row.ast_100],
            "p_tov_100": [row.tov_100],
            "p_stl_100": [row.stl_100],
            "p_blk_100": [row.blk_100],
        }
    )
    dest = path / "external" / "dunks"
    dest.mkdir(parents=True)
    pq.write_table(table, dest / f"epm_{stamp}.parquet")


def _write_box(path, minutes: float, stamp: str) -> None:
    dest = path / "external" / "dunks"
    dest.mkdir(parents=True, exist_ok=True)
    table = pa.table(
        {
            "player_id": [1],
            "team_abbr": ["SAS"],
            "minutes": [minutes],
            "pts": [20.0],
            "reb": [8.0],
            "ast": [4.0],
            "stl": [1.0],
            "blk": [1.0],
            "tov": [2.0],
            "oreb": [2.0],
            "dreb": [6.0],
            "fg3a": [6.0],
        }
    )
    pq.write_table(table, dest / f"box_{stamp}.parquet")


def _write_teams(path, ortg: float, drtg: float) -> None:
    dest = path / "external" / "dunks"
    dest.mkdir(parents=True)
    table = pa.table(
        {
            "team_abbr": ["SAS", "BOS"],
            "ortg": [ortg, 0.0],
            "drtg": [drtg, 0.0],
        }
    )
    pq.write_table(table, dest / "team_ratings_2026-11-01.parquet")
