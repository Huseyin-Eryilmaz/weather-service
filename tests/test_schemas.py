"""Response parsing and its guard rails."""

import pytest
from pydantic import ValidationError

from weather.clients.schemas import ForecastResponse, HourlyBlock


def _response(**hourly):
    return {"latitude": 39.9, "longitude": 32.8, "hourly": hourly}


def test_parallel_arrays_become_one_record_per_hour():
    response = ForecastResponse.model_validate(
        _response(
            time=["2026-07-25T00:00", "2026-07-25T01:00"],
            temperature_2m=[20.0, 19.0],
            relative_humidity_2m=[50, 55],
            wind_speed_10m=[10.0, 11.0],
            precipitation=[0.0, 0.5],
        )
    )
    records = response.to_records()
    assert len(records) == 2
    assert records[1].temperature_c == 19.0
    assert records[1].precipitation_mm == 0.5


def test_a_null_reading_is_preserved_as_none():
    """Open-Meteo sends null for a missing hour; it must stay None, not
    become zero, which would corrupt any average."""
    response = ForecastResponse.model_validate(
        _response(
            time=["2026-07-25T00:00"],
            temperature_2m=[None],
        )
    )
    assert response.to_records()[0].temperature_c is None


def test_misaligned_arrays_are_rejected():
    """A variable shorter than `time` would silently pair readings with
    the wrong hours; the response is refused instead."""
    with pytest.raises(ValidationError):
        HourlyBlock(
            time=["2026-07-25T00:00", "2026-07-25T01:00"],
            temperature_2m=[20.0],  # one value, two timestamps
        )


def test_missing_variables_default_to_empty():
    """A response that omits a variable entirely is valid; those readings
    are simply None."""
    response = ForecastResponse.model_validate(
        _response(time=["2026-07-25T00:00"], temperature_2m=[20.0])
    )
    record = response.to_records()[0]
    assert record.temperature_c == 20.0
    assert record.humidity_pct is None
