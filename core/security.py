import json
import logging
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Deque, Dict

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send


from core.config import Settings, get_settings, redact
from database import get_db
from models.user import User, UserRole

logger = logging.getLogger("vesper.security")
audit_logger = logging.getLogger("vesper.audit")


class VesperError(Exception):
    status_code = 400
    default_message = "Request could not be processed"

    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)


class NotFoundError(VesperError):
    status_code = 404
    default_message = "Resource not found"


class PermissionDeniedError(VesperError):
    status_code = 403
    default_message = "You do not have permission to perform this action"


class AuthenticationError(VesperError):
    status_code = 401
    default_message = "Invalid credentials"


class AccountDeactivatedError(VesperError):
    status_code = 403
    default_message = "Account is deactivated"


class ConflictError(VesperError):
    status_code = 409
    default_message = "The request conflicts with the current state"


class ValidationFailedError(VesperError):
    status_code = 422
    default_message = "The submitted data is not valid"


class TooManyRequestsError(VesperError):
    status_code = 429
    default_message = "Too many requests. Try again later"


class SatelliteDataError(VesperError):
    status_code = 502
    default_message = "Satellite data could not be retrieved"


def _request_id(request: Request) -> str:
    return (request.scope.get("state") or {}).get("request_id") or uuid.uuid4().hex


async def _vesper_error(request: Request, exc: VesperError) -> JSONResponse:
    headers = (
        {"WWW-Authenticate": "Bearer"} if isinstance(exc, AuthenticationError) else None
    )
    body = {"detail": exc.message, "request_id": _request_id(request)}
    return JSONResponse(status_code=exc.status_code, content=body, headers=headers)


async def _validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", [])]
        errors.append(
            {"loc": location, "msg": error.get("msg"), "type": error.get("type")}
        )
    body = {
        "detail": "The submitted data is not valid",
        "errors": errors,
        "request_id": _request_id(request),
    }
    return JSONResponse(status_code=422, content=body)


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if exc.status_code < 500 else "Server error"
    body = {"detail": detail, "request_id": _request_id(request)}
    return JSONResponse(
        status_code=exc.status_code, content=body, headers=getattr(exc, "headers", None)
    )


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    logger.exception(
        "unhandled error",
        extra={"extra_fields": {"request_id": request_id, "path": request.url.path}},
    )
    body = {
        "detail": "Something went wrong. Quote the request ID if you report this.",
        "request_id": request_id,
    }
    return JSONResponse(status_code=500, content=body)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(VesperError, _vesper_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled_error)


_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")
COMMON_PASSWORDS = {
    "password123",
    "123456789012",
    "qwertyuiop12",
    "welcome12345",
    "kariba123456",
    "vesper123456",
}


def validate_password_strength(password: str) -> str:
    if not 12 <= len(password) <= 128:
        raise ValidationFailedError(
            "Password must be between 12 and 128 characters long"
        )
    if password.lower() in COMMON_PASSWORDS:
        raise ValidationFailedError("Password is too common")
    if not (
        re.search(r"[a-z]", password)
        and re.search(r"[A-Z]", password)
        and re.search(r"\d", password)
    ):
        raise ValidationFailedError(
            "Password must contain upper case, lower case and a digit"
        )
    return password


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        try:
            _hasher.verify(_DUMMY_HASH, password)
        except VerificationError:
            pass
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


ACCESS_TOKEN = "access"
REFRESH_TOKEN = "refresh"
RESET_TOKEN = "reset"


def _create_token(
    subject: str,
    token_type: str,
    lifetime: timedelta,
    extra: Dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": now + lifetime,
        "jti": uuid.uuid4().hex,
        **(extra or {}),
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    minutes = get_settings().access_token_ttl_minutes
    return _create_token(
        str(user_id), ACCESS_TOKEN, timedelta(minutes=minutes), {"role": role}
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    return _create_token(
        str(user_id),
        REFRESH_TOKEN,
        timedelta(days=get_settings().refresh_token_ttl_days),
    )


def create_reset_token(user_id: uuid.UUID) -> str:
    return _create_token(
        str(user_id),
        RESET_TOKEN,
        timedelta(minutes=15),
    )


def decode_token(token: str, expected_type: str) -> Dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "type", "iss", "aud"]},
        )
        uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise AuthenticationError("Invalid or expired token") from exc
    if payload.get("type") != expected_type:
        raise AuthenticationError("Invalid or expired token")
    return payload


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window_seconds:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True


class LoginAttemptTracker:
    def __init__(self, max_attempts: int, lockout_seconds: int):
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self._failures: Dict[str, Deque[float]] = defaultdict(deque)
        self._locked_until: Dict[str, float] = {}
        self._lock = threading.Lock()

    def is_locked(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            until = self._locked_until.get(key)
            if until is None:
                return False
            if now >= until:
                self._locked_until.pop(key, None)
                self._failures.pop(key, None)
                return False
            return True

    def record_failure(self, key: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            failures = self._failures[key]
            while failures and now - failures[0] >= self.lockout_seconds:
                failures.popleft()
            failures.append(now)
            if len(failures) >= self.max_attempts:
                self._locked_until[key] = now + self.lockout_seconds

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)


_login_tracker: LoginAttemptTracker | None = None


def get_login_tracker() -> LoginAttemptTracker:
    global _login_tracker
    if _login_tracker is None:
        settings = get_settings()
        _login_tracker = LoginAttemptTracker(
            settings.login_max_attempts, settings.login_lockout_minutes * 60
        )
    return _login_tracker


def reset_login_tracker() -> None:
    global _login_tracker
    _login_tracker = None


_bearer = HTTPBearer(auto_error=False)


def user_from_token(db: Session, token: str) -> User:
    payload = decode_token(token, ACCESS_TOKEN)
    user = db.get(User, uuid.UUID(payload["sub"]))

    if user is None:
        raise AuthenticationError("Invalid or expired token")

    if not user.is_active:
        raise AuthenticationError("Account is deactivated")

    if payload.get("role") != user.role.value:
        raise AuthenticationError("Invalid or expired token")

    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Not authenticated")
    return user_from_token(db, credentials.credentials)


def require_role(*roles: UserRole) -> Callable[..., User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise PermissionDeniedError()
        return user

    return checker


require_coordinator = require_role(UserRole.PATROL_COORDINATOR)
require_officer = require_role(UserRole.PATROL_OFFICER)
require_any_user = require_role(UserRole.PATROL_COORDINATOR, UserRole.PATROL_OFFICER)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def audit_log(
    actor_id: uuid.UUID | None,
    action: str,
    entity: str,
    entity_id: Any = None,
    **metadata: Any,
) -> None:
    fields = {
        "actor_id": str(actor_id) if actor_id else None,
        "action": action,
        "entity": entity,
        "entity_id": str(entity_id) if entity_id is not None else None,
        **redact(metadata),
    }
    audit_logger.info("audit", extra={"extra_fields": fields})


_REQUEST_ID = re.compile(r"^[A-Za-z0-9\-]{8,64}$")


async def _reject(
    send: Send, status: int, detail: str, headers: list | None = None
) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ]
            + (headers or []),
        }
    )
    await send({"type": "http.response.body", "body": body})


class SecurityMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings, limiter: SlidingWindowLimiter):
        self.app = app
        self.max_bytes = settings.max_request_bytes
        self.enable_hsts = settings.is_production
        self.limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        incoming_id = headers.get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming_id if _REQUEST_ID.match(incoming_id) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status = {"code": 500}
        path = scope.get("path", "")

        async def send_secured(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                extra = [
                    (b"x-request-id", request_id.encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cache-control", b"no-store"),
                ]
                if not path.startswith(("/docs", "/redoc", "/openapi.json")):
                    extra.append(
                        (
                            b"content-security-policy",
                            b"default-src 'none'; frame-ancestors 'none'",
                        )
                    )
                if self.enable_hsts:
                    extra.append(
                        (
                            b"strict-transport-security",
                            b"max-age=31536000; includeSubDomains",
                        )
                    )
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        try:
            client = scope.get("client")
            if path != "/health" and not self.limiter.allow(
                client[0] if client else "unknown"
            ):
                await _reject(
                    send_secured,
                    429,
                    "Too many requests. Try again later",
                    [(b"retry-after", b"60")],
                )
                return
            length = headers.get(b"content-length")
            if length is not None and (
                not length.isdigit() or int(length) > self.max_bytes
            ):
                await _reject(send_secured, 413, "Request body is too large")
                return
            await self.app(scope, receive, send_secured)
        finally:
            logger.info(
                "request",
                extra={
                    "extra_fields": {
                        "request_id": request_id,
                        "method": scope.get("method"),
                        "path": path,
                        "status": status["code"],
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                },
            )


def apply_security(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "ngrok-skip-browser-warning",
        ],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(
        SecurityMiddleware,
        settings=settings,
        limiter=SlidingWindowLimiter(settings.api_rate_limit_per_minute, 60),
    )
    register_error_handlers(app)
