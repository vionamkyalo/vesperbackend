import uuid
from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from core.security import require_any_user, require_officer
from database import get_db
from models.user import User
from schemas.inspection import InspectionCreate, InspectionRead
from services.inspection import inspection_service

router = APIRouter(prefix="/inspections", tags=["inspections"])


@router.post("", response_model=InspectionRead, status_code=status.HTTP_201_CREATED)
def create_inspection(
    body: InspectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
):
    return inspection_service.create_inspection(db, current_user, body)


@router.get("", response_model=List[InspectionRead])
def list_inspections(
    alert_id: uuid.UUID | None = None,
    zone_id: uuid.UUID | None = None,
    officer_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_user),
):
    return inspection_service.list_inspections(
        db, current_user, alert_id, zone_id, officer_id, limit, offset
    )


@router.get("/{inspection_id}", response_model=InspectionRead)
def get_inspection(
    inspection_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_user),
):
    return inspection_service.get_inspection(db, current_user, inspection_id)
