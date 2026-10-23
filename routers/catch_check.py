import uuid
from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from core.security import require_any_user, require_officer
from database import get_db
from models.user import User
from schemas.catch_check import CatchCheckCreate, CatchCheckRead
from services.catch_check import catch_check_service

router = APIRouter(prefix="/catch-checks", tags=["catch checks"])


@router.post(
    "",
    response_model=CatchCheckRead,
    status_code=status.HTTP_201_CREATED,
)
def create_catch_check(
    body: CatchCheckCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
):
    return catch_check_service.create_catch_check(db, current_user, body)


@router.get("", response_model=List[CatchCheckRead])
def list_catch_checks(
    inspection_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_user),
):
    return catch_check_service.list_catch_checks(
        db, current_user, inspection_id, limit, offset
    )


@router.get("/{catch_id}", response_model=CatchCheckRead)
def get_catch_check(
    catch_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_user),
):
    return catch_check_service.get_catch_check(db, current_user, catch_id)
