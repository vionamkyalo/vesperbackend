import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from models.inspection import Inspection, InspectionOutcome, InspectionType
from datetime import timedelta
from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy.orm import Session

import core.security as security
from models.user import User, UserRole
from fastapi.testclient import TestClient
from pydantic import ValidationError
from database import get_db
from models.alert_assignment import AssignmentStatus
from models.zone import Zone, ZoneType
from repositories.inspection import inspection_repository
from schemas.inspection import InspectionCreate, InspectionRead
from services.inspection import inspection_service


class TestInspection:
    def test_create_inspection_happy_path(
        self, db_session, sample_officer, sample_zone, sample_alert
    ):
        inspection_id = uuid.uuid4()
        inspected_at = datetime(2026, 10, 10, 22, 30, tzinfo=timezone.utc)
        inspection = Inspection(
            inspection_id=inspection_id,
            alert_id=sample_alert.alert_id,
            officer_id=sample_officer.user_id,
            zone_id=sample_zone.zone_id,
            inspection_type=InspectionType.SITE,
            outcome=InspectionOutcome.ACTIVITY_CONSISTENT,
            rigs_observed=4,
            latitude=Decimal("-16.850100"),
            longitude=Decimal("28.050200"),
            notes="Four rigs with lights on",
            inspected_at=inspected_at,
        )
        db_session.add(inspection)
        db_session.commit()
        db_session.refresh(inspection)

        assert inspection.inspection_id == inspection_id
        assert isinstance(inspection.inspection_id, uuid.UUID)
        assert inspection.alert_id == sample_alert.alert_id
        assert inspection.officer_id == sample_officer.user_id
        assert inspection.zone_id == sample_zone.zone_id
        assert inspection.inspection_type == InspectionType.SITE
        assert inspection.outcome == InspectionOutcome.ACTIVITY_CONSISTENT
        assert inspection.rigs_observed == 4
        assert inspection.latitude == Decimal("-16.850100")
        assert inspection.longitude == Decimal("28.050200")
        assert inspection.notes == "Four rigs with lights on"
        assert inspection.inspected_at == inspected_at
        assert inspection.synced_at is not None

    def test_inspection_optional_fields(self, db_session, sample_officer, sample_zone):
        inspection = Inspection(
            inspection_id=uuid.uuid4(),
            officer_id=sample_officer.user_id,
            zone_id=sample_zone.zone_id,
            inspection_type=InspectionType.ZONE,
            outcome=InspectionOutcome.NO_ACTIVITY,
            rigs_observed=0,
            latitude=Decimal("-16.85"),
            longitude=Decimal("28.05"),
            inspected_at=datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc),
        )
        db_session.add(inspection)
        db_session.commit()
        db_session.refresh(inspection)

        assert inspection.alert_id is None
        assert inspection.notes is None
        assert inspection.synced_at is not None

    @pytest.mark.parametrize(
        "inspection_type",
        [
            InspectionType.SITE,
            InspectionType.LANDING_SITE,
            InspectionType.ZONE,
        ],
    )
    def test_inspection_type_values(
        self, db_session, sample_officer, sample_zone, inspection_type
    ):
        inspection = Inspection(
            inspection_id=uuid.uuid4(),
            officer_id=sample_officer.user_id,
            zone_id=sample_zone.zone_id,
            inspection_type=inspection_type,
            outcome=InspectionOutcome.NO_ACTIVITY,
            rigs_observed=0,
            latitude=Decimal("-16.85"),
            longitude=Decimal("28.05"),
            inspected_at=datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc),
        )
        db_session.add(inspection)
        db_session.commit()
        db_session.refresh(inspection)

        assert inspection.inspection_type == inspection_type

    @pytest.mark.parametrize(
        "outcome",
        [
            InspectionOutcome.ACTIVITY_CONSISTENT,
            InspectionOutcome.NO_ACTIVITY,
            InspectionOutcome.NO_FISHING_LIGHT,
            InspectionOutcome.UNABLE_TO_VERIFY,
        ],
    )
    def test_inspection_outcome_values(
        self, db_session, sample_officer, sample_zone, outcome
    ):
        inspection = Inspection(
            inspection_id=uuid.uuid4(),
            officer_id=sample_officer.user_id,
            zone_id=sample_zone.zone_id,
            inspection_type=InspectionType.ZONE,
            outcome=outcome,
            rigs_observed=0,
            latitude=Decimal("-16.85"),
            longitude=Decimal("28.05"),
            inspected_at=datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc),
        )
        db_session.add(inspection)
        db_session.commit()
        db_session.refresh(inspection)

        assert inspection.outcome == outcome

    def test_inspection_missing_required_fields(self, db_session):
        inspection = Inspection(inspection_id=uuid.uuid4())
        db_session.add(inspection)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_inspection_missing_officer_id(self, db_session, sample_zone):
        inspection = Inspection(
            inspection_id=uuid.uuid4(),
            zone_id=sample_zone.zone_id,
            inspection_type=InspectionType.ZONE,
            outcome=InspectionOutcome.NO_ACTIVITY,
            rigs_observed=0,
            latitude=Decimal("-16.85"),
            longitude=Decimal("28.05"),
            inspected_at=datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc),
        )
        db_session.add(inspection)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_inspection_missing_zone_id(self, db_session, sample_officer):
        inspection = Inspection(
            inspection_id=uuid.uuid4(),
            officer_id=sample_officer.user_id,
            inspection_type=InspectionType.ZONE,
            outcome=InspectionOutcome.NO_ACTIVITY,
            rigs_observed=0,
            latitude=Decimal("-16.85"),
            longitude=Decimal("28.05"),
            inspected_at=datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc),
        )
        db_session.add(inspection)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_inspection_alert_relationship(
        self, db_session, sample_alert, sample_inspection
    ):
        db_session.refresh(sample_alert)

        assert sample_inspection.alert.alert_id == sample_alert.alert_id
        assert sample_inspection in sample_alert.inspections

    def test_inspection_officer_relationship(
        self, db_session, sample_officer, sample_inspection
    ):
        db_session.refresh(sample_officer)

        assert sample_inspection.officer.user_id == sample_officer.user_id
        assert sample_inspection in sample_officer.inspections

    def test_inspection_zone_relationship(
        self, db_session, sample_zone, sample_inspection
    ):
        db_session.refresh(sample_zone)

        assert sample_inspection.zone.zone_id == sample_zone.zone_id
        assert sample_inspection in sample_zone.inspections

    def test_inspection_violation_reports_relationship(
        self, db_session, sample_inspection, sample_violation
    ):
        db_session.refresh(sample_inspection)

        assert (
            sample_violation.inspection.inspection_id == sample_inspection.inspection_id
        )
        assert sample_violation in sample_inspection.violation_reports

    def test_inspection_catch_checks_relationship(
        self, db_session, landing_inspection, sample_catch_check
    ):
        db_session.refresh(landing_inspection)

        assert (
            sample_catch_check.inspection.inspection_id
            == landing_inspection.inspection_id
        )
        assert sample_catch_check in landing_inspection.catch_checks


API = "/vesper/inspections"


def valid_body(zone_id=None, alert_id=None, **changes):
    body = {
        "alert_id": str(alert_id) if alert_id else None,
        "zone_id": str(zone_id or uuid.uuid4()),
        "inspection_type": "site",
        "outcome": "activity_consistent",
        "rigs_observed": 4,
        "latitude": "-16.8501",
        "longitude": "28.0502",
        "notes": "Four rigs with lights on",
        "inspected_at": (
            datetime.now(timezone.utc) - timedelta(minutes=30)
        ).isoformat(),
    }
    body.update(changes)
    return body


def stand_in_role_check(*roles):
    def checker(
        x_test_user: str | None = Header(default=None), db: Session = Depends(get_db)
    ):
        if x_test_user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        user = db.get(User, uuid.UUID(x_test_user))
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to perform this action",
            )
        return user

    return checker


REAL_SECURITY = hasattr(security, "create_access_token") and hasattr(
    security, "require_any_user"
)

STAND_INS = {
    "require_officer": stand_in_role_check(UserRole.PATROL_OFFICER),
    "require_coordinator": stand_in_role_check(UserRole.PATROL_COORDINATOR),
    "require_any_user": stand_in_role_check(
        UserRole.PATROL_COORDINATOR, UserRole.PATROL_OFFICER
    ),
}

if not REAL_SECURITY:
    for name, checker in STAND_INS.items():
        setattr(security, name, checker)


def auth_headers(user):
    if REAL_SECURITY:
        token = security.create_access_token(user.user_id, user.role.value)
        return {"Authorization": f"Bearer {token}"}
    return {"X-Test-User": str(user.user_id)}


@pytest.fixture
def client(db_session):
    from routers import inspection as inspection_router

    app = FastAPI()
    if REAL_SECURITY:
        security.register_error_handlers(app)
    app.include_router(inspection_router.router, prefix="/vesper")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    if not REAL_SECURITY:
        for name, checker in STAND_INS.items():
            if hasattr(inspection_router, name):
                app.dependency_overrides[getattr(inspection_router, name)] = checker
    with TestClient(app) as test_client:
        yield test_client


class TestInspectionRepository:
    def test_create_inspection(self, db_session, sample_officer, sample_zone):
        inspection = Inspection(
            inspection_id=uuid.uuid4(),
            officer_id=sample_officer.user_id,
            zone_id=sample_zone.zone_id,
            inspection_type=InspectionType.ZONE,
            outcome=InspectionOutcome.NO_ACTIVITY,
            rigs_observed=0,
            latitude=Decimal("-16.850000"),
            longitude=Decimal("28.050000"),
            inspected_at=datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc),
        )

        saved = inspection_repository.create(db_session, inspection)

        assert saved.synced_at is not None
        assert (
            inspection_repository.get(db_session, saved.inspection_id).inspection_id
            == saved.inspection_id
        )

    def test_get_inspection(self, db_session, landing_inspection):
        found = inspection_repository.get(db_session, landing_inspection.inspection_id)

        assert found.inspection_id == landing_inspection.inspection_id

    def test_get_inspection_not_found(self, db_session):
        assert inspection_repository.get(db_session, uuid.uuid4()) is None

    def test_get_all_inspections(
        self, db_session, sample_inspection, landing_inspection
    ):
        ids = {
            inspection.inspection_id
            for inspection in inspection_repository.get_all(db_session)
        }

        assert ids == {
            sample_inspection.inspection_id,
            landing_inspection.inspection_id,
        }

    def test_get_all_inspections_empty(self, db_session):
        assert inspection_repository.get_all(db_session) == []

    def test_update_inspection(self, db_session, landing_inspection):
        landing_inspection.notes = "Updated after review"

        inspection_repository.update(db_session, landing_inspection)
        db_session.expire_all()

        assert (
            inspection_repository.get(
                db_session, landing_inspection.inspection_id
            ).notes
            == "Updated after review"
        )

    def test_create_inspection_saves_all_fields(
        self, db_session, sample_officer, sample_zone, sample_alert
    ):
        inspection_id = uuid.uuid4()
        inspected_at = datetime(2026, 10, 10, 23, 15, tzinfo=timezone.utc)
        inspection = Inspection(
            inspection_id=inspection_id,
            alert_id=sample_alert.alert_id,
            officer_id=sample_officer.user_id,
            zone_id=sample_zone.zone_id,
            inspection_type=InspectionType.SITE,
            outcome=InspectionOutcome.UNABLE_TO_VERIFY,
            rigs_observed=7,
            latitude=Decimal("-16.851234"),
            longitude=Decimal("28.051234"),
            notes="Rough water, could not get close",
            inspected_at=inspected_at,
        )

        inspection_repository.create(db_session, inspection)
        db_session.expire_all()
        found = inspection_repository.get(db_session, inspection_id)

        assert found.alert_id == sample_alert.alert_id
        assert found.officer_id == sample_officer.user_id
        assert found.zone_id == sample_zone.zone_id
        assert found.inspection_type == InspectionType.SITE
        assert found.outcome == InspectionOutcome.UNABLE_TO_VERIFY
        assert found.rigs_observed == 7
        assert found.latitude == Decimal("-16.851234")
        assert found.longitude == Decimal("28.051234")
        assert found.notes == "Rough water, could not get close"
        assert found.inspected_at == inspected_at

    def test_create_inspection_duplicate_id_rejected(
        self, db_session, sample_officer, sample_zone, landing_inspection
    ):
        duplicate_id = landing_inspection.inspection_id
        db_session.expunge_all()
        duplicate = Inspection(
            inspection_id=duplicate_id,
            officer_id=sample_officer.user_id,
            zone_id=sample_zone.zone_id,
            inspection_type=InspectionType.ZONE,
            outcome=InspectionOutcome.NO_ACTIVITY,
            rigs_observed=0,
            latitude=Decimal("-16.850000"),
            longitude=Decimal("28.050000"),
            inspected_at=datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc),
        )

        with pytest.raises(IntegrityError):
            inspection_repository.create(db_session, duplicate)

        db_session.rollback()

    def test_create_inspection_missing_required_fields_rejected(self, db_session):
        with pytest.raises(IntegrityError):
            inspection_repository.create(
                db_session, Inspection(inspection_id=uuid.uuid4())
            )

        db_session.rollback()

    def test_get_all_returns_every_officers_inspections(
        self,
        db_session,
        sample_officer,
        second_officer,
        sample_zone,
        landing_inspection,
    ):
        other = Inspection(
            inspection_id=uuid.uuid4(),
            officer_id=second_officer.user_id,
            zone_id=sample_zone.zone_id,
            inspection_type=InspectionType.ZONE,
            outcome=InspectionOutcome.NO_ACTIVITY,
            rigs_observed=0,
            latitude=Decimal("-16.850000"),
            longitude=Decimal("28.050000"),
            inspected_at=datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc),
        )
        inspection_repository.create(db_session, other)

        officers = {
            inspection.officer_id
            for inspection in inspection_repository.get_all(db_session)
        }

        assert officers == {sample_officer.user_id, second_officer.user_id}

    def test_update_inspection_several_fields(self, db_session, landing_inspection):
        landing_inspection.outcome = InspectionOutcome.NO_FISHING_LIGHT
        landing_inspection.rigs_observed = 0
        landing_inspection.notes = None

        inspection_repository.update(db_session, landing_inspection)
        db_session.expire_all()
        found = inspection_repository.get(db_session, landing_inspection.inspection_id)

        assert found.outcome == InspectionOutcome.NO_FISHING_LIGHT
        assert found.rigs_observed == 0
        assert found.notes is None

    # ---- positive cases
    @pytest.mark.parametrize("inspection_type", list(InspectionType))
    def test_repository_create_each_inspection_type(
        self, db_session, sample_officer, sample_zone, inspection_type
    ):
        inspection = make_record(
            sample_officer, sample_zone, inspection_type=inspection_type
        )

        inspection_repository.create(db_session, inspection)
        db_session.expire_all()

        assert (
            inspection_repository.get(
                db_session, inspection.inspection_id
            ).inspection_type
            == inspection_type
        )

    @pytest.mark.parametrize("outcome", list(InspectionOutcome))
    def test_repository_create_each_outcome(
        self, db_session, sample_officer, sample_zone, outcome
    ):
        inspection = make_record(sample_officer, sample_zone, outcome=outcome)

        inspection_repository.create(db_session, inspection)
        db_session.expire_all()

        assert (
            inspection_repository.get(db_session, inspection.inspection_id).outcome
            == outcome
        )

    @pytest.mark.parametrize("count", [1, 3, 5])
    def test_repository_get_all_counts(
        self, db_session, sample_officer, sample_zone, count
    ):
        for _ in range(count):
            inspection_repository.create(
                db_session, make_record(sample_officer, sample_zone)
            )

        assert len(inspection_repository.get_all(db_session)) == count

    def test_repository_create_returns_saved_object(
        self, db_session, sample_officer, sample_zone
    ):
        inspection = make_record(sample_officer, sample_zone)

        saved = inspection_repository.create(db_session, inspection)

        assert saved is inspection
        assert saved.synced_at is not None

    def test_repository_update_returns_saved_object(
        self, db_session, landing_inspection
    ):
        landing_inspection.rigs_observed = 9

        saved = inspection_repository.update(db_session, landing_inspection)

        assert saved is landing_inspection
        assert saved.rigs_observed == 9

    # ---- negative cases
    @pytest.mark.parametrize("missing_link", ["zone_id", "officer_id", "alert_id"])
    def test_repository_create_unknown_link_rejected(
        self, db_session, sample_officer, sample_zone, missing_link
    ):
        inspection = make_record(sample_officer, sample_zone)
        setattr(inspection, missing_link, uuid.uuid4())

        with pytest.raises(IntegrityError):
            inspection_repository.create(db_session, inspection)

        db_session.rollback()

    @pytest.mark.parametrize(
        "field",
        [
            "officer_id",
            "zone_id",
            "inspection_type",
            "outcome",
            "rigs_observed",
            "latitude",
            "longitude",
        ],
    )
    def test_repository_create_each_required_field_missing(
        self, db_session, sample_officer, sample_zone, field
    ):
        inspection = make_record(sample_officer, sample_zone)
        setattr(inspection, field, None)

        with pytest.raises(IntegrityError):
            inspection_repository.create(db_session, inspection)

        db_session.rollback()


class TestInspectionSchema:
    def test_inspection_create_happy_path(self):
        data = InspectionCreate(**valid_body())

        assert data.inspection_type == InspectionType.SITE
        assert data.outcome == InspectionOutcome.ACTIVITY_CONSISTENT
        assert data.latitude == Decimal("-16.850100")
        assert data.alert_id is None

    def test_inspection_create_converts_time_to_utc(self):
        data = InspectionCreate(**valid_body(inspected_at="2026-10-10T23:00:00+02:00"))

        assert data.inspected_at == datetime(2026, 10, 10, 21, 0, tzinfo=timezone.utc)

    @pytest.mark.parametrize("inspection_type", ["site", "landing_site", "zone"])
    def test_inspection_create_type_values(self, inspection_type):
        assert InspectionCreate(
            **valid_body(inspection_type=inspection_type)
        ).inspection_type == InspectionType(inspection_type)

    @pytest.mark.parametrize(
        "outcome",
        ["activity_consistent", "no_activity", "no_fishing_light", "unable_to_verify"],
    )
    def test_inspection_create_outcome_values(self, outcome):
        assert InspectionCreate(
            **valid_body(outcome=outcome)
        ).outcome == InspectionOutcome(outcome)

    @pytest.mark.parametrize(
        "field, value",
        [
            ("rigs_observed", -1),
            ("rigs_observed", 1001),
            ("latitude", "91"),
            ("longitude", "-181"),
            ("inspection_type", "boat"),
            ("outcome", "illegal"),
            ("notes", "x" * 2001),
            ("inspected_at", "2026-10-10T22:00:00"),
            ("officer_id", str(uuid.uuid4())),
        ],
    )
    def test_inspection_create_rejects_bad_values(self, field, value):
        with pytest.raises(ValidationError):
            InspectionCreate(**valid_body(**{field: value}))

    @pytest.mark.parametrize(
        "field",
        [
            "zone_id",
            "inspection_type",
            "outcome",
            "rigs_observed",
            "latitude",
            "longitude",
        ],
    )
    def test_inspection_create_missing_required_field(self, field):
        body = valid_body()
        del body[field]

        with pytest.raises(ValidationError):
            InspectionCreate(**body)

    def test_inspection_read_json_uses_numbers(self, sample_inspection):
        data = InspectionRead.model_validate(sample_inspection).model_dump(mode="json")

        assert data["latitude"] == -16.8501
        assert data["longitude"] == 28.0502
        assert data["inspection_type"] == "site"
        assert data["outcome"] == "activity_consistent"

    def test_inspection_create_optional_fields(self):
        body = valid_body()
        del body["alert_id"]
        del body["notes"]

        data = InspectionCreate(**body)

        assert data.alert_id is None
        assert data.notes is None

    @pytest.mark.parametrize(
        "field, value",
        [
            ("rigs_observed", 0),
            ("rigs_observed", 1000),
            ("latitude", "-90"),
            ("latitude", "90"),
            ("longitude", "-180"),
            ("longitude", "180"),
        ],
    )
    def test_inspection_create_accepts_edge_values(self, field, value):
        data = InspectionCreate(**valid_body(**{field: value}))

        assert getattr(data, field) is not None

    def test_inspection_create_strips_notes(self):
        data = InspectionCreate(**valid_body(notes="   Two rigs near the island   "))

        assert data.notes == "Two rigs near the island"

    def test_inspection_create_with_alert_id(self):
        alert_id = uuid.uuid4()

        data = InspectionCreate(**valid_body(alert_id=alert_id))

        assert data.alert_id == alert_id

    def test_inspection_read_without_alert(self, landing_inspection):
        data = InspectionRead.model_validate(landing_inspection).model_dump(mode="json")

        assert data["alert_id"] is None
        assert data["inspection_type"] == "landing_site"
        assert data["officer_id"] == str(landing_inspection.officer_id)
        assert data["synced_at"] is not None

    # ---- boundary case
    @pytest.mark.parametrize("rigs", [0, 1, 500, 999, 1000])
    def test_schema_rigs_inside_limits(self, rigs):
        assert InspectionCreate(**valid_body(rigs_observed=rigs)).rigs_observed == rigs

    @pytest.mark.parametrize(
        "field, value",
        [
            ("latitude", "-90.0000001"),
            ("latitude", "90.0000001"),
            ("longitude", "-180.0000001"),
            ("longitude", "180.0000001"),
            ("rigs_observed", 1001),
            ("rigs_observed", -1),
        ],
    )
    def test_schema_just_outside_limits(self, field, value):
        with pytest.raises(ValidationError):
            InspectionCreate(**valid_body(**{field: value}))

    # ---- edge case
    @pytest.mark.parametrize(
        "value, expected",
        [
            ("-16.1234567", "-16.123457"),
            ("28.1", "28.100000"),
            ("0", "0.000000"),
            ("-16.123456", "-16.123456"),
        ],
    )
    def test_schema_latitude_rounded_to_six_places(self, value, expected):
        assert str(InspectionCreate(**valid_body(latitude=value)).latitude) == expected

    def test_schema_notes_exactly_at_limit(self):
        assert len(InspectionCreate(**valid_body(notes="x" * 2000)).notes) == 2000

    def test_schema_notes_empty_string(self):
        assert InspectionCreate(**valid_body(notes="")).notes == ""

    @pytest.mark.parametrize(
        "value",
        [
            "2026-10-10T21:00:00Z",
            "2026-10-10T21:00:00+00:00",
            "2026-10-11T00:00:00+03:00",
            "2026-10-10T16:00:00-05:00",
        ],
    )
    def test_schema_time_zones_converted_to_utc(self, value):
        data = InspectionCreate(**valid_body(inspected_at=value))

        assert data.inspected_at == datetime(2026, 10, 10, 21, 0, tzinfo=timezone.utc)
        assert data.inspected_at.utcoffset() == timedelta(0)

    # ---- negative case
    @pytest.mark.parametrize(
        "field, value",
        [
            ("inspected_at", "yesterday"),
            ("inspected_at", ""),
            ("zone_id", "zone-1"),
            ("alert_id", "abc"),
            ("inspection_type", "SITE"),
            ("inspection_type", ""),
            ("outcome", "No_Activity"),
            ("outcome", ""),
            ("rigs_observed", "four"),
            ("rigs_observed", 4.5),
            ("latitude", "north"),
            ("longitude", None),
        ],
    )
    def test_schema_bad_formats_rejected(self, field, value):
        with pytest.raises(ValidationError):
            InspectionCreate(**valid_body(**{field: value}))

    @pytest.mark.parametrize(
        "field, value",
        [
            ("inspection_id", str(uuid.uuid4())),
            ("officer_id", str(uuid.uuid4())),
            ("synced_at", "2026-10-10T21:00:00Z"),
            ("status", "reported"),
        ],
    )
    def test_schema_server_fields_rejected(self, field, value):
        with pytest.raises(ValidationError):
            InspectionCreate(**valid_body(**{field: value}))

    def test_schema_rigs_as_text_number(self):
        assert InspectionCreate(**valid_body(rigs_observed="4")).rigs_observed == 4

    def test_schema_alert_id_explicit_null(self):
        assert InspectionCreate(**valid_body(alert_id=None)).alert_id is None

    def test_schema_read_has_exact_fields(self, landing_inspection):
        data = InspectionRead.model_validate(landing_inspection).model_dump(mode="json")

        assert set(data) == {
            "inspection_id",
            "alert_id",
            "officer_id",
            "zone_id",
            "inspection_type",
            "outcome",
            "rigs_observed",
            "latitude",
            "longitude",
            "notes",
            "inspected_at",
            "synced_at",
        }

    def test_schema_read_coordinates_are_numbers(self, landing_inspection):
        data = InspectionRead.model_validate(landing_inspection).model_dump(mode="json")

        assert isinstance(data["latitude"], float)
        assert isinstance(data["longitude"], float)

    def test_schema_read_with_alert(self, sample_inspection, sample_alert):
        data = InspectionRead.model_validate(sample_inspection).model_dump(mode="json")

        assert data["alert_id"] == str(sample_alert.alert_id)

    def test_schema_read_without_notes(self, db_session, sample_officer, sample_zone):
        inspection = inspection_repository.create(
            db_session, make_record(sample_officer, sample_zone, notes=None)
        )

        assert InspectionRead.model_validate(inspection).notes is None


class TestInspectionService:
    def test_create_inspection_without_alert(
        self, db_session, sample_officer, sample_zone
    ):
        body = InspectionCreate(
            **valid_body(sample_zone.zone_id, inspection_type="zone")
        )

        inspection = inspection_service.create_inspection(
            db_session, sample_officer, body
        )

        assert isinstance(inspection.inspection_id, uuid.UUID)
        assert inspection.officer_id == sample_officer.user_id
        assert inspection.alert_id is None

    def test_create_inspection_for_assigned_alert(
        self, db_session, sample_officer, sample_zone, sample_alert, sample_assignment
    ):
        body = InspectionCreate(
            **valid_body(sample_zone.zone_id, sample_alert.alert_id)
        )

        inspection = inspection_service.create_inspection(
            db_session, sample_officer, body
        )
        db_session.refresh(sample_alert)
        db_session.refresh(sample_assignment)

        assert inspection.alert_id == sample_alert.alert_id
        assert sample_alert.assignment_status == AssignmentStatus.REPORTED
        assert sample_alert.reported_at is not None
        assert sample_assignment.status == AssignmentStatus.REPORTED
        assert sample_assignment.reported_at is not None

    def test_create_inspection_twice_creates_two_records(
        self, db_session, sample_officer, sample_zone
    ):
        body = InspectionCreate(**valid_body(sample_zone.zone_id))

        first = inspection_service.create_inspection(db_session, sample_officer, body)
        second = inspection_service.create_inspection(db_session, sample_officer, body)

        assert first.inspection_id != second.inspection_id
        assert len(inspection_service.list_inspections(db_session, sample_officer)) == 2

    def test_create_inspection_unknown_zone(self, db_session, sample_officer):
        with pytest.raises(HTTPException) as error:
            inspection_service.create_inspection(
                db_session, sample_officer, InspectionCreate(**valid_body())
            )

        assert error.value.status_code == 404

    def test_create_inspection_alert_not_assigned(
        self, db_session, second_officer, sample_zone, sample_alert
    ):
        body = InspectionCreate(
            **valid_body(sample_zone.zone_id, sample_alert.alert_id)
        )

        with pytest.raises(HTTPException) as error:
            inspection_service.create_inspection(db_session, second_officer, body)

        assert error.value.status_code == 404

    def test_create_inspection_alert_zone_mismatch(
        self,
        db_session,
        sample_officer,
        sample_coordinator,
        sample_alert,
        sample_assignment,
    ):
        other_zone = Zone(
            name="Other Zone",
            basin="Sanyati",
            zone_type=ZoneType.FISHING_ZONE,
            boundary={"type": "Polygon", "coordinates": []},
            radiance_threshold=Decimal(10),
            cluster_radius_m=Decimal(500),
        )
        db_session.add(other_zone)
        db_session.commit()
        body = InspectionCreate(**valid_body(other_zone.zone_id, sample_alert.alert_id))

        with pytest.raises(HTTPException) as error:
            inspection_service.create_inspection(db_session, sample_officer, body)

        assert error.value.status_code == 409

    def test_create_inspection_rejects_future_time(
        self, db_session, sample_officer, sample_zone
    ):
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        body = InspectionCreate(**valid_body(sample_zone.zone_id, inspected_at=future))

        with pytest.raises(HTTPException) as error:
            inspection_service.create_inspection(db_session, sample_officer, body)

        assert error.value.status_code == 400

    def test_create_inspection_coordinator_not_allowed(
        self, db_session, sample_coordinator, sample_zone
    ):
        body = InspectionCreate(**valid_body(sample_zone.zone_id))

        with pytest.raises(HTTPException) as error:
            inspection_service.create_inspection(db_session, sample_coordinator, body)

        assert error.value.status_code == 403

    def test_create_inspection_inactive_officer(
        self, db_session, sample_officer, sample_zone
    ):
        sample_officer.is_active = False
        body = InspectionCreate(**valid_body(sample_zone.zone_id))

        with pytest.raises(HTTPException) as error:
            inspection_service.create_inspection(db_session, sample_officer, body)

        assert error.value.status_code == 403

    def test_get_inspection_as_owner_and_coordinator(
        self, db_session, sample_officer, sample_coordinator, landing_inspection
    ):
        own = inspection_service.get_inspection(
            db_session, sample_officer, landing_inspection.inspection_id
        )
        any_ = inspection_service.get_inspection(
            db_session, sample_coordinator, landing_inspection.inspection_id
        )

        assert own.inspection_id == landing_inspection.inspection_id
        assert any_.inspection_id == landing_inspection.inspection_id

    def test_get_inspection_hidden_from_other_officer(
        self, db_session, second_officer, landing_inspection
    ):
        with pytest.raises(HTTPException) as error:
            inspection_service.get_inspection(
                db_session, second_officer, landing_inspection.inspection_id
            )

        assert error.value.status_code == 404

    def test_get_inspection_not_found(self, db_session, sample_coordinator):
        with pytest.raises(HTTPException) as error:
            inspection_service.get_inspection(
                db_session, sample_coordinator, uuid.uuid4()
            )

        assert error.value.status_code == 404

    def test_list_inspections_filters(
        self,
        db_session,
        sample_coordinator,
        sample_inspection,
        landing_inspection,
        sample_alert,
    ):
        by_alert = inspection_service.list_inspections(
            db_session, sample_coordinator, alert_id=sample_alert.alert_id
        )
        by_zone = inspection_service.list_inspections(
            db_session, sample_coordinator, zone_id=uuid.uuid4()
        )
        by_officer = inspection_service.list_inspections(
            db_session, sample_coordinator, officer_id=uuid.uuid4()
        )

        assert [inspection.inspection_id for inspection in by_alert] == [
            sample_inspection.inspection_id
        ]
        assert by_zone == []
        assert by_officer == []

    def test_list_inspections_limit_and_offset(
        self, db_session, sample_coordinator, sample_inspection, landing_inspection
    ):
        assert (
            len(
                inspection_service.list_inspections(
                    db_session, sample_coordinator, limit=1
                )
            )
            == 1
        )
        assert (
            len(
                inspection_service.list_inspections(
                    db_session, sample_coordinator, limit=1, offset=1
                )
            )
            == 1
        )

    def test_officer_was_assigned(
        self,
        db_session,
        sample_alert,
        sample_assignment,
        sample_officer,
        second_officer,
    ):
        assert inspection_service.officer_was_assigned(
            db_session, sample_alert.alert_id, sample_officer.user_id
        )
        assert not inspection_service.officer_was_assigned(
            db_session, sample_alert.alert_id, second_officer.user_id
        )

    def test_list_inspections_officer_sees_only_own(
        self, db_session, sample_officer, second_officer, landing_inspection
    ):
        assert len(inspection_service.list_inspections(db_session, sample_officer)) == 1
        assert inspection_service.list_inspections(db_session, second_officer) == []

    def test_list_inspections_officer_cannot_widen_filter(
        self, db_session, sample_officer, second_officer, landing_inspection
    ):
        results = inspection_service.list_inspections(
            db_session, second_officer, officer_id=sample_officer.user_id
        )

        assert results == []

    def test_list_inspections_coordinator_sees_all(
        self, db_session, sample_coordinator, landing_inspection
    ):
        assert (
            len(inspection_service.list_inspections(db_session, sample_coordinator))
            == 1
        )

    def test_create_inspection_previously_assigned_officer(
        self,
        db_session,
        sample_officer,
        second_officer,
        sample_zone,
        sample_alert,
        sample_assignment,
    ):
        sample_alert.officer_id = second_officer.user_id
        sample_assignment.ended_at = datetime.now(timezone.utc)
        db_session.commit()
        body = InspectionCreate(
            **valid_body(sample_zone.zone_id, sample_alert.alert_id)
        )

        inspection = inspection_service.create_inspection(
            db_session, sample_officer, body
        )
        db_session.refresh(sample_assignment)

        assert inspection.alert_id == sample_alert.alert_id
        assert sample_assignment.status == AssignmentStatus.ASSIGNED

    def test_create_inspection_small_clock_difference_allowed(
        self, db_session, sample_officer, sample_zone
    ):
        slightly_ahead = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        body = InspectionCreate(
            **valid_body(sample_zone.zone_id, inspected_at=slightly_ahead)
        )

        inspection = inspection_service.create_inspection(
            db_session, sample_officer, body
        )

        assert inspection.inspection_id is not None

    def test_get_inspection_inactive_user(
        self, db_session, sample_officer, landing_inspection
    ):
        sample_officer.is_active = False

        with pytest.raises(HTTPException) as error:
            inspection_service.get_inspection(
                db_session, sample_officer, landing_inspection.inspection_id
            )

        assert error.value.status_code == 403

    def test_list_inspections_inactive_user(
        self, db_session, sample_officer, landing_inspection
    ):
        sample_officer.is_active = False

        with pytest.raises(HTTPException) as error:
            inspection_service.list_inspections(db_session, sample_officer)

        assert error.value.status_code == 403

    def test_list_inspections_coordinator_filter_by_officer(
        self,
        db_session,
        sample_coordinator,
        sample_officer,
        second_officer,
        landing_inspection,
    ):
        mine = inspection_service.list_inspections(
            db_session, sample_coordinator, officer_id=sample_officer.user_id
        )
        theirs = inspection_service.list_inspections(
            db_session, sample_coordinator, officer_id=second_officer.user_id
        )

        assert [inspection.inspection_id for inspection in mine] == [
            landing_inspection.inspection_id
        ]
        assert theirs == []

    def test_list_inspections_newest_first(
        self, db_session, sample_officer, sample_zone
    ):
        now = datetime.now(timezone.utc)
        older = InspectionCreate(
            **valid_body(
                sample_zone.zone_id, inspected_at=(now - timedelta(hours=3)).isoformat()
            )
        )
        newer = InspectionCreate(
            **valid_body(
                sample_zone.zone_id, inspected_at=(now - timedelta(hours=1)).isoformat()
            )
        )
        older_record = inspection_service.create_inspection(
            db_session, sample_officer, older
        )
        newer_record = inspection_service.create_inspection(
            db_session, sample_officer, newer
        )

        results = inspection_service.list_inspections(db_session, sample_officer)

        assert [inspection.inspection_id for inspection in results] == [
            newer_record.inspection_id,
            older_record.inspection_id,
        ]

    # ---- positive case
    @pytest.mark.parametrize("inspection_type", ["site", "landing_site", "zone"])
    def test_service_create_each_type(
        self, db_session, sample_officer, sample_zone, inspection_type
    ):
        body = InspectionCreate(
            **valid_body(sample_zone.zone_id, inspection_type=inspection_type)
        )

        assert inspection_service.create_inspection(
            db_session, sample_officer, body
        ).inspection_type == InspectionType(inspection_type)

    @pytest.mark.parametrize(
        "outcome",
        ["activity_consistent", "no_activity", "no_fishing_light", "unable_to_verify"],
    )
    def test_service_create_each_outcome(
        self, db_session, sample_officer, sample_zone, outcome
    ):
        body = InspectionCreate(**valid_body(sample_zone.zone_id, outcome=outcome))

        assert inspection_service.create_inspection(
            db_session, sample_officer, body
        ).outcome == InspectionOutcome(outcome)

    # ---- boundary case
    @pytest.mark.parametrize(
        "minutes_ahead, allowed", [(0, True), (9, True), (11, False), (60, False)]
    )
    def test_service_clock_allowance(
        self, db_session, sample_officer, sample_zone, minutes_ahead, allowed
    ):
        when = (
            datetime.now(timezone.utc) + timedelta(minutes=minutes_ahead)
        ).isoformat()
        body = InspectionCreate(**valid_body(sample_zone.zone_id, inspected_at=when))

        if allowed:
            assert (
                inspection_service.create_inspection(
                    db_session, sample_officer, body
                ).inspection_id
                is not None
            )
        else:
            with pytest.raises(HTTPException) as error:
                inspection_service.create_inspection(db_session, sample_officer, body)
            assert error.value.status_code == 400

    def test_service_old_inspection_accepted(
        self, db_session, sample_officer, sample_zone
    ):
        last_year = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
        body = InspectionCreate(
            **valid_body(sample_zone.zone_id, inspected_at=last_year)
        )

        assert (
            inspection_service.create_inspection(
                db_session, sample_officer, body
            ).inspection_id
            is not None
        )

    # ---- negative case
    def test_service_unknown_alert(self, db_session, sample_officer, sample_zone):
        body = InspectionCreate(**valid_body(sample_zone.zone_id, uuid.uuid4()))

        with pytest.raises(HTTPException) as error:
            inspection_service.create_inspection(db_session, sample_officer, body)

        assert error.value.status_code == 404

    def test_service_create_without_user(self, db_session, sample_zone):
        with pytest.raises(HTTPException) as error:
            inspection_service.create_inspection(
                db_session, None, InspectionCreate(**valid_body(sample_zone.zone_id))
            )

        assert error.value.status_code == 403

    def test_service_get_without_user(self, db_session, landing_inspection):
        with pytest.raises(HTTPException) as error:
            inspection_service.get_inspection(
                db_session, None, landing_inspection.inspection_id
            )

        assert error.value.status_code == 403

    def test_service_list_without_user(self, db_session):
        with pytest.raises(HTTPException) as error:
            inspection_service.list_inspections(db_session, None)

        assert error.value.status_code == 403

    # ---- positive case
    def test_service_officer_gets_own_alert_inspection(
        self, db_session, sample_officer, sample_inspection
    ):
        result = inspection_service.get_inspection(
            db_session, sample_officer, sample_inspection.inspection_id
        )

        assert result.alert_id == sample_inspection.alert_id

    def test_service_coordinator_combined_filters(
        self,
        db_session,
        sample_coordinator,
        sample_zone,
        sample_alert,
        sample_inspection,
        landing_inspection,
    ):
        results = inspection_service.list_inspections(
            db_session,
            sample_coordinator,
            alert_id=sample_alert.alert_id,
            zone_id=sample_zone.zone_id,
        )

        assert [inspection.inspection_id for inspection in results] == [
            sample_inspection.inspection_id
        ]

    def test_service_officer_zone_filter_still_own_only(
        self,
        db_session,
        sample_officer,
        second_officer,
        sample_zone,
        landing_inspection,
    ):
        inspection_repository.create(
            db_session, make_record(second_officer, sample_zone)
        )

        results = inspection_service.list_inspections(
            db_session, sample_officer, zone_id=sample_zone.zone_id
        )

        assert [inspection.officer_id for inspection in results] == [
            sample_officer.user_id
        ]

    @pytest.mark.parametrize("offset, expected", [(0, 2), (1, 1), (2, 0), (10, 0)])
    def test_service_offset(
        self,
        db_session,
        sample_coordinator,
        sample_inspection,
        landing_inspection,
        offset,
        expected,
    ):
        assert (
            len(
                inspection_service.list_inspections(
                    db_session, sample_coordinator, offset=offset
                )
            )
            == expected
        )

    def test_service_officer_was_assigned_without_any_assignment(
        self, db_session, sample_alert, sample_officer
    ):
        assert (
            inspection_service.officer_was_assigned(
                db_session, sample_alert.alert_id, sample_officer.user_id
            )
            is False
        )

    def test_service_is_coordinator(self, sample_coordinator, sample_officer):
        assert inspection_service.is_coordinator(sample_coordinator) is True
        assert inspection_service.is_coordinator(sample_officer) is False

    def test_service_mark_alert_reported_without_active_assignment(
        self, db_session, sample_officer, sample_alert
    ):
        inspection_service.mark_alert_reported(db_session, sample_officer, sample_alert)

        assert sample_alert.assignment_status == AssignmentStatus.REPORTED
        assert sample_alert.reported_at is not None


class TestInspectionRouter:
    def test_create_inspection(self, client, sample_officer, sample_zone):
        body = valid_body(sample_zone.zone_id)

        response = client.post(API, json=body, headers=auth_headers(sample_officer))

        assert response.status_code == 201
        data = response.json()
        assert uuid.UUID(data["inspection_id"])
        assert data["officer_id"] == str(sample_officer.user_id)
        assert data["latitude"] == -16.8501

    def test_create_inspection_twice_creates_two(
        self, client, sample_officer, sample_zone
    ):
        body = valid_body(sample_zone.zone_id)
        headers = auth_headers(sample_officer)

        first = client.post(API, json=body, headers=headers)
        second = client.post(API, json=body, headers=headers)

        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["inspection_id"] != second.json()["inspection_id"]
        assert len(client.get(API, headers=headers).json()) == 2

    def test_create_inspection_rejects_client_id(
        self, client, sample_officer, sample_zone
    ):
        body = valid_body(sample_zone.zone_id, inspection_id=str(uuid.uuid4()))

        response = client.post(API, json=body, headers=auth_headers(sample_officer))

        assert response.status_code == 422

    def test_create_inspection_coordinator_forbidden(
        self, client, sample_coordinator, sample_zone
    ):
        response = client.post(
            API,
            json=valid_body(sample_zone.zone_id),
            headers=auth_headers(sample_coordinator),
        )

        assert response.status_code == 403

    def test_create_inspection_requires_login(self, client, sample_zone):
        assert client.post(API, json=valid_body(sample_zone.zone_id)).status_code == 401

    def test_create_inspection_unknown_zone(self, client, sample_officer):
        assert (
            client.post(
                API, json=valid_body(), headers=auth_headers(sample_officer)
            ).status_code
            == 404
        )

    @pytest.mark.parametrize(
        "field, value",
        [
            ("rigs_observed", -1),
            ("latitude", "100"),
            ("inspected_at", "2026-10-10T22:00:00"),
            ("extra", "x"),
        ],
    )
    def test_create_inspection_bad_body(
        self, client, sample_officer, sample_zone, field, value
    ):
        body = valid_body(sample_zone.zone_id, **{field: value})

        response = client.post(API, json=body, headers=auth_headers(sample_officer))

        assert response.status_code == 422

    def test_list_inspections(self, client, sample_coordinator, landing_inspection):
        response = client.get(API, headers=auth_headers(sample_coordinator))

        assert response.status_code == 200
        assert response.json()[0]["inspection_id"] == str(
            landing_inspection.inspection_id
        )

    def test_list_inspections_officer_scoped(
        self, client, second_officer, landing_inspection
    ):
        response = client.get(API, headers=auth_headers(second_officer))

        assert response.status_code == 200
        assert response.json() == []

    def test_get_inspection(self, client, sample_officer, landing_inspection):
        response = client.get(
            f"{API}/{landing_inspection.inspection_id}",
            headers=auth_headers(sample_officer),
        )

        assert response.status_code == 200
        assert response.json()["inspection_type"] == "landing_site"

    def test_get_inspection_hidden_from_other_officer(
        self, client, second_officer, landing_inspection
    ):
        response = client.get(
            f"{API}/{landing_inspection.inspection_id}",
            headers=auth_headers(second_officer),
        )

        assert response.status_code == 404

    def test_create_inspection_for_assigned_alert(
        self, client, sample_officer, sample_zone, sample_alert, sample_assignment
    ):
        body = valid_body(sample_zone.zone_id, sample_alert.alert_id)

        response = client.post(API, json=body, headers=auth_headers(sample_officer))

        assert response.status_code == 201
        assert response.json()["alert_id"] == str(sample_alert.alert_id)

    def test_create_inspection_alert_not_assigned(
        self, client, second_officer, sample_zone, sample_alert
    ):
        body = valid_body(sample_zone.zone_id, sample_alert.alert_id)

        response = client.post(API, json=body, headers=auth_headers(second_officer))

        assert response.status_code == 404

    def test_create_inspection_future_time(self, client, sample_officer, sample_zone):
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

        response = client.post(
            API,
            json=valid_body(sample_zone.zone_id, inspected_at=future),
            headers=auth_headers(sample_officer),
        )

        assert response.status_code == 400

    def test_list_inspections_requires_login(self, client):
        assert client.get(API).status_code == 401

    def test_list_inspections_filter_by_zone(
        self, client, sample_coordinator, sample_zone, landing_inspection
    ):
        headers = auth_headers(sample_coordinator)

        in_zone = client.get(
            API, params={"zone_id": str(sample_zone.zone_id)}, headers=headers
        )
        other_zone = client.get(
            API, params={"zone_id": str(uuid.uuid4())}, headers=headers
        )

        assert len(in_zone.json()) == 1
        assert other_zone.json() == []

    @pytest.mark.parametrize(
        "params",
        [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"zone_id": "not-a-uuid"}],
    )
    def test_list_inspections_bad_query(self, client, sample_coordinator, params):
        response = client.get(
            API, params=params, headers=auth_headers(sample_coordinator)
        )

        assert response.status_code == 422

    def test_get_inspection_as_coordinator(
        self, client, sample_coordinator, landing_inspection
    ):
        response = client.get(
            f"{API}/{landing_inspection.inspection_id}",
            headers=auth_headers(sample_coordinator),
        )

        assert response.status_code == 200
        assert response.json()["inspection_id"] == str(landing_inspection.inspection_id)

    def test_get_inspection_not_found(self, client, sample_coordinator):
        response = client.get(
            f"{API}/{uuid.uuid4()}", headers=auth_headers(sample_coordinator)
        )

        assert response.status_code == 404

    def test_get_inspection_bad_id(self, client, sample_coordinator):
        response = client.get(
            f"{API}/not-a-uuid", headers=auth_headers(sample_coordinator)
        )

        assert response.status_code == 422

    # ---- positive
    @pytest.mark.parametrize("inspection_type", ["site", "landing_site", "zone"])
    def test_router_create_each_type(
        self, client, sample_officer, sample_zone, inspection_type
    ):
        body = valid_body(sample_zone.zone_id, inspection_type=inspection_type)

        response = client.post(API, json=body, headers=auth_headers(sample_officer))

        assert response.status_code == 201
        assert response.json()["inspection_type"] == inspection_type

    def test_router_create_response_fields(self, client, sample_officer, sample_zone):
        response = client.post(
            API,
            json=valid_body(sample_zone.zone_id),
            headers=auth_headers(sample_officer),
        )

        assert set(response.json()) == {
            "inspection_id",
            "alert_id",
            "officer_id",
            "zone_id",
            "inspection_type",
            "outcome",
            "rigs_observed",
            "latitude",
            "longitude",
            "notes",
            "inspected_at",
            "synced_at",
        }

    def test_router_coordinator_lists_all_officers(
        self,
        client,
        sample_coordinator,
        second_officer,
        sample_zone,
        db_session,
        landing_inspection,
    ):
        inspection_repository.create(
            db_session, make_record(second_officer, sample_zone)
        )

        response = client.get(API, headers=auth_headers(sample_coordinator))

        assert len(response.json()) == 2

    def test_router_list_filter_by_alert(
        self,
        client,
        sample_coordinator,
        sample_alert,
        sample_inspection,
        landing_inspection,
    ):
        response = client.get(
            API,
            params={"alert_id": str(sample_alert.alert_id)},
            headers=auth_headers(sample_coordinator),
        )

        assert [item["inspection_id"] for item in response.json()] == [
            str(sample_inspection.inspection_id)
        ]

    @pytest.mark.parametrize(
        "params, expected",
        [({"limit": 1}, 1), ({"limit": 1, "offset": 1}, 1), ({"offset": 2}, 0)],
    )
    def test_router_list_paging(
        self,
        client,
        sample_coordinator,
        sample_inspection,
        landing_inspection,
        params,
        expected,
    ):
        response = client.get(
            API, params=params, headers=auth_headers(sample_coordinator)
        )

        assert len(response.json()) == expected

    # ---- negative case
    @pytest.mark.parametrize(
        "field",
        [
            "zone_id",
            "inspection_type",
            "outcome",
            "rigs_observed",
            "latitude",
            "longitude",
            "inspected_at",
        ],
    )
    def test_router_create_missing_field(
        self, client, sample_officer, sample_zone, field
    ):
        body = valid_body(sample_zone.zone_id)
        del body[field]

        response = client.post(API, json=body, headers=auth_headers(sample_officer))

        assert response.status_code == 422

    def test_router_create_not_json(self, client, sample_officer):
        headers = {**auth_headers(sample_officer), "Content-Type": "application/json"}

        response = client.post(API, content="this is not json", headers=headers)

        assert response.status_code == 422

    def test_router_create_unknown_alert(self, client, sample_officer, sample_zone):
        body = valid_body(sample_zone.zone_id, uuid.uuid4())

        assert (
            client.post(
                API, json=body, headers=auth_headers(sample_officer)
            ).status_code
            == 404
        )

    def test_router_create_alert_zone_mismatch(
        self, client, db_session, sample_officer, sample_alert, sample_assignment
    ):
        other_zone = Zone(
            name="Router Other Zone",
            basin="Sanyati",
            zone_type=ZoneType.FISHING_ZONE,
            boundary={"type": "Polygon", "coordinates": []},
            radiance_threshold=Decimal(10),
            cluster_radius_m=Decimal(500),
        )
        db_session.add(other_zone)
        db_session.commit()

        response = client.post(
            API,
            json=valid_body(other_zone.zone_id, sample_alert.alert_id),
            headers=auth_headers(sample_officer),
        )

        assert response.status_code == 409

    def test_router_create_inactive_officer(
        self, client, db_session, sample_officer, sample_zone
    ):
        headers = auth_headers(sample_officer)
        sample_officer.is_active = False
        db_session.commit()

        assert (
            client.post(
                API, json=valid_body(sample_zone.zone_id), headers=headers
            ).status_code
            == 401
        )

    def test_router_officer_cannot_widen_list(
        self, client, second_officer, sample_officer, landing_inspection
    ):
        response = client.get(
            API,
            params={"officer_id": str(sample_officer.user_id)},
            headers=auth_headers(second_officer),
        )

        assert response.json() == []

    def test_router_get_requires_login(self, client, landing_inspection):
        assert (
            client.get(f"{API}/{landing_inspection.inspection_id}").status_code == 401
        )

    def test_router_bad_token(self, client):
        assert (
            client.get(
                API, headers={"Authorization": "Bearer not-a-real-token"}
            ).status_code
            == 401
        )

    # ---- negative: actions that do not exist
    @pytest.mark.parametrize("method", ["put", "patch", "delete"])
    def test_router_unsupported_methods_on_one(
        self, client, sample_coordinator, landing_inspection, method
    ):
        response = getattr(client, method)(
            f"{API}/{landing_inspection.inspection_id}",
            headers=auth_headers(sample_coordinator),
        )

        assert response.status_code == 405

    @pytest.mark.parametrize("method", ["put", "patch", "delete"])
    def test_router_unsupported_methods_on_list(
        self, client, sample_coordinator, method
    ):
        assert (
            getattr(client, method)(
                API, headers=auth_headers(sample_coordinator)
            ).status_code
            == 405
        )


def make_record(officer, zone, **changes):
    values = {
        "inspection_id": uuid.uuid4(),
        "officer_id": officer.user_id,
        "zone_id": zone.zone_id,
        "inspection_type": InspectionType.ZONE,
        "outcome": InspectionOutcome.NO_ACTIVITY,
        "rigs_observed": 0,
        "latitude": Decimal("-16.850000"),
        "longitude": Decimal("28.050000"),
        "notes": "Patrol check",
        "inspected_at": datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc),
    }
    values.update(changes)
    return Inspection(**values)
