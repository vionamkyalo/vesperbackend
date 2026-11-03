import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy.exc import IntegrityError

from core.security import (
    ValidationFailedError,
    create_access_token,
    hash_password,
    register_error_handlers,
    verify_password,
)
from database import get_db
from models.user import User, UserRole
from repositories.user import user_repository
from routers import user as user_router
from schemas.user import PasswordChange, UserCreate, UserRead, UserUpdate
from services.user import user_service

PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$dGVzdHNhbHQ$dGVzdGhhc2g"
STRONG_PASSWORD = "Kariba-Patrol-2026"
API = "/api/users"


def valid_body(**changes):
    body = {
        "first_name": "Chipo",
        "last_name": "Dube",
        "phone_number": "+263771000099",
        "email": "Chipo.Dube@Example.org",
        "password": STRONG_PASSWORD,
    }
    body.update(changes)
    return body


def seed_settings(**changes):
    values = {
        "seed_coordinator_configured": True,
        "seed_coordinator_first_name": "Nyasha",
        "seed_coordinator_last_name": "Gumbo",
        "seed_coordinator_email": "Nyasha@Example.org",
        "seed_coordinator_phone": "+263771000050",
        "seed_coordinator_password": SecretStr(STRONG_PASSWORD),
    }
    values.update(changes)
    return SimpleNamespace(**values)


def auth_headers(user):
    token = create_access_token(user.user_id, user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(db_session):
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(user_router.router, prefix="/api")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


class TestUser:
    def test_create_user_happy_path(self, db_session):
        user = User(
            first_name="Rudo",
            last_name="Chikwanha",
            phone_number="+263771999999",
            email="rudo.c@example.org",
            password_hash=PASSWORD_HASH,
            role=UserRole.PATROL_COORDINATOR,
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.user_id is not None
        assert isinstance(user.user_id, uuid.UUID)
        assert user.first_name == "Rudo"
        assert user.last_name == "Chikwanha"
        assert user.phone_number == "+263771999999"
        assert user.email == "rudo.c@example.org"
        assert user.password_hash == PASSWORD_HASH
        assert user.role == UserRole.PATROL_COORDINATOR
        assert user.is_active is True
        assert user.created_at is not None
        assert user.updated_at is not None

    def test_user_default_fields(self, db_session):
        user = User(
            first_name="Tendai",
            last_name="Moyo",
            phone_number="+263771999998",
            email="tendai.m@example.org",
            password_hash=PASSWORD_HASH,
            role=UserRole.PATROL_OFFICER,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.is_active is True
        assert user.created_at is not None
        assert user.updated_at is not None
        assert user.created_at.tzinfo is not None

    @pytest.mark.parametrize(
        "role",
        [
            UserRole.PATROL_COORDINATOR,
            UserRole.PATROL_OFFICER,
        ],
    )
    def test_user_role_values(self, db_session, role):
        user = User(
            first_name="Test",
            last_name="User",
            phone_number="+263770000123",
            email="role.test@example.org",
            password_hash=PASSWORD_HASH,
            role=role,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.role == role

    def test_user_missing_required_fields(self, db_session):
        user = User()
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_user_missing_email(self, db_session):
        user = User(
            first_name="Test",
            last_name="User",
            phone_number="+263770000124",
            password_hash=PASSWORD_HASH,
            role=UserRole.PATROL_OFFICER,
        )
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_user_missing_phone_number(self, db_session):
        user = User(
            first_name="Test",
            last_name="User",
            email="no.phone@example.org",
            password_hash=PASSWORD_HASH,
            role=UserRole.PATROL_OFFICER,
        )
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_user_missing_password_hash(self, db_session):
        user = User(
            first_name="Test",
            last_name="User",
            phone_number="+263770000125",
            email="no.password@example.org",
            role=UserRole.PATROL_OFFICER,
        )
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_user_missing_role(self, db_session):
        user = User(
            first_name="Test",
            last_name="User",
            phone_number="+263770000126",
            email="no.role@example.org",
            password_hash=PASSWORD_HASH,
        )
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_user_unique_email(self, db_session, sample_officer):
        user = User(
            first_name="Other",
            last_name="Officer",
            phone_number="+263770000999",
            email=sample_officer.email,
            password_hash=PASSWORD_HASH,
            role=UserRole.PATROL_OFFICER,
        )
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_user_unique_phone_number(self, db_session, sample_officer):
        user = User(
            first_name="Other",
            last_name="Officer",
            phone_number=sample_officer.phone_number,
            email="other.officer@example.org",
            password_hash=PASSWORD_HASH,
            role=UserRole.PATROL_OFFICER,
        )
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_user_inspections_relationship(
        self, db_session, sample_officer, sample_inspection
    ):
        db_session.refresh(sample_officer)

        assert sample_inspection.officer.user_id == sample_officer.user_id
        assert sample_inspection in sample_officer.inspections

    def test_user_assignments_relationship(
        self, db_session, sample_officer, sample_assignment
    ):
        db_session.refresh(sample_officer)

        assert sample_assignment.officer.user_id == sample_officer.user_id
        assert sample_assignment in sample_officer.assignments

    def test_user_locations_relationship(
        self, db_session, sample_officer, sample_location
    ):
        db_session.refresh(sample_officer)

        assert sample_location.officer.user_id == sample_officer.user_id
        assert sample_location in sample_officer.locations


class TestUserRepository:
    def test_create_user(self, db_session):
        user = User(
            first_name="Chipo",
            last_name="Dube",
            phone_number="+263771000099",
            email="chipo@example.org",
            password_hash=PASSWORD_HASH,
            role=UserRole.PATROL_OFFICER,
        )

        saved = user_repository.create(db_session, user)

        assert saved.user_id is not None
        assert user_repository.get(db_session, saved.user_id) is saved

    def test_get_user_not_found(self, db_session):
        assert user_repository.get(db_session, uuid.uuid4()) is None

    def test_get_by_email_ignores_case(self, db_session, sample_officer):
        assert (
            user_repository.get_by_email(db_session, "TENDAI@example.org").user_id
            == sample_officer.user_id
        )
        assert user_repository.get_by_email(db_session, "nobody@example.org") is None

    def test_get_by_phone(self, db_session, sample_officer):
        assert (
            user_repository.get_by_phone(db_session, "+263771000002").user_id
            == sample_officer.user_id
        )
        assert user_repository.get_by_phone(db_session, "+263770000000") is None

    def test_list_users_filters(
        self, db_session, sample_coordinator, sample_officer, second_officer
    ):
        second_officer.is_active = False
        db_session.commit()

        officers = user_repository.list_users(db_session, role=UserRole.PATROL_OFFICER)
        active_officers = user_repository.list_users(
            db_session, role=UserRole.PATROL_OFFICER, is_active=True
        )

        assert len(user_repository.list_users(db_session)) == 3
        assert len(officers) == 2
        assert [user.user_id for user in active_officers] == [sample_officer.user_id]

    def test_list_users_limit_and_offset(
        self, db_session, sample_coordinator, sample_officer, second_officer
    ):
        assert len(user_repository.list_users(db_session, limit=2)) == 2
        assert len(user_repository.list_users(db_session, limit=2, offset=2)) == 1

    def test_count_by_role(
        self, db_session, sample_coordinator, sample_officer, second_officer
    ):
        assert (
            user_repository.count_by_role(db_session, UserRole.PATROL_COORDINATOR) == 1
        )
        assert user_repository.count_by_role(db_session, UserRole.PATROL_OFFICER) == 2


class TestUserSchema:
    def test_user_create_happy_path(self):
        data = UserCreate(**valid_body(first_name="  Chipo  "))

        assert data.first_name == "Chipo"
        assert data.email == "chipo.dube@example.org"

    @pytest.mark.parametrize(
        "field, value",
        [
            ("first_name", ""),
            ("last_name", "x" * 101),
            ("phone_number", "0771000099"),
            ("phone_number", "+26377"),
            ("email", "not-an-email"),
            ("password", "Short1"),
            ("password", "x" * 129),
            ("role", "admin"),
            ("is_active", False),
        ],
    )
    def test_user_create_rejects_bad_values(self, field, value):
        with pytest.raises(ValidationError):
            UserCreate(**valid_body(**{field: value}))

    @pytest.mark.parametrize(
        "field", ["first_name", "last_name", "phone_number", "email", "password"]
    )
    def test_user_create_missing_required_field(self, field):
        body = valid_body()
        del body[field]

        with pytest.raises(ValidationError):
            UserCreate(**body)

    def test_user_update_all_optional(self):
        assert UserUpdate().model_dump(exclude_unset=True) == {}

    @pytest.mark.parametrize(
        "field, value", [("role", "patrol_coordinator"), ("email", "new@example.org")]
    )
    def test_user_update_rejects_protected_fields(self, field, value):
        with pytest.raises(ValidationError):
            UserUpdate(**{field: value})

    def test_password_change_rejects_short_new_password(self):
        with pytest.raises(ValidationError):
            PasswordChange(current_password="anything", new_password="Short1")

    def test_user_read_has_no_password_hash(self):
        assert "password_hash" not in UserRead.model_fields


class TestUserService:
    def test_full_name(self, sample_coordinator):
        assert user_service.full_name(sample_coordinator) == "Rudo Chikwanha"

    def test_to_read(self, sample_officer):
        data = user_service.to_read(sample_officer)

        assert data.full_name == "Tendai Moyo"
        assert data.role == UserRole.PATROL_OFFICER

    def test_seed_coordinator(self, db_session):
        user = user_service.seed_coordinator(db_session, seed_settings())

        assert user.role == UserRole.PATROL_COORDINATOR
        assert user.email == "nyasha@example.org"
        assert verify_password(STRONG_PASSWORD, user.password_hash)

    def test_seed_coordinator_runs_once(self, db_session):
        user_service.seed_coordinator(db_session, seed_settings())

        assert user_service.seed_coordinator(db_session, seed_settings()) is None
        assert (
            user_repository.count_by_role(db_session, UserRole.PATROL_COORDINATOR) == 1
        )

    def test_seed_coordinator_uses_configured_credentials(self, db_session):
        from core.config import get_settings

        settings = get_settings()

        if not settings.seed_coordinator_configured:
            pytest.skip("Coordinator credentials are not configured")

        configured_password = settings.seed_coordinator_password.get_secret_value()

        user = user_service.seed_coordinator(db_session, settings)

        if user is None:
            user = user_repository.get_by_email(
                db_session,
                settings.seed_coordinator_email.strip().lower(),
            )

        assert user is not None
        assert user.role == UserRole.PATROL_COORDINATOR
        assert user.email == settings.seed_coordinator_email.strip().lower()
        assert user.phone_number == settings.seed_coordinator_phone
        assert user.is_active is True
        assert user.password_hash != configured_password
        assert verify_password(configured_password, user.password_hash)

    def test_seed_coordinator_not_configured(self, db_session):
        assert (
            user_service.seed_coordinator(
                db_session, seed_settings(seed_coordinator_configured=False)
            )
            is None
        )
        assert (
            user_repository.count_by_role(db_session, UserRole.PATROL_COORDINATOR) == 0
        )

    @pytest.mark.parametrize("password", ["", "weakpassword1"])
    def test_seed_coordinator_bad_password(self, db_session, password):
        with pytest.raises((RuntimeError, ValidationFailedError)):
            user_service.seed_coordinator(
                db_session, seed_settings(seed_coordinator_password=SecretStr(password))
            )

    def test_create_officer(self, db_session, sample_coordinator):
        officer = user_service.create_officer(
            db_session, sample_coordinator, UserCreate(**valid_body())
        )
        saved = user_repository.get(db_session, officer.user_id)

        assert officer.role == UserRole.PATROL_OFFICER
        assert officer.email == "chipo.dube@example.org"
        assert officer.full_name == "Chipo Dube"
        assert saved.password_hash != STRONG_PASSWORD
        assert verify_password(STRONG_PASSWORD, saved.password_hash)

    @pytest.mark.parametrize(
        "changes", [{"email": "tendai@example.org"}, {"phone_number": "+263771000002"}]
    )
    def test_create_officer_duplicate(
        self, db_session, sample_coordinator, sample_officer, changes
    ):
        with pytest.raises(HTTPException) as error:
            user_service.create_officer(
                db_session, sample_coordinator, UserCreate(**valid_body(**changes))
            )

        assert error.value.status_code == 409

    @pytest.mark.parametrize(
        "password",
        ["alllowercase123", "ALLUPPERCASE123", "NoDigitsHereAtAll", "kariba123456"],
    )
    def test_create_officer_weak_password(
        self, db_session, sample_coordinator, password
    ):
        with pytest.raises(HTTPException) as error:
            user_service.create_officer(
                db_session,
                sample_coordinator,
                UserCreate(**valid_body(password=password)),
            )

        assert error.value.status_code == 400

    def test_create_officer_by_officer_not_allowed(self, db_session, sample_officer):
        with pytest.raises(HTTPException) as error:
            user_service.create_officer(
                db_session, sample_officer, UserCreate(**valid_body())
            )

        assert error.value.status_code == 403

    def test_get_user_as_coordinator(
        self, db_session, sample_coordinator, sample_officer
    ):
        user = user_service.get_user(
            db_session, sample_coordinator, sample_officer.user_id
        )

        assert user.user_id == sample_officer.user_id

    def test_get_user_officer_sees_self_only(
        self, db_session, sample_officer, second_officer
    ):
        assert user_service.get_user(
            db_session, sample_officer, sample_officer.user_id
        ).user_id == (sample_officer.user_id)

        with pytest.raises(HTTPException) as error:
            user_service.get_user(db_session, sample_officer, second_officer.user_id)

        assert error.value.status_code == 404

    def test_get_user_not_found(self, db_session, sample_coordinator):
        with pytest.raises(HTTPException) as error:
            user_service.get_user(db_session, sample_coordinator, uuid.uuid4())

        assert error.value.status_code == 404

    def test_get_me_inactive(self, sample_officer):
        sample_officer.is_active = False

        with pytest.raises(HTTPException) as error:
            user_service.get_me(sample_officer)

        assert error.value.status_code == 403

    def test_list_users_coordinator_only(
        self, db_session, sample_coordinator, sample_officer
    ):
        assert len(user_service.list_users(db_session, sample_coordinator)) == 2

        with pytest.raises(HTTPException) as error:
            user_service.list_users(db_session, sample_officer)

        assert error.value.status_code == 403

    def test_update_user_by_coordinator(
        self, db_session, sample_coordinator, sample_officer
    ):
        body = UserUpdate(last_name="Moyo-Ncube", is_active=False)

        user = user_service.update_user(
            db_session, sample_coordinator, sample_officer.user_id, body
        )

        assert user.last_name == "Moyo-Ncube"
        assert user.full_name == "Tendai Moyo-Ncube"
        assert user.is_active is False

    def test_update_user_officer_updates_self(self, db_session, sample_officer):
        user = user_service.update_user(
            db_session,
            sample_officer,
            sample_officer.user_id,
            UserUpdate(first_name="Ten"),
        )

        assert user.first_name == "Ten"

    def test_update_user_officer_cannot_change_active(self, db_session, sample_officer):
        with pytest.raises(HTTPException) as error:
            user_service.update_user(
                db_session,
                sample_officer,
                sample_officer.user_id,
                UserUpdate(is_active=False),
            )

        assert error.value.status_code == 403

    def test_update_user_officer_cannot_edit_others(
        self, db_session, sample_officer, second_officer
    ):
        with pytest.raises(HTTPException) as error:
            user_service.update_user(
                db_session,
                sample_officer,
                second_officer.user_id,
                UserUpdate(first_name="X"),
            )

        assert error.value.status_code == 404

    def test_update_user_coordinator_cannot_deactivate_self(
        self, db_session, sample_coordinator
    ):
        with pytest.raises(HTTPException) as error:
            user_service.update_user(
                db_session,
                sample_coordinator,
                sample_coordinator.user_id,
                UserUpdate(is_active=False),
            )

        assert error.value.status_code == 409

    def test_update_user_duplicate_phone(
        self, db_session, sample_coordinator, sample_officer, second_officer
    ):
        body = UserUpdate(phone_number="+263771000002")

        with pytest.raises(HTTPException) as error:
            user_service.update_user(
                db_session, sample_coordinator, second_officer.user_id, body
            )

        assert error.value.status_code == 409

    def test_update_user_rejects_empty_field(
        self, db_session, sample_coordinator, sample_officer
    ):
        with pytest.raises(HTTPException) as error:
            user_service.update_user(
                db_session,
                sample_coordinator,
                sample_officer.user_id,
                UserUpdate(first_name=None),
            )

        assert error.value.status_code == 400

    def test_change_password(self, db_session, sample_officer):
        sample_officer.password_hash = hash_password("Old-Password-2026")
        db_session.commit()

        user_service.change_password(
            db_session,
            sample_officer,
            PasswordChange(
                current_password="Old-Password-2026", new_password=STRONG_PASSWORD
            ),
        )

        assert verify_password(STRONG_PASSWORD, sample_officer.password_hash)

    def test_change_password_wrong_current(self, db_session, sample_officer):
        body = PasswordChange(
            current_password="Wrong-Password-1", new_password=STRONG_PASSWORD
        )

        with pytest.raises(HTTPException) as error:
            user_service.change_password(db_session, sample_officer, body)

        assert error.value.status_code == 400

    def test_change_password_same_as_current(self, db_session, sample_officer):
        sample_officer.password_hash = hash_password(STRONG_PASSWORD)
        db_session.commit()
        body = PasswordChange(
            current_password=STRONG_PASSWORD, new_password=STRONG_PASSWORD
        )

        with pytest.raises(HTTPException) as error:
            user_service.change_password(db_session, sample_officer, body)

        assert error.value.status_code == 400

    def test_change_password_weak_new_password(self, db_session, sample_officer):
        sample_officer.password_hash = hash_password("Old-Password-2026")
        db_session.commit()
        body = PasswordChange(
            current_password="Old-Password-2026", new_password="alllowercase123"
        )

        with pytest.raises(HTTPException) as error:
            user_service.change_password(db_session, sample_officer, body)

        assert error.value.status_code == 400

    def test_deactivate_user(self, db_session, sample_coordinator, sample_officer):
        user = user_service.deactivate_user(
            db_session, sample_coordinator, sample_officer.user_id
        )

        assert user.is_active is False
        assert (
            user_repository.get(db_session, sample_officer.user_id).is_active is False
        )

    def test_deactivate_user_keeps_record(
        self, db_session, sample_coordinator, sample_officer
    ):
        user_service.deactivate_user(
            db_session, sample_coordinator, sample_officer.user_id
        )

        saved = user_repository.get(db_session, sample_officer.user_id)

        assert saved is not None
        assert saved.email == sample_officer.email

    def test_deactivate_user_by_officer_not_allowed(
        self, db_session, sample_officer, second_officer
    ):
        with pytest.raises(HTTPException) as error:
            user_service.deactivate_user(
                db_session, sample_officer, second_officer.user_id
            )

        assert error.value.status_code == 403

    def test_deactivate_user_not_found(self, db_session, sample_coordinator):
        with pytest.raises(HTTPException) as error:
            user_service.deactivate_user(db_session, sample_coordinator, uuid.uuid4())

        assert error.value.status_code == 404

    def test_deactivate_user_coordinator_cannot_deactivate_self(
        self, db_session, sample_coordinator
    ):
        with pytest.raises(HTTPException) as error:
            user_service.deactivate_user(
                db_session, sample_coordinator, sample_coordinator.user_id
            )

        assert error.value.status_code == 409

    def test_deactivate_user_already_inactive(
        self, db_session, sample_coordinator, sample_officer
    ):
        sample_officer.is_active = False
        db_session.commit()

        with pytest.raises(HTTPException) as error:
            user_service.deactivate_user(
                db_session, sample_coordinator, sample_officer.user_id
            )

        assert error.value.status_code == 409

    def test_deactivate_user_inactive_coordinator(
        self, db_session, sample_coordinator, sample_officer
    ):
        sample_coordinator.is_active = False

        with pytest.raises(HTTPException) as error:
            user_service.deactivate_user(
                db_session, sample_coordinator, sample_officer.user_id
            )

        assert error.value.status_code == 403


class TestUserRouter:
    def test_create_officer(self, client, sample_coordinator):
        response = client.post(
            API, json=valid_body(), headers=auth_headers(sample_coordinator)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["role"] == "patrol_officer"
        assert data["email"] == "chipo.dube@example.org"
        assert data["full_name"] == "Chipo Dube"
        assert "password" not in data
        assert "password_hash" not in data

    def test_create_user_defaults_to_officer(self, client, sample_coordinator):
        response = client.post(
            API, json=valid_body(), headers=auth_headers(sample_coordinator)
        )

        assert response.json()["role"] == "patrol_officer"

    def test_coordinator_can_create_coordinator(self, client, sample_coordinator):
        body = valid_body(role="patrol_coordinator")

        response = client.post(API, json=body, headers=auth_headers(sample_coordinator))

        assert response.status_code == 201
        assert response.json()["role"] == "patrol_coordinator"

    def test_create_coordinator_duplicate_email(
        self, client, sample_coordinator, sample_officer
    ):
        body = valid_body(role="patrol_coordinator", email="tendai@example.org")

        response = client.post(API, json=body, headers=auth_headers(sample_coordinator))

        assert response.status_code == 409

    def test_create_user_rejects_unknown_role(self, client, sample_coordinator):
        body = valid_body(role="admin")

        assert (
            client.post(
                API, json=body, headers=auth_headers(sample_coordinator)
            ).status_code
            == 422
        )

    def test_create_officer_officer_forbidden(self, client, sample_officer):
        assert (
            client.post(
                API, json=valid_body(), headers=auth_headers(sample_officer)
            ).status_code
            == 403
        )

    def test_create_officer_requires_login(self, client):
        assert client.post(API, json=valid_body()).status_code == 401

    def test_create_officer_duplicate_email(
        self, client, sample_coordinator, sample_officer
    ):
        body = valid_body(email="tendai@example.org")

        assert (
            client.post(
                API, json=body, headers=auth_headers(sample_coordinator)
            ).status_code
            == 409
        )

    def test_create_officer_weak_password(self, client, sample_coordinator):
        body = valid_body(password="alllowercase123")

        assert (
            client.post(
                API, json=body, headers=auth_headers(sample_coordinator)
            ).status_code
            == 400
        )

    def test_list_users(self, client, sample_coordinator, sample_officer):
        response = client.get(
            API,
            params={"role": "patrol_officer"},
            headers=auth_headers(sample_coordinator),
        )

        assert response.status_code == 200
        assert [user["user_id"] for user in response.json()] == [
            str(sample_officer.user_id)
        ]

    def test_list_users_officer_forbidden(self, client, sample_officer):
        assert client.get(API, headers=auth_headers(sample_officer)).status_code == 403

    def test_get_me(self, client, sample_officer):
        response = client.get(f"{API}/me", headers=auth_headers(sample_officer))

        assert response.status_code == 200
        assert response.json()["user_id"] == str(sample_officer.user_id)
        assert response.json()["full_name"] == "Tendai Moyo"

    def test_get_user_other_officer_hidden(
        self, client, sample_officer, second_officer
    ):
        response = client.get(
            f"{API}/{second_officer.user_id}", headers=auth_headers(sample_officer)
        )

        assert response.status_code == 404

    def test_update_user(self, client, sample_coordinator, sample_officer):
        response = client.patch(
            f"{API}/{sample_officer.user_id}",
            json={"is_active": False},
            headers=auth_headers(sample_coordinator),
        )

        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_deactivated_user_is_locked_out(
        self, client, sample_coordinator, sample_officer
    ):
        client.patch(
            f"{API}/{sample_officer.user_id}",
            json={"is_active": False},
            headers=auth_headers(sample_coordinator),
        )

        assert (
            client.get(f"{API}/me", headers=auth_headers(sample_officer)).status_code
            == 401
        )

    def test_update_user_cannot_change_role(
        self, client, sample_coordinator, sample_officer
    ):
        response = client.patch(
            f"{API}/{sample_officer.user_id}",
            json={"role": "patrol_coordinator"},
            headers=auth_headers(sample_coordinator),
        )

        assert response.status_code == 422

    def test_change_password(self, client, db_session, sample_officer):
        sample_officer.password_hash = hash_password("Old-Password-2026")
        db_session.commit()

        response = client.patch(
            f"{API}/me/password",
            json={
                "current_password": "Old-Password-2026",
                "new_password": STRONG_PASSWORD,
            },
            headers=auth_headers(sample_officer),
        )

        assert response.status_code == 200
        assert response.json() == {"message": "Password changed successfully"}
        assert verify_password(STRONG_PASSWORD, sample_officer.password_hash)

    def test_change_password_wrong_current(self, client, sample_officer):
        response = client.patch(
            f"{API}/me/password",
            json={
                "current_password": "Wrong-Password-1",
                "new_password": STRONG_PASSWORD,
            },
            headers=auth_headers(sample_officer),
        )

        assert response.status_code == 400

    def test_deactivate_user(self, client, sample_coordinator, sample_officer):
        response = client.post(
            f"{API}/{sample_officer.user_id}/deactivate",
            headers=auth_headers(sample_coordinator),
        )

        assert response.status_code == 200
        assert response.json()["user_id"] == str(sample_officer.user_id)
        assert response.json()["is_active"] is False

    def test_deactivate_user_locks_out(
        self, client, sample_coordinator, sample_officer
    ):
        client.post(
            f"{API}/{sample_officer.user_id}/deactivate",
            headers=auth_headers(sample_coordinator),
        )

        assert (
            client.get(f"{API}/me", headers=auth_headers(sample_officer)).status_code
            == 401
        )

    def test_deactivate_user_officer_forbidden(
        self, client, sample_officer, second_officer
    ):
        response = client.post(
            f"{API}/{second_officer.user_id}/deactivate",
            headers=auth_headers(sample_officer),
        )

        assert response.status_code == 403

    def test_deactivate_user_requires_login(self, client, sample_officer):
        response = client.post(f"{API}/{sample_officer.user_id}/deactivate")

        assert response.status_code == 401

    def test_deactivate_user_not_found(self, client, sample_coordinator):
        response = client.post(
            f"{API}/{uuid.uuid4()}/deactivate",
            headers=auth_headers(sample_coordinator),
        )

        assert response.status_code == 404

    def test_deactivate_user_twice(self, client, sample_coordinator, sample_officer):
        url = f"{API}/{sample_officer.user_id}/deactivate"
        client.post(url, headers=auth_headers(sample_coordinator))

        response = client.post(url, headers=auth_headers(sample_coordinator))

        assert response.status_code == 409

    def test_delete_user_not_available(
        self, client, sample_coordinator, sample_officer
    ):
        response = client.delete(
            f"{API}/{sample_officer.user_id}",
            headers=auth_headers(sample_coordinator),
        )

        assert response.status_code == 405