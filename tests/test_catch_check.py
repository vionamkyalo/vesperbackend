import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from core.security import create_access_token, register_error_handlers
from database import get_db
from models.catch_check import CatchCheck
from repositories.catch_check import catch_check_repository
from routers import catch_check as catch_check_router
from schemas.catch_check import CatchCheckCreate, CatchCheckRead
from services.catch_check import catch_check_service

API = "/api/v1/catch-checks"


def make_catch_check(db_session, inspection, rig_identifier, checked_at):
    check = CatchCheck(
        catch_id=uuid.uuid4(),
        inspection_id=inspection.inspection_id,
        rig_identifier=rig_identifier,
        rig_nights=3,
        type_of_fish="Tilapia",
        catch_weight_kg=Decimal("100.00"),
        catch_per_rig_night=Decimal("33.33"),
        notes=None,
        checked_at=checked_at,
    )
    db_session.add(check)
    db_session.commit()
    db_session.refresh(check)
    return check


def valid_body(inspection_id=None, **changes):
    body = {
        "catch_id": str(uuid.uuid4()),
        "inspection_id": str(inspection_id or uuid.uuid4()),
        "rig_identifier": "KR-6000",
        "rig_nights": 3,
        "type_of_fish": "Tilapia",
        "catch_weight_kg": "301.00",
        "notes": "Routine nightly catch check",
        "checked_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
    }
    body.update(changes)
    return body


def auth_headers(user):
    token = create_access_token(user.user_id, user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(db_session):
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(catch_check_router.router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


class TestCatchCheck:
    def test_create_catch_check_happy_path(self, db_session, landing_inspection):
        catch_id = uuid.uuid4()
        checked_at = datetime(2026, 10, 11, 6, 0, tzinfo=timezone.utc)

        check = CatchCheck(
            catch_id=catch_id,
            inspection_id=landing_inspection.inspection_id,
            rig_identifier="KR-3000",
            rig_nights=3,
            type_of_fish="Tilapia",
            catch_weight_kg=Decimal("301.00"),
            catch_per_rig_night=Decimal("100.33"),
            notes="Routine nightly catch check",
            checked_at=checked_at,
        )
        db_session.add(check)
        db_session.commit()
        db_session.refresh(check)

        assert check.catch_id == catch_id
        assert isinstance(check.catch_id, uuid.UUID)
        assert check.inspection_id == landing_inspection.inspection_id
        assert check.rig_identifier == "KR-3000"
        assert check.rig_nights == 3
        assert check.type_of_fish == "Tilapia"
        assert check.catch_weight_kg == Decimal("301.00")
        assert check.catch_per_rig_night == Decimal("100.33")
        assert check.notes == "Routine nightly catch check"
        assert check.checked_at == checked_at
        assert check.synced_at is not None

    def test_catch_check_missing_required_fields(self, db_session):
        check = CatchCheck(catch_id=uuid.uuid4())
        db_session.add(check)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_catch_check_missing_inspection_id(self, db_session):
        check = CatchCheck(
            catch_id=uuid.uuid4(),
            rig_identifier="KR-3001",
            rig_nights=3,
            catch_weight_kg=Decimal("100.00"),
            catch_per_rig_night=Decimal("33.33"),
            checked_at=datetime(2026, 10, 11, 6, 0, tzinfo=timezone.utc),
        )
        db_session.add(check)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_catch_check_missing_catch_weight(self, db_session, landing_inspection):
        check = CatchCheck(
            catch_id=uuid.uuid4(),
            inspection_id=landing_inspection.inspection_id,
            rig_identifier="KR-3002",
            rig_nights=3,
            catch_per_rig_night=Decimal("33.33"),
            checked_at=datetime(2026, 10, 11, 6, 0, tzinfo=timezone.utc),
        )
        db_session.add(check)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_catch_check_inspection_relationship(
        self, db_session, landing_inspection, sample_catch_check
    ):
        db_session.refresh(landing_inspection)

        assert (
            sample_catch_check.inspection.inspection_id
            == landing_inspection.inspection_id
        )
        assert sample_catch_check in landing_inspection.catch_checks


class TestCatchCheckRepository:
    def test_create_catch_check(self, db_session, landing_inspection):
        catch_id = uuid.uuid4()
        check = CatchCheck(
            catch_id=catch_id,
            inspection_id=landing_inspection.inspection_id,
            rig_identifier="KR-5000",
            rig_nights=2,
            type_of_fish="Kapenta",
            catch_weight_kg=Decimal("200.00"),
            catch_per_rig_night=Decimal("100.00"),
            notes=None,
            checked_at=datetime(2026, 10, 11, 6, 0, tzinfo=timezone.utc),
        )

        saved = catch_check_repository.create(db_session, check)

        assert saved.catch_id == catch_id
        assert saved.rig_nights == 2
        assert saved.catch_per_rig_night == Decimal("100.00")
        assert saved.type_of_fish == "Kapenta"
        assert saved.synced_at is not None

    def test_get_catch_check(self, db_session, sample_catch_check):
        found = catch_check_repository.get(db_session, sample_catch_check.catch_id)
        assert found.catch_id == sample_catch_check.catch_id

    def test_get_catch_check_not_found(self, db_session):
        assert catch_check_repository.get(db_session, uuid.uuid4()) is None

    def test_get_all_catch_checks(self, db_session, landing_inspection):
        now = datetime.now(timezone.utc)
        make_catch_check(
            db_session,
            landing_inspection,
            "KR-1",
            now - timedelta(hours=2),
        )
        make_catch_check(
            db_session,
            landing_inspection,
            "KR-2",
            now - timedelta(hours=1),
        )

        assert len(catch_check_repository.get_all(db_session)) == 2

    def test_get_all_empty(self, db_session):
        assert catch_check_repository.get_all(db_session) == []

    def test_update_catch_check(self, db_session, sample_catch_check):
        sample_catch_check.type_of_fish = "Kapenta"

        saved = catch_check_repository.update(db_session, sample_catch_check)
        db_session.expire_all()

        assert saved.catch_id == sample_catch_check.catch_id
        found = catch_check_repository.get(db_session, sample_catch_check.catch_id)
        assert found.type_of_fish == "Kapenta"


class TestCatchCheckSchema:
    def test_catch_check_create_happy_path(self):
        data = CatchCheckCreate(**valid_body(catch_weight_kg="450.00"))

        assert data.rig_identifier == "KR-6000"
        assert data.rig_nights == 3
        assert data.type_of_fish == "Tilapia"
        assert data.catch_weight_kg == Decimal("450.00")
        assert data.notes == "Routine nightly catch check"

    def test_catch_check_create_converts_time_to_utc(self):
        data = CatchCheckCreate(**valid_body(checked_at="2026-10-11T06:00:00+02:00"))

        assert data.checked_at == datetime(2026, 10, 11, 4, 0, tzinfo=timezone.utc)
        assert data.checked_at.utcoffset() == timedelta(0)

    def test_catch_check_create_strips_rig_identifier(self):
        data = CatchCheckCreate(**valid_body(rig_identifier="  KR-3000  "))
        assert data.rig_identifier == "KR-3000"

    def test_catch_check_create_zero_weight_allowed(self):
        data = CatchCheckCreate(**valid_body(catch_weight_kg="0"))
        assert data.catch_weight_kg == Decimal("0")

    def test_optional_fields_can_be_omitted(self):
        body = valid_body()
        body.pop("type_of_fish")
        body.pop("notes")

        data = CatchCheckCreate(**body)

        assert data.type_of_fish is None
        assert data.notes is None

    @pytest.mark.parametrize(
        "field,value",
        [
            ("catch_weight_kg", "-1.00"),
            ("catch_weight_kg", "10.123"),
            ("catch_weight_kg", "123456789.00"),
            ("rig_nights", 0),
            ("rig_nights", -1),
            ("rig_nights", "not-a-number"),
            ("rig_identifier", ""),
            ("rig_identifier", "K" * 51),
            ("type_of_fish", "F" * 101),
            ("notes", "N" * 2001),
            ("checked_at", "2026-10-11T06:00:00"),
            ("catch_id", "not-a-uuid"),
            ("synced_at", "2026-10-11T06:00:00Z"),
        ],
    )
    def test_catch_check_create_rejects_bad_values(self, field, value):
        with pytest.raises(ValidationError):
            CatchCheckCreate(**valid_body(**{field: value}))

    @pytest.mark.parametrize(
        "field",
        [
            "catch_id",
            "inspection_id",
            "rig_identifier",
            "rig_nights",
            "catch_weight_kg",
            "checked_at",
        ],
    )
    def test_catch_check_create_missing_required_field(self, field):
        body = valid_body()
        del body[field]

        with pytest.raises(ValidationError):
            CatchCheckCreate(**body)

    def test_catch_check_read_json_uses_numbers(self, sample_catch_check):
        data = CatchCheckRead(
            catch_id=sample_catch_check.catch_id,
            inspection_id=sample_catch_check.inspection_id,
            rig_identifier=sample_catch_check.rig_identifier,
            rig_nights=sample_catch_check.rig_nights,
            type_of_fish=sample_catch_check.type_of_fish,
            catch_weight_kg=sample_catch_check.catch_weight_kg,
            catch_per_rig_night=sample_catch_check.catch_per_rig_night,
            notes=sample_catch_check.notes,
            checked_at=sample_catch_check.checked_at,
            synced_at=sample_catch_check.synced_at,
        ).model_dump(mode="json")

        assert data["rig_nights"] == 3
        assert data["catch_weight_kg"] == 450.0
        assert data["catch_per_rig_night"] == 150.0
        assert data["type_of_fish"] == "Tilapia"
        assert data["notes"] == "Routine nightly catch check"
        assert data["catch_id"] == str(sample_catch_check.catch_id)


class TestCatchCheckService:
    def test_get_inspection(self, db_session, landing_inspection):
        found = catch_check_service.get_inspection(
            db_session, landing_inspection.inspection_id
        )

        assert found.inspection_id == landing_inspection.inspection_id
        assert catch_check_service.get_inspection(db_session, uuid.uuid4()) is None

    def test_list_catch_checks_newest_first(
        self, db_session, sample_coordinator, landing_inspection
    ):
        now = datetime.now(timezone.utc)
        older = make_catch_check(
            db_session,
            landing_inspection,
            "KR-1",
            now - timedelta(hours=5),
        )
        newer = make_catch_check(
            db_session,
            landing_inspection,
            "KR-2",
            now - timedelta(hours=1),
        )

        checks = catch_check_service.list_catch_checks(db_session, sample_coordinator)

        assert [check.catch_id for check in checks] == [
            newer.catch_id,
            older.catch_id,
        ]

    def test_list_catch_checks_limit_and_offset(
        self, db_session, sample_coordinator, landing_inspection
    ):
        now = datetime.now(timezone.utc)
        for number in range(3):
            make_catch_check(
                db_session,
                landing_inspection,
                f"KR-{number}",
                now - timedelta(hours=number + 1),
            )

        assert (
            len(
                catch_check_service.list_catch_checks(
                    db_session, sample_coordinator, limit=2
                )
            )
            == 2
        )
        assert (
            len(
                catch_check_service.list_catch_checks(
                    db_session, sample_coordinator, limit=2, offset=2
                )
            )
            == 1
        )

    def test_create_catch_check(self, db_session, sample_officer, landing_inspection):
        body = CatchCheckCreate(**valid_body(landing_inspection.inspection_id))

        result = catch_check_service.create_catch_check(
            db_session, sample_officer, body
        )

        assert result.catch_id == body.catch_id
        assert result.rig_nights == 3
        assert result.catch_weight_kg == Decimal("301.00")
        assert result.catch_per_rig_night == Decimal("100.33")
        assert result.type_of_fish == "Tilapia"
        assert result.notes == "Routine nightly catch check"
        assert result.synced_at is not None
        assert db_session.get(CatchCheck, body.catch_id) is not None

    def test_create_catch_check_calculates_catch_per_rig_night(
        self, db_session, sample_officer, landing_inspection
    ):
        body = CatchCheckCreate(
            **valid_body(
                landing_inspection.inspection_id,
                rig_nights=3,
                catch_weight_kg="300.00",
            )
        )

        result = catch_check_service.create_catch_check(
            db_session, sample_officer, body
        )

        assert result.rig_nights == 3
        assert result.catch_weight_kg == Decimal("300.00")
        assert result.catch_per_rig_night == Decimal("100.00")

    def test_create_catch_check_retry_returns_same_record(
        self, db_session, sample_officer, landing_inspection
    ):
        body = CatchCheckCreate(**valid_body(landing_inspection.inspection_id))

        first = catch_check_service.create_catch_check(db_session, sample_officer, body)
        second = catch_check_service.create_catch_check(
            db_session, sample_officer, body
        )

        assert first.catch_id == second.catch_id
        assert len(catch_check_repository.get_all(db_session)) == 1

    def test_create_catch_check_reused_id_conflicts(
        self, db_session, sample_officer, sample_catch_check
    ):
        body = CatchCheckCreate(**valid_body(catch_id=str(sample_catch_check.catch_id)))

        with pytest.raises(HTTPException) as error:
            catch_check_service.create_catch_check(db_session, sample_officer, body)

        assert error.value.status_code == 409

    def test_create_catch_check_unknown_inspection(self, db_session, sample_officer):
        with pytest.raises(HTTPException) as error:
            catch_check_service.create_catch_check(
                db_session,
                sample_officer,
                CatchCheckCreate(**valid_body()),
            )

        assert error.value.status_code == 404

    def test_create_catch_check_other_officers_inspection(
        self, db_session, second_officer, landing_inspection
    ):
        body = CatchCheckCreate(**valid_body(landing_inspection.inspection_id))

        with pytest.raises(HTTPException) as error:
            catch_check_service.create_catch_check(db_session, second_officer, body)

        assert error.value.status_code == 404

    def test_create_catch_check_needs_landing_site_inspection(
        self, db_session, sample_officer, sample_inspection
    ):
        body = CatchCheckCreate(**valid_body(sample_inspection.inspection_id))

        with pytest.raises(HTTPException) as error:
            catch_check_service.create_catch_check(db_session, sample_officer, body)

        assert error.value.status_code == 409

    def test_create_catch_check_rejects_future_time(
        self, db_session, sample_officer, landing_inspection
    ):
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        body = CatchCheckCreate(
            **valid_body(landing_inspection.inspection_id, checked_at=future)
        )

        with pytest.raises(HTTPException) as error:
            catch_check_service.create_catch_check(db_session, sample_officer, body)

        assert error.value.status_code == 400

    def test_create_catch_check_coordinator_not_allowed(
        self, db_session, sample_coordinator, landing_inspection
    ):
        body = CatchCheckCreate(**valid_body(landing_inspection.inspection_id))

        with pytest.raises(HTTPException) as error:
            catch_check_service.create_catch_check(db_session, sample_coordinator, body)

        assert error.value.status_code == 403

    def test_create_catch_check_inactive_officer(
        self, db_session, sample_officer, landing_inspection
    ):
        sample_officer.is_active = False
        body = CatchCheckCreate(**valid_body(landing_inspection.inspection_id))

        with pytest.raises(HTTPException) as error:
            catch_check_service.create_catch_check(db_session, sample_officer, body)

        assert error.value.status_code == 403

    def test_get_catch_check_as_owner(
        self, db_session, sample_officer, sample_catch_check
    ):
        result = catch_check_service.get_catch_check(
            db_session, sample_officer, sample_catch_check.catch_id
        )

        assert result.catch_id == sample_catch_check.catch_id
        assert result.rig_nights == 3
        assert result.catch_weight_kg == Decimal("450.00")
        assert result.catch_per_rig_night == Decimal("150.00")
        assert result.type_of_fish == "Tilapia"

    def test_get_catch_check_as_coordinator(
        self, db_session, sample_coordinator, sample_catch_check
    ):
        result = catch_check_service.get_catch_check(
            db_session, sample_coordinator, sample_catch_check.catch_id
        )
        assert result.catch_id == sample_catch_check.catch_id

    def test_get_catch_check_hidden_from_other_officer(
        self, db_session, second_officer, sample_catch_check
    ):
        with pytest.raises(HTTPException) as error:
            catch_check_service.get_catch_check(
                db_session, second_officer, sample_catch_check.catch_id
            )

        assert error.value.status_code == 404

    def test_get_catch_check_not_found(self, db_session, sample_coordinator):
        with pytest.raises(HTTPException) as error:
            catch_check_service.get_catch_check(
                db_session, sample_coordinator, uuid.uuid4()
            )

        assert error.value.status_code == 404

    def test_list_catch_checks_as_coordinator(
        self, db_session, sample_coordinator, sample_catch_check
    ):
        results = catch_check_service.list_catch_checks(db_session, sample_coordinator)

        assert [result.catch_id for result in results] == [sample_catch_check.catch_id]
        assert results[0].rig_nights == 3
        assert results[0].catch_weight_kg == Decimal("450.00")
        assert results[0].catch_per_rig_night == Decimal("150.00")

    def test_list_catch_checks_officer_sees_only_own(
        self, db_session, sample_officer, second_officer, sample_catch_check
    ):
        assert (
            len(catch_check_service.list_catch_checks(db_session, sample_officer)) == 1
        )
        assert catch_check_service.list_catch_checks(db_session, second_officer) == []

    def test_list_catch_checks_filter_by_inspection(
        self,
        db_session,
        sample_coordinator,
        sample_catch_check,
        landing_inspection,
    ):
        results = catch_check_service.list_catch_checks(
            db_session,
            sample_coordinator,
            inspection_id=landing_inspection.inspection_id,
        )

        assert len(results) == 1
        assert (
            catch_check_service.list_catch_checks(
                db_session,
                sample_coordinator,
                inspection_id=uuid.uuid4(),
            )
            == []
        )


class TestCatchCheckRouter:
    def test_create_catch_check(self, client, sample_officer, landing_inspection):
        body = valid_body(
            landing_inspection.inspection_id,
            catch_weight_kg="450.00",
        )

        response = client.post(API, json=body, headers=auth_headers(sample_officer))

        assert response.status_code == 201
        data = response.json()
        assert data["catch_id"] == body["catch_id"]
        assert data["rig_nights"] == 3
        assert data["catch_weight_kg"] == 450.0
        assert data["catch_per_rig_night"] == 150.0
        assert data["type_of_fish"] == "Tilapia"
        assert data["notes"] == "Routine nightly catch check"
        assert data["synced_at"] is not None

    def test_create_catch_check_retry_is_safe(
        self, client, sample_officer, landing_inspection
    ):
        body = valid_body(landing_inspection.inspection_id)
        headers = auth_headers(sample_officer)

        first = client.post(API, json=body, headers=headers)
        second = client.post(API, json=body, headers=headers)

        assert first.status_code == 201
        assert second.status_code == 201
        assert len(client.get(API, headers=headers).json()) == 1

    def test_create_catch_check_coordinator_forbidden(
        self, client, sample_coordinator, landing_inspection
    ):
        response = client.post(
            API,
            json=valid_body(landing_inspection.inspection_id),
            headers=auth_headers(sample_coordinator),
        )

        assert response.status_code == 403

    def test_create_catch_check_requires_login(self, client, landing_inspection):
        response = client.post(API, json=valid_body(landing_inspection.inspection_id))
        assert response.status_code == 401

    def test_create_catch_check_unknown_inspection(self, client, sample_officer):
        response = client.post(
            API, json=valid_body(), headers=auth_headers(sample_officer)
        )
        assert response.status_code == 404

    def test_create_catch_check_wrong_inspection_type(
        self, client, sample_officer, sample_inspection
    ):
        response = client.post(
            API,
            json=valid_body(sample_inspection.inspection_id),
            headers=auth_headers(sample_officer),
        )
        assert response.status_code == 409

    def test_create_catch_check_future_time(
        self, client, sample_officer, landing_inspection
    ):
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        body = valid_body(
            landing_inspection.inspection_id,
            checked_at=future,
        )

        response = client.post(API, json=body, headers=auth_headers(sample_officer))
        assert response.status_code == 400

    @pytest.mark.parametrize(
        "field,value",
        [
            ("catch_weight_kg", "-5"),
            ("rig_nights", 0),
            ("rig_nights", -1),
            ("checked_at", "2026-10-11T06:00:00"),
            ("type_of_fish", "F" * 101),
            ("extra", "x"),
        ],
    )
    def test_create_catch_check_bad_body(
        self,
        client,
        sample_officer,
        landing_inspection,
        field,
        value,
    ):
        body = valid_body(
            landing_inspection.inspection_id,
            **{field: value},
        )

        response = client.post(API, json=body, headers=auth_headers(sample_officer))
        assert response.status_code == 422

    def test_create_catch_check_optional_fields_can_be_null(
        self, client, sample_officer, landing_inspection
    ):
        body = valid_body(landing_inspection.inspection_id)
        body["type_of_fish"] = None
        body["notes"] = None

        response = client.post(API, json=body, headers=auth_headers(sample_officer))

        assert response.status_code == 201
        assert response.json()["type_of_fish"] is None
        assert response.json()["notes"] is None

    def test_list_catch_checks(self, client, sample_coordinator, sample_catch_check):
        response = client.get(API, headers=auth_headers(sample_coordinator))

        assert response.status_code == 200
        data = response.json()
        assert data[0]["catch_id"] == str(sample_catch_check.catch_id)
        assert data[0]["rig_nights"] == 3
        assert data[0]["catch_weight_kg"] == 450.0
        assert data[0]["catch_per_rig_night"] == 150.0
        assert data[0]["type_of_fish"] == "Tilapia"

    def test_list_catch_checks_officer_scoped(
        self, client, second_officer, sample_catch_check
    ):
        response = client.get(API, headers=auth_headers(second_officer))

        assert response.status_code == 200
        assert response.json() == []

    def test_list_catch_checks_bad_limit(self, client, sample_coordinator):
        response = client.get(
            API,
            params={"limit": 0},
            headers=auth_headers(sample_coordinator),
        )
        assert response.status_code == 422

    def test_get_catch_check(self, client, sample_officer, sample_catch_check):
        response = client.get(
            f"{API}/{sample_catch_check.catch_id}",
            headers=auth_headers(sample_officer),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["rig_identifier"] == "KR-2001"
        assert data["rig_nights"] == 3
        assert data["catch_weight_kg"] == 450.0
        assert data["catch_per_rig_night"] == 150.0

    def test_get_catch_check_hidden_from_other_officer(
        self, client, second_officer, sample_catch_check
    ):
        response = client.get(
            f"{API}/{sample_catch_check.catch_id}",
            headers=auth_headers(second_officer),
        )
        assert response.status_code == 404

    def test_get_catch_check_not_found(self, client, sample_coordinator):
        response = client.get(
            f"{API}/{uuid.uuid4()}",
            headers=auth_headers(sample_coordinator),
        )
        assert response.status_code == 404
