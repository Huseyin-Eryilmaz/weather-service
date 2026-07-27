"""The accuracy mathematics, checked against hand-computable answers."""

import math

import pytest

from weather.core.metrics import (
    ErrorStats,
    absolute_error,
    horizon_hours,
    signed_error,
    summarise,
)


def test_a_perfect_forecast_has_zero_error():
    stats = summarise([(20.0, 20.0), (15.0, 15.0)])
    assert stats.mae == 0.0
    assert stats.rmse == 0.0
    assert stats.bias == 0.0


def test_mae_is_the_average_absolute_miss():
    # misses: 2, 4 -> mean 3
    stats = summarise([(22.0, 20.0), (16.0, 20.0)])
    assert stats.mae == 3.0


def test_rmse_punishes_large_errors_more_than_mae():
    """One big miss and several small ones: RMSE pulls above MAE."""
    pairs = [(20.0, 20.0), (20.0, 20.0), (30.0, 20.0)]  # errors 0,0,10
    stats = summarise(pairs)
    assert stats.mae == pytest.approx(10 / 3)
    assert stats.rmse == pytest.approx(math.sqrt(100 / 3))
    assert stats.rmse > stats.mae


def test_rmse_equals_mae_when_all_errors_are_equal():
    """With uniform errors the two measures coincide — the gap between
    them only opens when errors are uneven."""
    stats = summarise([(22.0, 20.0), (18.0, 20.0), (22.0, 20.0)])  # all |2|
    assert stats.mae == pytest.approx(2.0)
    assert stats.rmse == pytest.approx(2.0)


def test_bias_reveals_a_systematic_direction():
    """Always 2 too warm: MAE and bias agree in magnitude, bias keeps the
    sign that says which way."""
    stats = summarise([(22.0, 20.0), (17.0, 15.0), (12.0, 10.0)])
    assert stats.bias == pytest.approx(2.0)


def test_bias_cancels_when_errors_are_symmetric():
    """Two too warm and two too cold: no net bias, but real inaccuracy —
    which is exactly the case MAE catches and bias cannot."""
    stats = summarise([(22.0, 20.0), (18.0, 20.0)])
    assert stats.bias == pytest.approx(0.0)
    assert stats.mae == pytest.approx(2.0)


def test_no_pairs_summarise_to_none():
    """Empty input is 'nothing to compare', not a division by zero."""
    assert summarise([]) is None


def test_absolute_and_signed_error_differ_only_in_sign():
    assert absolute_error(18.0, 20.0) == 2.0
    assert signed_error(18.0, 20.0) == -2.0  # under-forecast is negative


def test_horizon_is_whole_hours_between_issue_and_target():
    # issued at t, target 6 hours later
    assert horizon_hours(0.0, 6 * 3600) == 6


def test_a_forecast_issued_after_its_target_clamps_to_zero():
    """A data glitch must not yield a negative horizon."""
    assert horizon_hours(10 * 3600, 6 * 3600) == 0


def test_stats_round_for_stable_output():
    stats = ErrorStats(count=3, mae=1.23456, rmse=2.34567, bias=-0.98765)
    rounded = stats.rounded(2)
    assert rounded.mae == 1.23
    assert rounded.rmse == 2.35
    assert rounded.bias == -0.99
    assert rounded.count == 3
