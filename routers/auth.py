from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from core.security import (
    AuthenticationError,
    TooManyRequestsError,
    client_ip,
    create_access_token,
    create_refresh_token,
    get_login_tracker,
    verify_password,
)
from database import get_db
from repositories.user import user_repository
from schemas.user import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    tracker = get_login_tracker()
    email = str(body.email).strip().lower()
    key = f"{client_ip(request)}:{email}"

    if tracker.is_locked(key):
        raise TooManyRequestsError("Too many failed login attempts. Try again later.")

    user = user_repository.get_by_email(db, email)

    if user is None or not verify_password(
        body.password,
        user.password_hash if user else None,
    ):
        tracker.record_failure(key)
        raise AuthenticationError("Invalid email or password")

    if not user.is_active:
        tracker.record_failure(key)
        raise AuthenticationError("Invalid email or password")

    tracker.record_success(key)

    return TokenResponse(
        access_token=create_access_token(user.user_id, user.role.value),
        refresh_token=create_refresh_token(user.user_id),
    )
