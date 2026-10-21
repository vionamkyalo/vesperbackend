from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import User, UserRole


def require_local_test_mode(request: Request):
    client_host = request.client.host if request.client else None

    if client_host not in {"127.0.0.1", "::1"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Testing tools can only be used from this computer.",
        )


def get_current_user(
    db: Session = Depends(get_db),
    x_test_user_id: UUID | None = Header(
        default=None,
        alias="X-Test-User-ID",
        description="LOCAL TESTING ONLY: UUID of an existing test user.",
    ),
    _local_test_mode: None = Depends(require_local_test_mode),
) -> User:
    if x_test_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Enter an existing test user's UUID in X-Test-User-ID.",
        )

    user = db.get(User, x_test_user_id)

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The selected test user does not exist or is inactive.",
        )

    return user


def require_any_user(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


def require_coordinator(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.PATROL_COORDINATOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the patrol coordinator can do this.",
        )

    return current_user


def require_officer(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.PATROL_OFFICER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only patrol officers can do this.",
        )

    return current_user
