from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from core.security import audit_log, client_ip
from database import get_db
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
    request: Request,
    db: Session = Depends(get_db),
):
    audit_log(
        None,
        "password_reset_requested",
        "user",
        email=str(body.email),
        ip=client_ip(request),
    )
    return user_service.forgot_password(db, body.email)


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    result = user_service.reset_password(
        db,
        email=str(body.email),
        code=body.code,
        new_password=body.new_password,
    )
    audit_log(
        None,
        "password_reset_completed",
        "user",
        email=str(body.email),
        ip=client_ip(request),
    )
    return result


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    return user_service.login(db, str(body.email), body.password, client_ip(request))
