import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.security import (
    create_access_token,
    register_error_handlers,
    verify_password,
)
from database import get_db
from models.user import User, UserRole
from routers import auth as auth_router
import services.user as user_service_module

STRONG_PASSWORD = "Kariba-Patrol-2026"
API = "/api/auth"


def make_user(
    db_session, email, first_name, last_name, phone, role, password_hash=None
):
    user = User(
        first_name=first_name,
        last_name=last_name,
        phone_number=phone,
        email=email,
        password_hash=password_hash
        or "$argon2id$v=19$m=65536,t=3,p=4$dGVzdHNhbHQ$dGVzdGhhc2g",
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(autouse=True)
def clear_reset_codes():
    # Each test starts with an empty in-memory OTP store.
    user_service_module._reset_codes.clear()
    yield
    user_service_module._reset_codes.clear()


@pytest.fixture
def client(db_session):
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(auth_router.router, prefix="/api")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


class TestForgotPasswordRouter:
    def test_forgot_password_sends_email(
        self, client, db_session, monkeypatch
    ):
        make_user(
            db_session,
            "tendai@example.org",
            "Tendai",
            "Moyo",
            "+263771000002",
            UserRole.PATROL_OFFICER,
        )

        calls = []

        def fake_send(recipient, first_name, reset_code):
            calls.append((recipient, first_name, reset_code))

        monkeypatch.setattr(
            "services.user.send_password_reset_email", fake_send
        )

        response = client.post(
            f"{API}/forgot-password",
            json={"email": "Tendai@example.org"},
        )

        assert response.status_code == 200
        assert response.json()["message"].startswith(
            "If an account exists"
        )
        assert len(calls) == 1
        assert calls[0][0] == "tendai@example.org"
        assert calls[0][1] == "Tendai"
        assert len(calls[0][2]) == 6
        assert calls[0][2].isdigit()

    def test_forgot_password_unknown_email(
        self, client, db_session, monkeypatch
    ):
        calls = []
        monkeypatch.setattr(
            "services.user.send_password_reset_email",
            lambda recipient, first_name, reset_code: calls.append(
                (recipient, first_name, reset_code)
            ),
        )

        response = client.post(
            f"{API}/forgot-password",
            json={"email": "nobody@example.org"},
        )

        assert response.status_code == 200
        assert response.json()["message"].startswith(
            "If an account exists"
        )
        assert calls == []

    def test_forgot_password_inactive_user(
        self, client, db_session, monkeypatch
    ):
        user = make_user(
            db_session,
            "inactive@example.org",
            "Inactive",
            "User",
            "+263771000090",
            UserRole.PATROL_OFFICER,
        )
        user.is_active = False
        db_session.commit()

        calls = []
        monkeypatch.setattr(
            "services.user.send_password_reset_email",
            lambda recipient, first_name, reset_code: calls.append(
                (recipient, first_name, reset_code)
            ),
        )

        response = client.post(
            f"{API}/forgot-password",
            json={"email": "inactive@example.org"},
        )

        assert response.status_code == 200
        assert calls == []


class TestResetPasswordRouter:
    def test_reset_password_happy_path(
        self, client, db_session, monkeypatch
    ):
        user = make_user(
            db_session,
            "reset@example.org",
            "Reset",
            "User",
            "+263771000091",
            UserRole.PATROL_OFFICER,
        )

        sent = {}

        def fake_send(recipient, first_name, reset_code):
            sent["code"] = reset_code

        monkeypatch.setattr(
            "services.user.send_password_reset_email", fake_send
        )

        forgot = client.post(
            f"{API}/forgot-password",
            json={"email": "reset@example.org"},
        )
        assert forgot.status_code == 200
        assert "code" in sent

        response = client.post(
            f"{API}/reset-password",
            json={
                "email": "reset@example.org",
                "code": sent["code"],
                "new_password": STRONG_PASSWORD,
            },
        )

        assert response.status_code == 200, response.text
        assert response.json() == {
            "message": "Password has been reset successfully."
        }
        assert verify_password(STRONG_PASSWORD, user.password_hash)

    def test_reset_password_invalid_code(self, client, db_session):
        make_user(
            db_session,
            "invalid@example.org",
            "Invalid",
            "User",
            "+263771000093",
            UserRole.PATROL_OFFICER,
        )

        response = client.post(
            f"{API}/reset-password",
            json={
                "email": "invalid@example.org",
                "code": "123456",
                "new_password": STRONG_PASSWORD,
            },
        )

        assert response.status_code == 400

    def test_reset_password_wrong_code(self, client, db_session, monkeypatch):
        make_user(
            db_session,
            "wrong@example.org",
            "Wrong",
            "User",
            "+263771000094",
            UserRole.PATROL_OFFICER,
        )

        monkeypatch.setattr(
            "services.user.send_password_reset_email",
            lambda recipient, first_name, reset_code: None,
        )

        forgot = client.post(
            f"{API}/forgot-password",
            json={"email": "wrong@example.org"},
        )
        assert forgot.status_code == 200

        response = client.post(
            f"{API}/reset-password",
            json={
                "email": "wrong@example.org",
                "code": "000000",
                "new_password": STRONG_PASSWORD,
            },
        )

        assert response.status_code == 400

    def test_reset_password_weak_password(
        self, client, db_session, monkeypatch
    ):
        make_user(
            db_session,
            "weak@example.org",
            "Weak",
            "User",
            "+263771000095",
            UserRole.PATROL_OFFICER,
        )

        sent = {}

        def fake_send(recipient, first_name, reset_code):
            sent["code"] = reset_code

        monkeypatch.setattr(
            "services.user.send_password_reset_email", fake_send
        )

        forgot = client.post(
            f"{API}/forgot-password",
            json={"email": "weak@example.org"},
        )
        assert forgot.status_code == 200

        response = client.post(
            f"{API}/reset-password",
            json={
                "email": "weak@example.org",
                "code": sent["code"],
                "new_password": "alllowercase123",
            },
        )

        assert response.status_code == 400
