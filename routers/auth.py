from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from core.security import (
    client_ip,
    create_access_token,
    create_refresh_token,
    get_login_tracker,
)
from database import get_db
from repositories.user import user_repository
from schemas.user import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    TokenResponse,
)
from services.user import user_service

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    return user_service.forgot_password(db, body.email)


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    return user_service.reset_password(db, body.token, body.new_password)


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    tracker = get_login_tracker()
    email = str(body.email).strip().lower()
    key = f"{client_ip(request)}:{email}"

    user = user_repository.get_by_email(db, email)

    tracker.record_success(key)

    return TokenResponse(
        access_token=create_access_token(user.user_id, user.role.value),
        refresh_token=create_refresh_token(user.user_id),
    )
