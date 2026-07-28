"""The four tables, as Python classes.

  locations          the places we track
  observations       what the weather actually was
  forecasts          what the weather was predicted to be
  forecast_accuracy  how far the prediction turned out to be off

The one modelling decision worth pausing on lives in `forecasts`: a
forecast has *two* timestamps. `issued_at` is when the prediction was
made; `target_time` is the hour it predicts. Tomorrow's weather is
predicted today, and it was also predicted yesterday, and those two
predictions can disagree. Collapsing them into one column would throw
away exactly the information the accuracy analysis is built on — "how
does a forecast made 6 hours ahead compare with one made 3 days ahead?"

Every measurement table carries a unique constraint over the columns
that identify a single reading. That constraint is what makes writes
idempotent: fetching the same hour twice tries to insert the same key
twice, and the database refuses the duplicate instead of doubling it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from weather.db.base import Base


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    country: Mapped[str] = mapped_column(String(2), default="TR")
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    observations: Mapped[list[Observation]] = relationship(
        back_populates="location", cascade="all, delete-orphan"
    )
    forecasts: Mapped[list[Forecast]] = relationship(
        back_populates="location", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # No two active rows for the same coordinates. A city added twice
        # by slightly different names should still be one location.
        UniqueConstraint("latitude", "longitude", name="uq_location_coords"),
    )


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    temperature_c: Mapped[float | None] = mapped_column(Float)
    humidity_pct: Mapped[float | None] = mapped_column(Float)
    wind_speed_kmh: Mapped[float | None] = mapped_column(Float)
    precipitation_mm: Mapped[float | None] = mapped_column(Float)
    # WMO weather code (0 = clear, 1-3 = increasing cloud, 45 = fog,
    # 61 = rain, 95 = thunderstorm, ...). Stored as the raw number; the
    # frontend maps it to a label and icon. Nullable, since older rows
    # predate it and the API does not always supply it.
    weather_code: Mapped[int | None] = mapped_column(Integer)

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    location: Mapped[Location] = relationship(back_populates="observations")

    __table_args__ = (
        UniqueConstraint(
            "location_id", "observed_at", name="uq_observation_location_time"
        ),
        # The common query is "this location, over this time range", so
        # the index leads with location and orders by time.
        Index("ix_observation_location_time", "location_id", "observed_at"),
    )


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    temperature_c: Mapped[float | None] = mapped_column(Float)
    humidity_pct: Mapped[float | None] = mapped_column(Float)
    wind_speed_kmh: Mapped[float | None] = mapped_column(Float)
    precipitation_mm: Mapped[float | None] = mapped_column(Float)
    # WMO weather code; see Observation.weather_code.
    weather_code: Mapped[int | None] = mapped_column(Integer)

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    location: Mapped[Location] = relationship(back_populates="forecasts")

    __table_args__ = (
        # One prediction per (place, when-made, what-predicted). Re-fetching
        # the same forecast run updates nothing new.
        UniqueConstraint(
            "location_id",
            "issued_at",
            "target_time",
            name="uq_forecast_location_issue_target",
        ),
        Index("ix_forecast_location_target", "location_id", "target_time"),
    )


class ForecastAccuracy(Base):
    __tablename__ = "forecast_accuracy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    target_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    metric: Mapped[str] = mapped_column(String(32), nullable=False)

    # How many hours before target_time the forecast was issued. This is
    # the axis the accuracy analysis pivots on: error almost always grows
    # with the horizon.
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False)

    forecast_value: Mapped[float] = mapped_column(Float, nullable=False)
    observed_value: Mapped[float] = mapped_column(Float, nullable=False)
    absolute_error: Mapped[float] = mapped_column(Float, nullable=False)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "location_id",
            "target_time",
            "metric",
            "horizon_hours",
            name="uq_accuracy_key",
        ),
        Index("ix_accuracy_location_metric", "location_id", "metric"),
    )
