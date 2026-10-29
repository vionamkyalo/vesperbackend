from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from core.security import (
    AccountDeactivatedError,
    AuthenticationError,
    TooManyRequestsError,
    audit_log,
    client_ip,
    create_access_token,
    create_refresh_token,
    get_login_tracker,
    verify_password,
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
    tracker = get_login_tracker()
    email = str(body.email).strip().lower()
    ip = client_ip(request)
    key = f"{ip}:{email}"

    if tracker.is_locked(key):
        audit_log(None, "login_blocked_locked", "user", email=email, ip=ip)
        raise TooManyRequestsError()

    user = user_repository.get_by_email(db, email)

    password_valid = verify_password(
        body.password,
        user.password_hash if user is not None else None,
    )

    if user is None or not password_valid:
        tracker.record_failure(key)
        audit_log(
            user.user_id if user is not None else None,
            "login_failed",
            "user",
            email=email,
            ip=ip,
        )
        if tracker.is_locked(key):
            audit_log(
                user.user_id if user is not None else None,
                "account_locked",
                "user",
                email=email,
                ip=ip,
            )
        raise AuthenticationError()

    if not user.is_active:
        audit_log(user.user_id, "login_blocked_deactivated", "user", ip=ip)
        raise AccountDeactivatedError()

    tracker.record_success(key)
    audit_log(user.user_id, "login_success", "user", user.user_id, ip=ip)

    return TokenResponse(
        access_token=create_access_token(user.user_id, user.role.value),
        refresh_token=create_refresh_token(user.user_id),
    )
