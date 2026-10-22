"""Stint extraction and margin-conditioned rotation helpers (Step F)."""

from __future__ import annotations

from datetime import date

from ingest.stints import clock_to_seconds, margin_bucket
from projections.rotations import (
    RotationModel,
    expected_abs_margin_from_strength,
    redistribute_minutes_for_absences,
)


def test_clock_to_seconds():
    assert abs(clock_to_seconds("PT11M27.00S") - (11 * 60 + 27)) < 0.01
    assert clock_to_seconds("PT00M00.00S") == 0.0


def test_margin_bucket():
    assert margin_bucket(3) == "close"
    assert margin_bucket(10) == "moderate"
    assert margin_bucket(-20) == "blowout"


def test_adjust_means_close_shortens_rotation():
    model = RotationModel(step_f=True)
    means = [34.0, 32.0, 30.0, 28.0, 26.0, 20.0, 16.0, 12.0, 8.0, 4.0, 0.0]
    ranks = list(range(11))
    close = model.adjust_means(means, ranks, expected_abs_margin=3.0, config={"minutes": {}})
    blow = model.adjust_means(means, ranks, expected_abs_margin=20.0, config={"minutes": {}})
    # Stars get relatively more in close games than in blowouts.
    assert close[0] / close[7] > blow[0] / blow[7]
    # Bench (rank 7+) gets more relative share in blowouts.
    assert blow[7] > close[7]


def test_expected_abs_margin_from_strength():
    wide = expected_abs_margin_from_strength(118, 108, 108, 118)
    tight = expected_abs_margin_from_strength(112, 112, 111, 111)
    assert wide > tight


def test_blowout_period_weights_bench_earlier():
    model = RotationModel(step_f=True)
    starter_q4_blow = model.period_weights(1, period=4, margin_bucket_name="blowout")
    bench_q4_blow = model.period_weights(7, period=4, margin_bucket_name="blowout")
    starter_q4_close = model.period_weights(1, period=4, margin_bucket_name="close")
    bench_q4_close = model.period_weights(7, period=4, margin_bucket_name="close")
    assert bench_q4_blow > starter_q4_blow
    assert starter_q4_close > bench_q4_close


def test_redistribute_minutes_prefers_historical_replacement():
    model = RotationModel(step_f=True)
    model.replacements[(1, 100)] = {200: 8.0, 300: 2.0}
    player_ids = [100, 200, 300, 400]
    means = [32.0, 18.0, 14.0, 10.0]
    out = redistribute_minutes_for_absences(
        player_ids,
        means,
        team_id=1,
        out_ids={100},
        caps=None,
        model=model,
        config={"minutes": {"replacement_share": 1.0}},
    )
    assert out[0] == 0.0
    # Player 200 should receive most of the 32 freed minutes.
    assert out[1] > out[2] > means[2]
    assert abs(sum(out) - sum(means)) < 1e-6


def test_redistribute_respects_minutes_cap():
    model = RotationModel(step_f=True)
    model.replacements[(1, 100)] = {200: 1.0}
    out = redistribute_minutes_for_absences(
        [100, 200],
        [30.0, 20.0],
        team_id=1,
        out_ids={100},
        caps={200: 28.0},
        model=model,
        config={"minutes": {"replacement_share": 1.0}},
    )
    assert out[0] == 0.0
    assert out[1] <= 28.0 + 1e-9


def test_redistribute_noop_when_step_f_off():
    model = RotationModel(step_f=False)
    model.replacements[(1, 100)] = {200: 1.0}
    means = [30.0, 20.0]
    out = redistribute_minutes_for_absences(
        [100, 200],
        means,
        team_id=1,
        out_ids={100},
        caps=None,
        model=model,
        config={"minutes": {"replacement_share": 1.0}},
    )
    assert out == means


def test_closing_share_boost_in_adjust_means():
    model = RotationModel(step_f=True)
    model.closing_sec[(9, 1)] = 100.0
    model.closing_sec[(9, 2)] = 10.0
    means = [30.0, 28.0, 20.0]
    ranks = [0, 1, 5]
    boosted = model.adjust_means(
        means,
        ranks,
        expected_abs_margin=2.0,
        config={"minutes": {}},
        player_ids=[1, 2, 3],
        team_id=9,
    )
    plain = model.adjust_means(
        means,
        ranks,
        expected_abs_margin=2.0,
        config={"minutes": {}},
    )
    # Closer (player 1) should get a larger relative bump than without closing info.
    assert boosted[0] / plain[0] > boosted[2] / plain[2]
