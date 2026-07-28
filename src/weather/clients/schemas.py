"""What Open-Meteo sends back, described as Pydantic models.

Data crossing the boundary from an external service is *untrusted* until
proven otherwise. It might be missing a field, carry a null where a
number was expected, or have changed shape since the code was written.
Parsing it into these models at the door means one of two things happens:
either it validates and the rest of the code works with clean, typed
Python objects, or it fails loudly right here, at the boundary, with a
message that says exactly what was wrong — instead of a mysterious
`None` surfacing three layers deeper.

Open-Meteo returns weather as *parallel arrays*: an hourly block with a
`time` list and one same-length list per variable, lined up by index.
That is compact over the wire but awkward to work with, so `to_records`
zips them back into one object per hour.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, model_validator


class HourlyBlock(BaseModel):
    """The parallel arrays exactly as they arrive."""

    time: list[datetime]
    temperature_2m: list[float | None] = []
    relative_humidity_2m: list[float | None] = []
    wind_speed_10m: list[float | None] = []
    precipitation: list[float | None] = []
    weather_code: list[int | None] = []

    @model_validator(mode="after")
    def _arrays_line_up(self) -> HourlyBlock:
        """Every present series must match the length of `time`.

        If they do not, the index-based zip below would silently pair a
        timestamp with the wrong reading, or drop data off the end. Better
        to reject the whole response than to store quietly-misaligned rows.
        """
        n = len(self.time)
        for name in (
            "temperature_2m",
            "relative_humidity_2m",
            "wind_speed_10m",
            "precipitation",
            "weather_code",
        ):
            series = getattr(self, name)
            if series and len(series) != n:
                raise ValueError(f"{name} has {len(series)} values but time has {n}")
        return self


class WeatherReading(BaseModel):
    """One hour, with every variable in one place — the shape we store."""

    time: datetime
    temperature_c: float | None = None
    humidity_pct: float | None = None
    wind_speed_kmh: float | None = None
    precipitation_mm: float | None = None
    weather_code: int | None = None


class ForecastResponse(BaseModel):
    """The top-level response from the forecast and archive endpoints."""

    latitude: float
    longitude: float
    hourly: HourlyBlock

    def to_records(self) -> list[WeatherReading]:
        """Transposes the parallel arrays into one reading per hour."""
        hourly = self.hourly

        def at(series: list, index: int):
            return series[index] if index < len(series) else None

        return [
            WeatherReading(
                time=timestamp,
                temperature_c=at(hourly.temperature_2m, i),
                humidity_pct=at(hourly.relative_humidity_2m, i),
                wind_speed_kmh=at(hourly.wind_speed_10m, i),
                precipitation_mm=at(hourly.precipitation, i),
                weather_code=at(hourly.weather_code, i),
            )
            for i, timestamp in enumerate(hourly.time)
        ]
