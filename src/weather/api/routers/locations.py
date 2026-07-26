"""Location endpoints: list, fetch, add, deactivate.

A location is the one thing in this API a caller can create, so this is
where request validation earns its keep. By the time a handler runs,
Pydantic has already guaranteed the coordinates are in range and the name
is non-empty; the handler only has to worry about duplicates, which the
database — not the schema — is the authority on.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from weather.api.dependencies import get_db_session
from weather.api.schemas import LocationCreate, LocationOut
from weather.db import queries

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=list[LocationOut])
async def list_locations(
    active_only: bool = True,
    session: AsyncSession = Depends(get_db_session),
) -> list[LocationOut]:
    locations = await queries.list_locations(session, active_only=active_only)
    return [LocationOut.model_validate(loc) for loc in locations]


@router.get("/{location_id}", response_model=LocationOut)
async def get_location(
    location_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> LocationOut:
    location = await queries.get_location(session, location_id)
    if location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="location not found")
    return LocationOut.model_validate(location)


@router.post("", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
async def create_location(
    body: LocationCreate,
    session: AsyncSession = Depends(get_db_session),
) -> LocationOut:
    """Adds a location, refusing coordinates that already exist.

    The uniqueness rule lives on the table, but checking here first lets
    the API answer with a clear 409 instead of surfacing a raw database
    constraint error.
    """
    existing = await queries.find_location_by_coords(
        session, body.latitude, body.longitude
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"a location already exists at those coordinates: {existing.name}",
        )
    location = await queries.create_location(
        session,
        name=body.name,
        latitude=body.latitude,
        longitude=body.longitude,
        country=body.country,
    )
    return LocationOut.model_validate(location)


@router.delete("/{location_id}", response_model=LocationOut)
async def deactivate_location(
    location_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> LocationOut:
    """Deactivates a location. Its history stays; collection stops."""
    location = await queries.deactivate_location(session, location_id)
    if location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="location not found")
    return LocationOut.model_validate(location)
