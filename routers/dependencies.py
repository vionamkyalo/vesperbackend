from fastapi import HTTPException, status

from core import security


def _auth_not_ready(name):
    def placeholder():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not set up yet.",
        )

    placeholder.__name__ = name
    return placeholder


require_coordinator = getattr(security, "require_coordinator", None) or _auth_not_ready(
    "require_coordinator"
)
require_officer = getattr(security, "require_officer", None) or _auth_not_ready(
    "require_officer"
)
require_any_user = getattr(security, "require_any_user", None) or _auth_not_ready(
    "require_any_user"
)
