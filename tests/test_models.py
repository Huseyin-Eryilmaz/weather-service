"""Model-level checks that need no database: table names, the shape of
the schema, and the relationships that hold it together."""

from weather.db.models import Forecast, ForecastAccuracy, Location, Observation


def test_table_names_are_stable():
    """Downstream tools and migrations key off these; a rename is a
    breaking change worth noticing in a diff."""
    assert Location.__tablename__ == "locations"
    assert Observation.__tablename__ == "observations"
    assert Forecast.__tablename__ == "forecasts"
    assert ForecastAccuracy.__tablename__ == "forecast_accuracy"


def test_a_forecast_carries_both_timestamps():
    """The heart of the accuracy design: when it was made, and what it
    predicts. Losing either column would make the analysis impossible."""
    columns = set(Forecast.__table__.columns.keys())
    assert "issued_at" in columns
    assert "target_time" in columns


def test_measurement_tables_share_the_same_metrics():
    """Forecasts and observations must record the same fields, or there
    would be nothing to compare."""
    metrics = {"temperature_c", "humidity_pct", "wind_speed_kmh", "precipitation_mm"}
    assert metrics <= set(Observation.__table__.columns.keys())
    assert metrics <= set(Forecast.__table__.columns.keys())


def test_observations_are_uniquely_keyed_by_location_and_time():
    constraints = {c.name for c in Observation.__table__.constraints if c.name}
    assert "uq_observation_location_time" in constraints


def test_forecasts_are_uniquely_keyed_by_location_issue_and_target():
    constraints = {c.name for c in Forecast.__table__.constraints if c.name}
    assert "uq_forecast_location_issue_target" in constraints


def test_accuracy_records_a_horizon():
    """Error is analysed per forecast horizon, so the column must exist."""
    assert "horizon_hours" in ForecastAccuracy.__table__.columns
