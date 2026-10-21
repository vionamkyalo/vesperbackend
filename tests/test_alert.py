import uuid
from datetime import datetime, timezone
from decimal import Decimal

import jwt
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from models.alert import Alert, AlertStatus, VerificationResult
from models.alert_assignment import AssignmentStatus

from core.config import get_settings
from core.security import create_access_token
from models.zone_light_reading import IngestionStatus
from repositories.alert import AlertRepository
from schemas.alert import (
    AlertCreate,
    AlertListQuery,
    AlertStatusUpdate,
    AlertVerificationUpdate,
    priority_for,
)
from services.alert import AlertService, point_in_geojson
import os
from models.user import User, UserRole

import models.catch_check  # noqa: F401
import models.inspection  # noqa: F401
import models.violation_report  # noqa: F401
import models.zone_baseline  # noqa: F401
import models.zone_setting_history  # noqa: F401

PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$dGVzdHNhbHQ$dGVzdGhhc2g"

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

    from fastapi.testclient import TestClient

    from database import get_db
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
        return {
            "Authorization": f"Bearer {create_access_token(user.user_id, user.role)}"
        }

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
def inactive_officer(db_session):
    user = User(
        first_name="Inactive",
        last_name="Officer",
        phone_number="+263771000099",
        email="inactive@example.org",
        password_hash=PASSWORD_HASH,
        role=UserRole.PATROL_OFFICER,
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


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
def alert_payload(sample_zone, sample_reading):
    return {
        "zone_id": str(sample_zone.zone_id),
        "reading_id": str(sample_reading.reading_id),
        "cluster_label": 1,
        "point_count": 4,
        "confidence": 0.65,
        "centroid_latitude": -16.845,
        "centroid_longitude": 28.055,
    }


class TestAlert:
    def test_create_alert_happy_path(
        self,
        db_session,
        sample_zone,
        sample_reading,
        sample_officer,
        sample_coordinator,
    ):
        assigned_at = datetime(2026, 10, 10, 18, 0, tzinfo=timezone.utc)
        reported_at = datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc)
        verified_at = datetime(2026, 10, 11, 8, 0, tzinfo=timezone.utc)
        alert = Alert(
            zone_id=sample_zone.zone_id,
            reading_id=sample_reading.reading_id,
            cluster_label=3,
            point_count=5,
            confidence=Decimal("0.6000"),
            centroid_latitude=Decimal("-16.840000"),
            centroid_longitude=Decimal("28.040000"),
            status=AlertStatus.CLOSED,
            verification_result=VerificationResult.ACTIVITY_CONFIRMED,
            verified_at=verified_at,
            officer_id=sample_officer.user_id,
            assigned_by=sample_coordinator.user_id,
            assignment_status=AssignmentStatus.REPORTED,
            assigned_at=assigned_at,
            reported_at=reported_at,
        )
        db_session.add(alert)
        db_session.commit()
        db_session.refresh(alert)

        assert alert.alert_id is not None
        assert isinstance(alert.alert_id, uuid.UUID)
        assert alert.zone_id == sample_zone.zone_id
        assert alert.reading_id == sample_reading.reading_id
        assert alert.cluster_label == 3
        assert alert.point_count == 5
        assert alert.confidence == Decimal("0.6000")
        assert alert.centroid_latitude == Decimal("-16.840000")
        assert alert.centroid_longitude == Decimal("28.040000")
        assert alert.status == AlertStatus.CLOSED
        assert alert.verification_result == VerificationResult.ACTIVITY_CONFIRMED
        assert alert.verified_at == verified_at
        assert alert.officer_id == sample_officer.user_id
        assert alert.assigned_by == sample_coordinator.user_id
        assert alert.assignment_status == AssignmentStatus.REPORTED
        assert alert.assigned_at == assigned_at
        assert alert.reported_at == reported_at
        assert alert.created_at is not None

    def test_alert_optional_fields(self, db_session, sample_zone, sample_reading):
        alert = Alert(
            zone_id=sample_zone.zone_id,
            reading_id=sample_reading.reading_id,
            cluster_label=4,
            point_count=3,
            confidence=Decimal("0.5"),
            centroid_latitude=Decimal("-16.85"),
            centroid_longitude=Decimal("28.05"),
        )
        db_session.add(alert)
        db_session.commit()
        db_session.refresh(alert)

        assert alert.officer_id is None
        assert alert.assigned_by is None
        assert alert.assignment_status is None
        assert alert.assigned_at is None
        assert alert.reported_at is None
        assert alert.verified_at is None
        assert alert.status == AlertStatus.NEW
        assert alert.verification_result == VerificationResult.PENDING
        assert alert.created_at is not None

    @pytest.mark.parametrize(
        "status",
        [
            AlertStatus.NEW,
            AlertStatus.IN_PROGRESS,
            AlertStatus.DISMISSED,
            AlertStatus.CLOSED,
        ],
    )
    def test_alert_status_values(self, db_session, sample_zone, sample_reading, status):
        alert = Alert(
            zone_id=sample_zone.zone_id,
            reading_id=sample_reading.reading_id,
            cluster_label=5,
            point_count=3,
            confidence=Decimal("0.5"),
            centroid_latitude=Decimal("-16.85"),
            centroid_longitude=Decimal("28.05"),
            status=status,
        )
        db_session.add(alert)
        db_session.commit()
        db_session.refresh(alert)

        assert alert.status == status

    @pytest.mark.parametrize(
        "result",
        [
            VerificationResult.PENDING,
            VerificationResult.ACTIVITY_CONFIRMED,
            VerificationResult.NO_ACTIVITY,
        ],
    )
    def test_alert_verification_result_values(
        self, db_session, sample_zone, sample_reading, result
    ):
        alert = Alert(
            zone_id=sample_zone.zone_id,
            reading_id=sample_reading.reading_id,
            cluster_label=6,
            point_count=3,
            confidence=Decimal("0.5"),
            centroid_latitude=Decimal("-16.85"),
            centroid_longitude=Decimal("28.05"),
            verification_result=result,
        )
        db_session.add(alert)
        db_session.commit()
        db_session.refresh(alert)

        assert alert.verification_result == result

    @pytest.mark.parametrize(
        "assignment_status",
        [
            AssignmentStatus.ASSIGNED,
            AssignmentStatus.ACKNOWLEDGED,
            AssignmentStatus.REPORTED,
            AssignmentStatus.REASSIGNED,
            AssignmentStatus.FAILED,
        ],
    )
    def test_alert_assignment_status_values(
        self, db_session, sample_zone, sample_reading, assignment_status
    ):
        alert = Alert(
            zone_id=sample_zone.zone_id,
            reading_id=sample_reading.reading_id,
            cluster_label=7,
            point_count=3,
            confidence=Decimal("0.5"),
            centroid_latitude=Decimal("-16.85"),
            centroid_longitude=Decimal("28.05"),
            assignment_status=assignment_status,
        )
        db_session.add(alert)
        db_session.commit()
        db_session.refresh(alert)

        assert alert.assignment_status == assignment_status

    def test_alert_missing_required_fields(self, db_session):
        alert = Alert()
        db_session.add(alert)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_alert_missing_zone_id(self, db_session, sample_reading):
        alert = Alert(
            reading_id=sample_reading.reading_id,
            cluster_label=8,
            point_count=3,
            confidence=Decimal("0.5"),
            centroid_latitude=Decimal("-16.85"),
            centroid_longitude=Decimal("28.05"),
        )
        db_session.add(alert)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_alert_missing_reading_id(self, db_session, sample_zone):
        alert = Alert(
            zone_id=sample_zone.zone_id,
            cluster_label=9,
            point_count=3,
            confidence=Decimal("0.5"),
            centroid_latitude=Decimal("-16.85"),
            centroid_longitude=Decimal("28.05"),
        )
        db_session.add(alert)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_alert_missing_confidence(self, db_session, sample_zone, sample_reading):
        alert = Alert(
            zone_id=sample_zone.zone_id,
            reading_id=sample_reading.reading_id,
            cluster_label=10,
            point_count=3,
            centroid_latitude=Decimal("-16.85"),
            centroid_longitude=Decimal("28.05"),
        )
        db_session.add(alert)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_alert_unique_reading_and_cluster_label(
        self, db_session, sample_zone, sample_reading
    ):
        alert1 = Alert(
            zone_id=sample_zone.zone_id,
            reading_id=sample_reading.reading_id,
            cluster_label=11,
            point_count=3,
            confidence=Decimal("0.5"),
            centroid_latitude=Decimal("-16.85"),
            centroid_longitude=Decimal("28.05"),
        )
        db_session.add(alert1)
        db_session.commit()

        alert2 = Alert(
            zone_id=sample_zone.zone_id,
            reading_id=sample_reading.reading_id,
            cluster_label=11,
            point_count=4,
            confidence=Decimal("0.6"),
            centroid_latitude=Decimal("-16.84"),
            centroid_longitude=Decimal("28.04"),
        )
        db_session.add(alert2)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_alert_zone_relationship(self, db_session, sample_zone, sample_alert):
        db_session.refresh(sample_zone)

        assert sample_alert.zone.zone_id == sample_zone.zone_id
        assert sample_alert in sample_zone.alerts

    def test_alert_reading_relationship(self, db_session, sample_reading, sample_alert):
        db_session.refresh(sample_reading)

        assert sample_alert.reading.reading_id == sample_reading.reading_id
        assert sample_alert in sample_reading.alerts

    def test_alert_officer_relationship(
        self, db_session, sample_alert, sample_assignment, sample_officer
    ):
        db_session.refresh(sample_alert)

        assert sample_alert.officer.user_id == sample_officer.user_id

    def test_alert_assigner_relationship(
        self, db_session, sample_alert, sample_assignment, sample_coordinator
    ):
        db_session.refresh(sample_alert)

        assert sample_alert.assigner.user_id == sample_coordinator.user_id

    def test_alert_assignments_relationship(
        self, db_session, sample_alert, sample_assignment
    ):
        db_session.refresh(sample_alert)

        assert sample_assignment.alert.alert_id == sample_alert.alert_id
        assert sample_assignment in sample_alert.assignments

    def test_alert_inspections_relationship(
        self, db_session, sample_alert, sample_inspection
    ):
        db_session.refresh(sample_alert)

        assert sample_inspection.alert.alert_id == sample_alert.alert_id
        assert sample_inspection in sample_alert.inspections


COORDINATOR_ONLY = [
    ("post", "/vesper/alerts", {}),
    ("get", "/vesper/alerts", None),
    ("patch", "/vesper/alerts/{id}/status", {"status": "dismissed"}),
    (
        "patch",
        "/vesper/alerts/{id}/verification",
        {"verification_result": "no_activity"},
    ),
]
OFFICER_ONLY = [("get", "/vesper/alerts/assigned/me", None)]
ANY_ROLE = [("get", "/vesper/alerts/{id}", None)]

SQUARE = {
    "type": "Polygon",
    "coordinates": [
        [[28.0, -16.9], [28.1, -16.9], [28.1, -16.8], [28.0, -16.8], [28.0, -16.9]]
    ],
}
SQUARE_WITH_HOLE = {
    "type": "Polygon",
    "coordinates": [
        SQUARE["coordinates"][0],
        [
            [28.04, -16.86],
            [28.06, -16.86],
            [28.06, -16.84],
            [28.04, -16.84],
            [28.04, -16.86],
        ],
    ],
}


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def call(client, method, path, body=None, headers=None, alert_id=None):
    url = path.replace("{id}", str(alert_id or uuid.uuid4()))
    kwargs = {"headers": headers or {}}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(url, **kwargs)


def create_body(zone, reading, **overrides) -> AlertCreate:
    body = {
        "zone_id": zone.zone_id,
        "reading_id": reading.reading_id,
        "cluster_label": 1,
        "point_count": 4,
        "confidence": "0.6500",
        "centroid_latitude": "-16.845000",
        "centroid_longitude": "28.055000",
    }
    body.update(overrides)
    return AlertCreate(**body)


def assert_http_error(excinfo, status_code, text=None):
    assert excinfo.value.status_code == status_code
    if text is not None:
        assert text in excinfo.value.detail


class TestAlertSchemas:
    def test_values_rounded_to_scale(self):
        alert = AlertCreate(
            zone_id=uuid.uuid4(),
            reading_id=uuid.uuid4(),
            cluster_label=2,
            point_count=5,
            confidence=0.123456,
            centroid_latitude=-16.8500005,
            centroid_longitude=28.05,
        )
        assert alert.confidence == Decimal("0.1235")
        assert alert.centroid_latitude == Decimal("-16.850001")

    @pytest.mark.parametrize(
        "field, value",
        [
            ("confidence", 1.01),
            ("centroid_latitude", 90.5),
            ("centroid_longitude", -181),
            ("point_count", 0),
        ],
    )
    def test_out_of_range_rejected(self, field, value):
        body = dict(
            zone_id=uuid.uuid4(),
            reading_id=uuid.uuid4(),
            cluster_label=1,
            point_count=5,
            confidence=0.5,
            centroid_latitude=-16.85,
            centroid_longitude=28.05,
        )
        body[field] = value
        with pytest.raises(ValidationError):
            AlertCreate(**body)

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            AlertStatusUpdate(status="closed", officer_id=str(uuid.uuid4()))

    def test_pending_is_not_a_final_verification(self):
        with pytest.raises(ValidationError):
            AlertVerificationUpdate(verification_result="pending")

    def test_query_defaults_and_range_check(self):
        query = AlertListQuery()
        assert (query.skip, query.limit) == (0, 50)
        with pytest.raises(ValidationError):
            AlertListQuery(created_from=utc(2026, 10, 12), created_to=utc(2026, 10, 10))

    @pytest.mark.parametrize(
        "confidence, expected",
        [("0.75", "high"), ("0.9", "high"), ("0.5", "medium"), ("0.4999", "low")],
    )
    def test_priority_bands(self, confidence, expected):
        assert priority_for(Decimal(confidence)) == expected


class TestPointInGeojson:
    @pytest.mark.parametrize(
        "lat, lon, expected",
        [
            (-16.85, 28.05, True),
            (-16.85, 28.20, False),
            (-16.95, 28.05, False),
            (-16.90, 28.05, True),
            (-16.80, 28.10, True),
        ],
    )
    def test_polygon(self, lat, lon, expected):
        assert point_in_geojson(lat, lon, SQUARE) is expected

    def test_hole_is_outside(self):
        assert point_in_geojson(-16.85, 28.05, SQUARE_WITH_HOLE) is False
        assert point_in_geojson(-16.82, 28.02, SQUARE_WITH_HOLE) is True

    def test_multipolygon(self):
        multi = {
            "type": "MultiPolygon",
            "coordinates": [
                SQUARE["coordinates"],
                [[[29.0, -17.0], [29.1, -17.0], [29.1, -16.9], [29.0, -17.0]]],
            ],
        }
        assert point_in_geojson(-16.85, 28.05, multi) is True
        assert point_in_geojson(-16.98, 29.08, multi) is True
        assert point_in_geojson(-10, 10, multi) is False

    @pytest.mark.parametrize(
        "geometry",
        [
            None,
            {},
            {"type": "Point", "coordinates": [28, -16]},
            {"type": "Polygon"},
            "x",
        ],
    )
    def test_unusable_geometry_returns_none(self, geometry):
        assert point_in_geojson(-16.85, 28.05, geometry) is None


class TestAlertRepository:
    @pytest.fixture
    def repo(self, db_session):
        return AlertRepository(db_session)

    @pytest.fixture
    def three_alerts(self, make_alert, sample_officer):
        return [
            make_alert(10, confidence="0.4000", created_at=utc(2026, 10, 10, 20)),
            make_alert(
                11,
                confidence="0.6000",
                status=AlertStatus.IN_PROGRESS,
                officer=sample_officer,
                created_at=utc(2026, 10, 11, 20),
            ),
            make_alert(
                12,
                confidence="0.9000",
                status=AlertStatus.DISMISSED,
                created_at=utc(2026, 10, 12, 20),
            ),
        ]

    def test_get_by_id(self, repo, sample_alert):
        assert repo.get_by_id(sample_alert.alert_id).alert_id == sample_alert.alert_id
        assert repo.get_by_id(uuid.uuid4()) is None

    def test_get_by_reading_and_cluster(self, repo, sample_alert):
        found = repo.get_by_reading_and_cluster(sample_alert.reading_id, 0)
        assert found.alert_id == sample_alert.alert_id
        assert repo.get_by_reading_and_cluster(sample_alert.reading_id, 99) is None

    def test_list_is_newest_first(self, repo, three_alerts):
        items, total = repo.list_filtered(AlertListQuery())
        assert total == 3
        assert [a.cluster_label for a in items] == [12, 11, 10]

    def test_filters(self, repo, three_alerts, sample_officer):
        _, total = repo.list_filtered(AlertListQuery(min_confidence="0.5"))
        assert total == 2
        _, total = repo.list_filtered(AlertListQuery(status=AlertStatus.DISMISSED))
        assert total == 1
        items, _ = repo.list_filtered(AlertListQuery(officer_id=sample_officer.user_id))
        assert [a.cluster_label for a in items] == [11]

    def test_pagination(self, repo, three_alerts):
        items, total = repo.list_filtered(AlertListQuery(skip=1, limit=1))
        assert total == 3
        assert [a.cluster_label for a in items] == [11]

    def test_list_for_officer(self, repo, three_alerts, sample_officer):
        items, total = repo.list_for_officer(sample_officer.user_id, None, 0, 50)
        assert total == 1 and items[0].cluster_label == 11


class TestAlertService:
    @pytest.fixture
    def service(self, db_session):
        return AlertService(db_session)

    def test_create_alert_success(
        self, service, sample_zone, sample_reading, sample_coordinator
    ):
        alert = service.create_alert(
            create_body(sample_zone, sample_reading), sample_coordinator
        )
        assert alert.status == AlertStatus.NEW
        assert alert.verification_result == VerificationResult.PENDING

    def test_below_confidence_threshold(
        self, service, sample_zone, sample_reading, sample_coordinator
    ):
        with pytest.raises(HTTPException) as exc:
            service.create_alert(
                create_body(sample_zone, sample_reading, confidence="0.1"),
                sample_coordinator,
            )
        assert_http_error(exc, 422, "below the zone threshold")

    def test_below_min_cluster_points(
        self, service, sample_zone, sample_reading, sample_coordinator
    ):
        with pytest.raises(HTTPException) as exc:
            service.create_alert(
                create_body(sample_zone, sample_reading, point_count=2),
                sample_coordinator,
            )
        assert_http_error(exc, 422, "zone minimum")

    def test_centroid_outside_zone(
        self, service, sample_zone, sample_reading, sample_coordinator
    ):
        with pytest.raises(HTTPException) as exc:
            service.create_alert(
                create_body(
                    sample_zone,
                    sample_reading,
                    centroid_latitude="-17.5",
                    centroid_longitude="28.5",
                ),
                sample_coordinator,
            )
        assert_http_error(exc, 422, "outside the zone boundary")

    def test_inactive_zone(
        self, service, db_session, sample_zone, sample_reading, sample_coordinator
    ):
        sample_zone.is_active = False
        db_session.commit()
        with pytest.raises(HTTPException) as exc:
            service.create_alert(
                create_body(sample_zone, sample_reading), sample_coordinator
            )
        assert_http_error(exc, 409, "not active")

    def test_reading_not_received(
        self, service, db_session, sample_zone, sample_reading, sample_coordinator
    ):
        sample_reading.ingestion_status = IngestionStatus.INGESTION_ERROR
        db_session.commit()
        with pytest.raises(HTTPException) as exc:
            service.create_alert(
                create_body(sample_zone, sample_reading), sample_coordinator
            )
        assert_http_error(exc, 409, "Insufficient data")

    def test_unknown_zone_and_reading(
        self, service, sample_zone, sample_reading, sample_coordinator
    ):
        with pytest.raises(HTTPException) as exc:
            service.create_alert(
                create_body(sample_zone, sample_reading, zone_id=uuid.uuid4()),
                sample_coordinator,
            )
        assert_http_error(exc, 404, "Zone")
        with pytest.raises(HTTPException) as exc:
            service.create_alert(
                create_body(sample_zone, sample_reading, reading_id=uuid.uuid4()),
                sample_coordinator,
            )
        assert_http_error(exc, 404, "Reading")

    def test_duplicate_cluster(
        self, service, sample_zone, sample_reading, sample_coordinator
    ):
        service.create_alert(
            create_body(sample_zone, sample_reading), sample_coordinator
        )
        with pytest.raises(HTTPException) as exc:
            service.create_alert(
                create_body(sample_zone, sample_reading), sample_coordinator
            )
        assert_http_error(exc, 409, "already exists")

    def test_valid_status_flow_with_verification(
        self, service, make_alert, sample_coordinator
    ):
        alert = make_alert(30)
        service.update_alert_status(
            alert.alert_id,
            AlertStatusUpdate(status=AlertStatus.IN_PROGRESS),
            sample_coordinator,
        )
        service.record_verification(
            alert.alert_id,
            AlertVerificationUpdate(verification_result="activity_confirmed"),
            sample_coordinator,
        )
        closed = service.update_alert_status(
            alert.alert_id,
            AlertStatusUpdate(status=AlertStatus.CLOSED),
            sample_coordinator,
        )
        assert closed.status == AlertStatus.CLOSED
        assert closed.verified_at is not None

    def test_invalid_transition(self, service, make_alert, sample_coordinator):
        alert = make_alert(31)
        with pytest.raises(HTTPException) as exc:
            service.update_alert_status(
                alert.alert_id,
                AlertStatusUpdate(status=AlertStatus.CLOSED),
                sample_coordinator,
            )
        assert_http_error(exc, 409, "Cannot change alert status")

    def test_cannot_close_without_verification(
        self, service, make_alert, sample_coordinator
    ):
        alert = make_alert(32, status=AlertStatus.IN_PROGRESS)
        with pytest.raises(HTTPException) as exc:
            service.update_alert_status(
                alert.alert_id,
                AlertStatusUpdate(status=AlertStatus.CLOSED),
                sample_coordinator,
            )
        assert_http_error(exc, 409, "verification result")

    def test_same_status_is_idempotent(self, service, make_alert, sample_coordinator):
        alert = make_alert(33)
        result = service.update_alert_status(
            alert.alert_id,
            AlertStatusUpdate(status=AlertStatus.NEW),
            sample_coordinator,
        )
        assert result.status == AlertStatus.NEW

    def test_verify_requires_in_progress(self, service, make_alert, sample_coordinator):
        alert = make_alert(34)
        with pytest.raises(HTTPException) as exc:
            service.record_verification(
                alert.alert_id,
                AlertVerificationUpdate(verification_result="no_activity"),
                sample_coordinator,
            )
        assert_http_error(exc, 409, "in progress")

    def test_officer_cannot_read_unassigned_alert(
        self, service, sample_alert, sample_officer
    ):
        with pytest.raises(HTTPException) as exc:
            service.get_alert(sample_alert.alert_id, sample_officer)
        assert_http_error(exc, 403)

    def test_missing_alert_is_404(self, service, sample_coordinator):
        with pytest.raises(HTTPException) as exc:
            service.get_alert(uuid.uuid4(), sample_coordinator)
        assert_http_error(exc, 404)


class TestAlertAccessControl:
    @pytest.mark.parametrize(
        "method, path, body", COORDINATOR_ONLY + OFFICER_ONLY + ANY_ROLE
    )
    def test_no_token_is_401(self, client, method, path, body):
        response = call(client, method, path, body)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_expired_token_is_401(self, client, sample_coordinator):
        token = create_access_token(sample_coordinator.user_id, expires_minutes=-1)
        assert (
            client.get(
                "/vesper/alerts", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 401
        )

    def test_tampered_token_is_401(self, client, sample_coordinator):
        settings = get_settings()
        bad = jwt.encode(
            {
                "sub": str(sample_coordinator.user_id),
                "type": "access",
                "exp": 9999999999,
            },
            "x" * 40,
            algorithm=settings.JWT_ALGORITHM,
        )
        assert (
            client.get(
                "/vesper/alerts", headers={"Authorization": f"Bearer {bad}"}
            ).status_code
            == 401
        )

    def test_deactivated_account_is_403(self, client, headers_for, inactive_officer):
        response = client.get(
            "/vesper/alerts/assigned/me", headers=headers_for(inactive_officer)
        )
        assert response.status_code == 403

    @pytest.mark.parametrize("method, path, body", COORDINATOR_ONLY)
    def test_officer_forbidden_on_coordinator_routes(
        self, client, officer_headers, method, path, body
    ):
        assert call(client, method, path, body, officer_headers).status_code == 403

    @pytest.mark.parametrize("method, path, body", OFFICER_ONLY)
    def test_coordinator_forbidden_on_officer_routes(
        self, client, coordinator_headers, method, path, body
    ):
        assert call(client, method, path, body, coordinator_headers).status_code == 403


class TestAlertEndpoints:
    def test_create_alert(self, client, coordinator_headers, alert_payload):
        response = client.post(
            "/vesper/alerts", json=alert_payload, headers=coordinator_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert uuid.UUID(data["alert_id"])
        assert data["status"] == "new"
        assert data["priority"] == "medium"
        assert data["confidence"] == 0.65

    def test_duplicate_create_is_409(self, client, coordinator_headers, alert_payload):
        assert (
            client.post(
                "/vesper/alerts", json=alert_payload, headers=coordinator_headers
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/vesper/alerts", json=alert_payload, headers=coordinator_headers
            ).status_code
            == 409
        )

    def test_invalid_body_is_422(self, client, coordinator_headers, alert_payload):
        alert_payload["confidence"] = 2
        assert (
            client.post(
                "/vesper/alerts", json=alert_payload, headers=coordinator_headers
            ).status_code
            == 422
        )

    def test_list_alerts_and_page_limit(
        self, client, coordinator_headers, sample_alert
    ):
        body = client.get("/vesper/alerts", headers=coordinator_headers).json()
        assert body["total"] == 1
        assert (
            client.get(
                "/vesper/alerts?limit=101", headers=coordinator_headers
            ).status_code
            == 422
        )

    def test_get_alert(self, client, coordinator_headers, sample_alert):
        response = client.get(
            f"/vesper/alerts/{sample_alert.alert_id}", headers=coordinator_headers
        )
        assert response.status_code == 200
        assert response.json()["alert_id"] == str(sample_alert.alert_id)

    def test_officer_sees_only_assigned_alert(
        self,
        client,
        officer_headers,
        second_officer_headers,
        sample_alert,
        sample_assignment,
    ):
        url = f"/vesper/alerts/{sample_alert.alert_id}"
        assert client.get(url, headers=officer_headers).status_code == 200
        assert client.get(url, headers=second_officer_headers).status_code == 403

    def test_dismiss_alert(self, client, coordinator_headers, sample_alert):
        response = client.patch(
            f"/vesper/alerts/{sample_alert.alert_id}/status",
            json={"status": "dismissed"},
            headers=coordinator_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "dismissed"

    def test_unknown_alert_is_404(self, client, coordinator_headers):
        assert (
            client.get(
                f"/vesper/alerts/{uuid.uuid4()}", headers=coordinator_headers
            ).status_code
            == 404
        )

    def test_alert_lifecycle_e2e(
        self,
        client,
        db_session,
        coordinator_headers,
        officer_headers,
        alert_payload,
        sample_officer,
        sample_coordinator,
    ):
        alert_id = client.post(
            "/vesper/alerts", json=alert_payload, headers=coordinator_headers
        ).json()["alert_id"]

        alert = db_session.get(Alert, uuid.UUID(alert_id))
        alert.officer_id = sample_officer.user_id
        alert.assigned_by = sample_coordinator.user_id
        db_session.commit()

        mine = client.get("/vesper/alerts/assigned/me", headers=officer_headers).json()
        assert [a["alert_id"] for a in mine["items"]] == [alert_id]

        for path, body in [
            ("status", {"status": "in_progress"}),
            ("verification", {"verification_result": "activity_confirmed"}),
            ("status", {"status": "closed"}),
        ]:
            response = client.patch(
                f"/vesper/alerts/{alert_id}/{path}",
                json=body,
                headers=coordinator_headers,
            )
            assert response.status_code == 200, response.text
        assert response.json()["status"] == "closed"
        assert response.json()["verification_result"] == "activity_confirmed"
