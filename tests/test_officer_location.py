import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

import models.catch_check  # noqa: F401
import models.inspection  # noqa: F401
import models.violation_report  # noqa: F401
import models.zone_baseline  # noqa: F401
import models.zone_setting_history  # noqa: F401
from core.config import get_settings
from core.security import create_access_token
from models.alert import Alert, AlertStatus
from models.officer_location import OfficerLocation
from repositories.officer_location import OfficerLocationRepository
from schemas.officer_location import OfficerLocationCreate
from services.officer_location import (
    evaluate_jump,
    haversine_m,
)

TEST_JWT_SECRET = "test-only-jwt-secret-for-pytest-runs-0123456789"


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch):
    if len(os.environ.get("JWT_SECRET", "")) < 32:
        monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client(db_session):
    from database import get_db
    from fastapi.testclient import TestClient
    from main import app

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def headers_for():
    def _headers(user):
        token = create_access_token(user.user_id, user.role.value)
        return {"Authorization": f"Bearer {token}"}

    return _headers


@pytest.fixture
def coordinator_headers(headers_for, sample_coordinator):
    return headers_for(sample_coordinator)


@pytest.fixture
def officer_headers(headers_for, sample_officer):
    return headers_for(sample_officer)


@pytest.fixture
def second_officer_headers(headers_for, second_officer):
    return headers_for(second_officer)


@pytest.fixture
def make_alert(db_session, sample_zone, sample_reading):
    def _make(
        cluster_label,
        confidence="0.6000",
        status=AlertStatus.NEW,
        officer=None,
        created_at=None,
        latitude="-16.850000",
        longitude="28.050000",
        **extra,
    ):
        alert = Alert(
            zone_id=sample_zone.zone_id,
            reading_id=sample_reading.reading_id,
            cluster_label=cluster_label,
            point_count=5,
            confidence=Decimal(confidence),
            centroid_latitude=Decimal(latitude),
            centroid_longitude=Decimal(longitude),
            status=status,
            officer_id=officer.user_id if officer else None,
            **extra,
        )
        if created_at is not None:
            alert.created_at = created_at
        db_session.add(alert)
        db_session.commit()
        db_session.refresh(alert)
        return alert

    return _make


@pytest.fixture
def make_location(db_session):
    def _make(
        officer,
        recorded_at,
        latitude="-16.850000",
        longitude="28.050000",
        alert=None,
        accuracy_m=None,
    ):
        location = OfficerLocation(
            location_id=uuid.uuid4(),
            officer_id=officer.user_id,
            alert_id=alert.alert_id if alert else None,
            latitude=Decimal(latitude),
            longitude=Decimal(longitude),
            accuracy_m=Decimal(accuracy_m) if accuracy_m is not None else None,
            recorded_at=recorded_at,
        )
        db_session.add(location)
        db_session.commit()
        db_session.refresh(location)
        return location

    return _make


@pytest.fixture
def location_payload():
    return {
        "location_id": str(uuid.uuid4()),
        "latitude": "-16.851000",
        "longitude": "28.049000",
        "accuracy_m": "8.50",
        "recorded_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
    }


OFFICER_ONLY = [
    (
        "post",
        "/api/officer-locations",
        {
            "latitude": "-16.851000",
            "longitude": "28.049000",
            "accuracy_m": "10.00",
            "recorded_at": "2026-10-10T21:45:00Z",
        },
    ),
    ("get", "/api/me", None),
]
COORDINATOR_ONLY = [
    ("get", "/api/officer-locations", None),
    ("get", "/api/officer-locations/latest", None),
    ("post", "/api/officer-locations/retention/purge", None),
]
ANY_ROLE = [
    ("get", "/api/officer-locations/{id}", None),
    ("get", "/api/officer-locations/arrival-check/{id}", None),
]


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def minutes_ago(minutes: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


def call_api(client, method, path, body=None, headers=None):
    url = path.replace("{id}", str(uuid.uuid4()))
    kwargs = {"headers": headers or {}}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(url, **kwargs)


def create_payload(**overrides):
    body = {
        "location_id": str(uuid.uuid4()),
        "latitude": "-16.851000",
        "longitude": "28.049000",
        "accuracy_m": "12.50",
        "recorded_at": minutes_ago(5).isoformat(),
    }
    body.update(overrides)
    return body


class TestOfficerLocation:
    def test_create_officer_location_happy_path(
        self, db_session, sample_officer, sample_alert
    ):
        location_id = uuid.uuid4()
        recorded_at = datetime(2026, 10, 10, 21, 45, tzinfo=timezone.utc)
        location = OfficerLocation(
            location_id=location_id,
            officer_id=sample_officer.user_id,
            alert_id=sample_alert.alert_id,
            latitude=Decimal("-16.851000"),
            longitude=Decimal("28.049000"),
            accuracy_m=Decimal("12.50"),
            recorded_at=recorded_at,
        )
        db_session.add(location)
        db_session.commit()
        db_session.refresh(location)

        assert location.location_id == location_id
        assert isinstance(location.location_id, uuid.UUID)
        assert location.officer_id == sample_officer.user_id
        assert location.alert_id == sample_alert.alert_id
        assert location.latitude == Decimal("-16.851000")
        assert location.longitude == Decimal("28.049000")
        assert location.accuracy_m == Decimal("12.50")
        assert location.recorded_at == recorded_at
        assert location.synced_at is not None

    def test_officer_location_optional_fields(self, db_session, sample_officer):
        location = OfficerLocation(
            location_id=uuid.uuid4(),
            officer_id=sample_officer.user_id,
            latitude=Decimal("-16.80"),
            longitude=Decimal("28.00"),
            recorded_at=datetime(2026, 10, 10, 21, 0, tzinfo=timezone.utc),
        )
        db_session.add(location)
        db_session.commit()
        db_session.refresh(location)

        assert location.alert_id is None
        assert location.accuracy_m is None
        assert location.synced_at is not None

    def test_officer_location_missing_required_fields(self, db_session):
        location = OfficerLocation(location_id=uuid.uuid4())
        db_session.add(location)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_officer_location_missing_officer_id(self, db_session):
        location = OfficerLocation(
            location_id=uuid.uuid4(),
            latitude=Decimal("-16.80"),
            longitude=Decimal("28.00"),
            recorded_at=datetime(2026, 10, 10, 21, 0, tzinfo=timezone.utc),
        )
        db_session.add(location)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_officer_location_missing_latitude(self, db_session, sample_officer):
        location = OfficerLocation(
            location_id=uuid.uuid4(),
            officer_id=sample_officer.user_id,
            longitude=Decimal("28.00"),
            recorded_at=datetime(2026, 10, 10, 21, 0, tzinfo=timezone.utc),
        )
        db_session.add(location)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_officer_location_officer_relationship(
        self, db_session, sample_officer, sample_location
    ):
        db_session.refresh(sample_officer)

        assert sample_location.officer.user_id == sample_officer.user_id
        assert sample_location in sample_officer.locations

    def test_officer_location_alert_relationship(
        self, db_session, sample_alert, sample_location
    ):
        db_session.refresh(sample_location)

        assert sample_location.alert.alert_id == sample_alert.alert_id


class FakeFix:
    def __init__(self, lat, lon, at, accuracy=None):
        self.latitude = Decimal(lat)
        self.longitude = Decimal(lon)
        self.recorded_at = at
        self.accuracy_m = Decimal(accuracy) if accuracy is not None else None


class TestLocationSchemas:
    def test_valid_create_normalises_to_utc(self):
        fix = OfficerLocationCreate(
            **create_payload(recorded_at="2026-10-10T23:45:00+02:00")
        )
        assert fix.latitude == Decimal("-16.851000")
        assert fix.recorded_at == datetime(2026, 10, 10, 21, 45, tzinfo=timezone.utc)

    @pytest.mark.parametrize(
        "field, value",
        [
            ("latitude", "-90.000001"),
            ("longitude", "180.000001"),
            ("accuracy_m", "-0.01"),
            ("recorded_at", "2026-10-10T21:45:00"),
        ],
    )
    def test_invalid_values_rejected(self, field, value):
        with pytest.raises(ValidationError):
            OfficerLocationCreate(**create_payload(**{field: value}))

    def test_server_fields_forbidden(self):
        with pytest.raises(ValidationError):
            OfficerLocationCreate(**create_payload(officer_id=str(uuid.uuid4())))

    def test_accuracy_is_optional(self):
        payload = create_payload()
        del payload["accuracy_m"]
        assert OfficerLocationCreate(**payload).accuracy_m is None


class TestLocationRepository:
    @pytest.fixture
    def repo(self, db_session):
        return OfficerLocationRepository(db_session)

    def test_create_and_duplicate_id(self, repo, sample_officer):
        loc_id = uuid.uuid4()

        def build():
            return OfficerLocation(
                location_id=loc_id,
                officer_id=sample_officer.user_id,
                latitude=Decimal("-16.85"),
                longitude=Decimal("28.05"),
                recorded_at=utc(2026, 10, 10, 21),
            )

        assert repo.create(build()).synced_at is not None
        with pytest.raises(IntegrityError):
            repo.create(build())

    def test_latest_per_officer(
        self, repo, make_location, sample_officer, second_officer
    ):
        make_location(sample_officer, utc(2026, 10, 10, 20))
        fix2 = make_location(sample_officer, utc(2026, 10, 10, 21))
        fix_other = make_location(second_officer, utc(2026, 10, 10, 22))
        by_officer = {f.officer_id: f.location_id for f in repo.latest_per_officer()}
        assert by_officer == {
            sample_officer.user_id: fix2.location_id,
            second_officer.user_id: fix_other.location_id,
        }

    def test_list_for_alert_is_chronological(
        self, repo, make_location, sample_officer, sample_alert
    ):
        later = make_location(sample_officer, utc(2026, 10, 10, 22), alert=sample_alert)
        earlier = make_location(
            sample_officer, utc(2026, 10, 10, 21), alert=sample_alert
        )
        ids = [f.location_id for f in repo.list_for_alert(sample_alert.alert_id)]
        assert ids == [earlier.location_id, later.location_id]

    def test_officer_was_assigned(
        self, repo, sample_alert, sample_assignment, sample_officer, second_officer
    ):
        assert repo.officer_was_assigned(sample_alert, sample_officer.user_id) is True
        assert repo.officer_was_assigned(sample_alert, second_officer.user_id) is False

    def test_unlinked_older_than(self, repo, make_location, sample_officer):
        old = make_location(sample_officer, utc(2026, 1, 1))
        make_location(sample_officer, utc(2026, 10, 10))
        assert repo.list_unlinked_older_than(utc(2026, 6, 1)) == [old.location_id]


class TestGeoRules:
    def test_zero_distance(self):
        assert haversine_m(-16.85, 28.05, -16.85, 28.05) == 0

    def test_one_degree_of_latitude(self):
        assert haversine_m(0, 0, 1, 0) == pytest.approx(111_195, rel=1e-3)

    def test_symmetric(self):
        assert haversine_m(-16.8, 28.0, -16.9, 28.1) == pytest.approx(
            haversine_m(-16.9, 28.1, -16.8, 28.0)
        )

    def test_accepts_decimal_inputs(self):
        assert haversine_m(
            Decimal("0"), Decimal("0"), Decimal("1"), Decimal("0")
        ) == pytest.approx(111_195, rel=1e-3)

    def test_normal_speed_not_flagged_and_jump_flagged(self):
        now = utc(2026, 10, 18, 12)
        before = FakeFix("-16.850", "28.05", now)
        normal = FakeFix("-16.859", "28.05", now + timedelta(seconds=60))
        jump = FakeFix("-16.859", "28.05", now + timedelta(seconds=10))
        flagged, speed = evaluate_jump(before, normal, 120)
        assert flagged is False and 50 < speed < 70
        flagged, speed = evaluate_jump(before, jump, 120)
        assert flagged is True and speed > 120

    def test_first_fix_is_never_flagged(self):
        assert evaluate_jump(
            None, FakeFix("-16.85", "28.05", utc(2026, 10, 18)), 120
        ) == (False, None)

    def test_gps_accuracy_absorbs_noise(self):
        now = utc(2026, 10, 18, 12)
        before = FakeFix("-16.850", "28.05", now, accuracy="600")
        after = FakeFix("-16.859", "28.05", now + timedelta(seconds=1), accuracy="600")
        assert evaluate_jump(before, after, 120) == (False, 0.0)
