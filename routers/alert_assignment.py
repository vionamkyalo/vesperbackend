import uuid
from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from core.security import require_any_user, require_coordinator, require_officer
from database import get_db
from models.alert_assignment import AssignmentStatus
from models.user import User
from schemas.alert_assignment import AlertAssignmentCreate, AlertAssignmentRead
from services.alert_assignment import alert_assignment_service

router = APIRouter(prefix="/alert-assignments", tags=["alert assignments"])


@router.post(
    "", response_model=AlertAssignmentRead, status_code=status.HTTP_201_CREATED
)
def assign_alert(
    body: AlertAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return alert_assignment_service.assign_alert(db, current_user, body)


@router.get("", response_model=List[AlertAssignmentRead])
def list_assignments(
    alert_id: uuid.UUID | None = None,
    officer_id: uuid.UUID | None = None,
    assignment_status: AssignmentStatus | None = Query(default=None, alias="status"),
    active_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_user),
):
    return alert_assignment_service.list_assignments(
        db,
        current_user,
        alert_id,
        officer_id,
        assignment_status,
        active_only,
        limit,
        offset,
    )


@router.get("/{assignment_id}", response_model=AlertAssignmentRead)
def get_assignment(
    assignment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_user),
):
    return alert_assignment_service.get_assignment(db, current_user, assignment_id)


@router.post("/{assignment_id}/acknowledge", response_model=AlertAssignmentRead)
def acknowledge(
    assignment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
):
    return alert_assignment_service.acknowledge(db, current_user, assignment_id)


@router.post("/{assignment_id}/fail", response_model=AlertAssignmentRead)
def mark_failed(
    assignment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return alert_assignment_service.mark_failed(db, current_user, assignment_id)
