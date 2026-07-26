"""Location endpoints, over HTTP against a real database."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def _add(client, name, lat, lon):
    return await client.post(
        "/locations", json={"name": name, "latitude": lat, "longitude": lon}
    )


async def test_a_new_location_is_created(api_client):
    response = await _add(api_client, "Ankara", 39.93, 32.85)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Ankara"
    assert body["id"] > 0
    assert body["is_active"] is True


async def test_the_list_returns_created_locations_sorted(api_client):
    await _add(api_client, "Izmir", 38.42, 27.14)
    await _add(api_client, "Ankara", 39.93, 32.85)
    response = await api_client.get("/locations")
    assert response.status_code == 200
    names = [loc["name"] for loc in response.json()]
    assert names == ["Ankara", "Izmir"]  # alphabetical


async def test_fetching_one_location_by_id(api_client):
    created = (await _add(api_client, "Bursa", 40.19, 29.06)).json()
    response = await api_client.get(f"/locations/{created['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "Bursa"


async def test_a_missing_location_is_404(api_client):
    response = await api_client.get("/locations/99999")
    assert response.status_code == 404


async def test_duplicate_coordinates_are_rejected_with_409(api_client):
    await _add(api_client, "First", 40.0, 30.0)
    response = await _add(api_client, "Second", 40.0, 30.0)
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", 200),
        ("latitude", -200),
        ("longitude", 999),
        ("name", ""),
    ],
)
async def test_invalid_input_is_rejected_before_the_database(api_client, field, value):
    """Pydantic stops bad input at the door with a 422, so no invalid row
    ever reaches the database."""
    body = {"name": "Valid", "latitude": 40.0, "longitude": 30.0}
    body[field] = value
    response = await api_client.post("/locations", json=body)
    assert response.status_code == 422


async def test_deactivating_a_location_hides_it_from_the_active_list(api_client):
    created = (await _add(api_client, "Temporary", 41.0, 28.0)).json()

    response = await api_client.delete(f"/locations/{created['id']}")
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    # Gone from the default (active-only) list...
    active = await api_client.get("/locations")
    assert created["id"] not in [loc["id"] for loc in active.json()]

    # ...but still there, and still fetchable, when asked for all.
    everything = await api_client.get("/locations?active_only=false")
    assert created["id"] in [loc["id"] for loc in everything.json()]
