import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from core.security import (
    get_current_user,
    require_coordinator,
    require_officer,
)
from database import get_db
from models.user import User
from schemas.officer_location import (
    ArrivalCheckRead,
    LocationListQuery,
    LocationPurgeResult,
    OfficerLocationCreate,
    OfficerLocationPage,
    OfficerLocationRead,
)
from services.officer_location import OfficerLocationService

router = APIRouter(tags=["Officer Locations"])


@router.post(
    "",
    response_model=OfficerLocationRead,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Same fix was already stored (safe retry)"}},
)
def record_location(
    data: OfficerLocationCreate,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
):
    location, created = OfficerLocationService(db).record_location(data, current_user)
    if not created:
        response.status_code = status.HTTP_200_OK
    return location


@router.get("/me", response_model=OfficerLocationPage)
def list_my_locations(
    query: Annotated[LocationListQuery, Query()],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
):
    return OfficerLocationService(db).list_my_locations(current_user, query)


@router.get("", response_model=OfficerLocationPage)
def list_locations(
    query: Annotated[LocationListQuery, Query()],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return OfficerLocationService(db).list_locations(query)


@router.get("/latest", response_model=list[OfficerLocationRead])
def latest_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return OfficerLocationService(db).latest_locations()


@router.get("/arrival-check/{alert_id}", response_model=ArrivalCheckRead)
def check_arrival(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OfficerLocationService(db).check_arrival(alert_id, current_user)


@router.post("/retention/purge", response_model=LocationPurgeResult)
def purge_expired_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return OfficerLocationService(db).purge_expired_locations(current_user)


@router.get("/{location_id}", response_model=OfficerLocationRead)
def get_location(
    location_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OfficerLocationService(db).get_location(location_id, current_user)
