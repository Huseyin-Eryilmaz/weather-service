"""The shapes the API speaks: what it accepts, what it returns.

These are separate from the database models on purpose. A model is how a
row is stored; a schema is part of the public contract with whoever calls
the API. Keeping them apart means the storage can change without breaking
callers, and — just as important — the API never leaks a column it did
not mean to expose simply because someone added it to a table.

Request schemas also validate input at the door. A latitude of 200 or an
empty name is rejected by Pydantic before any handler runs, with a 422
that says exactly which field was wrong, so no bad row ever reaches the
database.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LocationCreate(BaseModel):
    """The body for adding a location. Coordinates are range-checked."""

    name: str = Field(min_length=1, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    country: str = Field(default="TR", min_length=2, max_length=2)


class LocationOut(BaseModel):
    """A location as returned to callers.

    `from_attributes=True` lets FastAPI build this straight from a
    SQLAlchemy row object, reading it attribute by attribute — no manual
    field copying, and no chance of the two drifting out of sync.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    latitude: float
    longitude: float
    country: str
    is_active: bool
    created_at: datetime


class WeatherPoint(BaseModel):
    """One hour of weather, forecast or observed."""

    model_config = ConfigDict(from_attributes=True)

    observed_at: datetime = Field(validation_alias="observed_at")
    temperature_c: float | None = None
    humidity_pct: float | None = None
    wind_speed_kmh: float | None = None
    precipitation_mm: float | None = None


class Page(BaseModel):
    """A page of results, plus the count needed to walk the rest.

    Returning a bare list would leave a caller unable to tell "that is
    everything" from "that is the first hundred of thousands". The total
    makes pagination navigable instead of guesswork.
    """

    total: int
    limit: int
    offset: int


class ObservationPage(Page):
    items: list[WeatherPoint]


class ForecastPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    issued_at: datetime
    target_time: datetime
    temperature_c: float | None = None
    humidity_pct: float | None = None
    wind_speed_kmh: float | None = None
    precipitation_mm: float | None = None


class ForecastPage(Page):
    items: list[ForecastPoint]
