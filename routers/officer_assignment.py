import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from core.security import (
    get_current_user,
    require_coordinator,
    require_officer,
)
from database import get_db
from models.user import User
from schemas.officer_assignment import (
    ArrivalCheckRead,
    AssignmentListQuery,
    AssignmentPurgeResult,
    OfficerAssignmentCreate,
    OfficerAssignmentPage,
    OfficerAssignmentRead,
)
from services.officer_assignment import OfficerAssignmentService

router = APIRouter(tags=["officer assignment"])


@router.post(
    "",
    response_model=OfficerAssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
def record_location(
    data: OfficerAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
):
    return OfficerAssignmentService(db).record_location(data, current_user)


@router.get("/me", response_model=OfficerAssignmentPage)
def list_my_locations(
    query: Annotated[AssignmentListQuery, Query()],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
):
    return OfficerAssignmentService(db).list_my_locations(current_user, query)


@router.get("", response_model=OfficerAssignmentPage)
def list_locations(
    query: Annotated[AssignmentListQuery, Query()],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return OfficerAssignmentService(db).list_locations(query)


@router.get("/latest", response_model=list[OfficerAssignmentRead])
def latest_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return OfficerAssignmentService(db).latest_locations()


@router.get("/arrival-check/{alert_id}", response_model=ArrivalCheckRead)
def check_arrival(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OfficerAssignmentService(db).check_arrival(alert_id, current_user)


@router.post("/retention/purge", response_model=AssignmentPurgeResult)
def purge_expired_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return OfficerAssignmentService(db).purge_expired_locations(current_user)


@router.get("/{location_id}", response_model=OfficerAssignmentRead)
def get_location(
    location_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OfficerAssignmentService(db).get_location(location_id, current_user)
