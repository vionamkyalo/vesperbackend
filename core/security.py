import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from core.config import get_settings
from database import get_db
from models.user import User, UserRole

ACCESS_TOKEN_TYPE = "access"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_access_token(
    user_id: uuid.UUID | str,
    role: UserRole | str | None = None,
    expires_minutes: int | None = None,
) -> str:

    settings = get_settings()
    now = datetime.now(timezone.utc)
    lifetime = (
        expires_minutes
        if expires_minutes is not None
        else settings.access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=lifetime),
    }
    if role is not None:
        payload["role"] = role.value if isinstance(role, UserRole) else str(role)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        raise _credentials_error()

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise _credentials_error()

    try:
        return uuid.UUID(str(payload["sub"]))
    except (ValueError, TypeError):
        raise _credentials_error()


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:

    if not token:
        raise _credentials_error()

    user_id = decode_access_token(token)
    user = db.get(User, user_id)
    if user is None:
        raise _credentials_error()

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )
    return user


def require_patrol_coordinator(
    current_user: User = Depends(get_current_user),
) -> User:

    if current_user.role != UserRole.PATROL_COORDINATOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Patrol coordinator privileges required",
        )
    return current_user


def require_patrol_officer(
    current_user: User = Depends(get_current_user),
) -> User:

    if current_user.role != UserRole.PATROL_OFFICER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Patrol officer privileges required",
        )
    return current_user
