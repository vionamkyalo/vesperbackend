import uuid
from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from core.security import (
    get_current_user,
    require_any_user,
    require_coordinator,
)
from database import get_db
from models.user import User, UserRole
from schemas.user import PasswordChange, UserCreate, UserRead, UserUpdate
from services.user import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
def create_officer(
    body: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return user_service.create_officer(db, current_user, body)


@router.get("", response_model=List[UserRead])
def list_users(
    role: UserRole | None = None,
    is_active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return user_service.list_users(db, current_user, role, is_active, limit, offset)


@router.get("/me", response_model=UserRead)
def get_me(
    current_user: User = Depends(require_any_user),
):
    return user_service.get_me(current_user)


@router.patch(
    "/me/password",
    status_code=status.HTTP_200_OK,
)
def change_password(
    body: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_service.change_password(db, current_user, body)
    return {"message": "Password changed successfully"}


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_user),
):
    return user_service.get_user(db, current_user, user_id)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_user),
):
    return user_service.update_user(db, current_user, user_id, body)


@router.post("/{user_id}/deactivate", response_model=UserRead)
def deactivate_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return user_service.deactivate_user(db, current_user, user_id)
