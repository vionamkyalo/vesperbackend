import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from models.alert_assignment import AlertAssignment, AssignmentStatus
from datetime import timedelta
from decimal import Decimal
from fastapi import Depends
from fastapi import FastAPI
from fastapi import Header
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session
from core import security
from database import get_db
from models.alert import AlertStatus
from models.user import User
from models.user import UserRole
from repositories.alert_assignment import alert_assignment_repository
from schemas.alert_assignment import AlertAssignmentCreate
from schemas.alert_assignment import AlertAssignmentRead
from services.alert_assignment import alert_assignment_service
import models.zone_setting_history  # noqa: F401


class TestAlertAssignment:
    def test_create_alert_assignment_happy_path(
        self, db_session, sample_alert, sample_officer, sample_coordinator
    ):
        assigned_at = datetime(2026, 10, 10, 18, 0, tzinfo=timezone.utc)
        acknowledged_at = datetime(2026, 10, 10, 18, 5, tzinfo=timezone.utc)
        reported_at = datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc)
        ended_at = datetime(2026, 10, 11, 8, 0, tzinfo=timezone.utc)
        assignment = AlertAssignment(
            alert_id=sample_alert.alert_id,
            officer_id=sample_officer.user_id,
            assigned_by=sample_coordinator.user_id,
            status=AssignmentStatus.REPORTED,
            assigned_at=assigned_at,
            acknowledged_at=acknowledged_at,
            reported_at=reported_at,
            ended_at=ended_at,
        )
        db_session.add(assignment)
        db_session.commit()
        db_session.refresh(assignment)

        assert assignment.assignment_id is not None
        assert isinstance(assignment.assignment_id, uuid.UUID)
        assert assignment.alert_id == sample_alert.alert_id
        assert assignment.officer_id == sample_officer.user_id
        assert assignment.assigned_by == sample_coordinator.user_id
        assert assignment.status == AssignmentStatus.REPORTED
        assert assignment.assigned_at == assigned_at
        assert assignment.acknowledged_at == acknowledged_at
        assert assignment.reported_at == reported_at
        assert assignment.ended_at == ended_at
        assert assignment.ended_at is not None

    def test_alert_assignment_optional_fields(
        self, db_session, sample_alert, sample_officer, sample_coordinator
    ):
        assignment = AlertAssignment(
            alert_id=sample_alert.alert_id,
            officer_id=sample_officer.user_id,
            assigned_by=sample_coordinator.user_id,
        )
        db_session.add(assignment)
        db_session.commit()
        db_session.refresh(assignment)

        assert assignment.acknowledged_at is None
        assert assignment.reported_at is None
        assert assignment.ended_at is None
        assert assignment.status == AssignmentStatus.ASSIGNED
        assert assignment.assigned_at is not None
        assert assignment.ended_at is None

    @pytest.mark.parametrize(
        "status",
        [
            AssignmentStatus.ASSIGNED,
            AssignmentStatus.ACKNOWLEDGED,
            AssignmentStatus.REPORTED,
            AssignmentStatus.REASSIGNED,
            AssignmentStatus.FAILED,
        ],
    )
    def test_alert_assignment_status_values(
        self, db_session, sample_alert, sample_officer, sample_coordinator, status
    ):
        assignment = AlertAssignment(
            alert_id=sample_alert.alert_id,
            officer_id=sample_officer.user_id,
            assigned_by=sample_coordinator.user_id,
            status=status,
        )
        db_session.add(assignment)
        db_session.commit()
        db_session.refresh(assignment)

        assert assignment.status == status

    def test_alert_assignment_missing_required_fields(self, db_session):
        assignment = AlertAssignment()
        db_session.add(assignment)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_alert_assignment_missing_alert_id(
        self, db_session, sample_officer, sample_coordinator
    ):
        assignment = AlertAssignment(
            officer_id=sample_officer.user_id,
            assigned_by=sample_coordinator.user_id,
        )
        db_session.add(assignment)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_alert_assignment_missing_officer_id(
        self, db_session, sample_alert, sample_coordinator
    ):
        assignment = AlertAssignment(
            alert_id=sample_alert.alert_id,
            assigned_by=sample_coordinator.user_id,
        )
        db_session.add(assignment)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_alert_assignment_missing_assigned_by(
        self, db_session, sample_alert, sample_officer
    ):
        assignment = AlertAssignment(
            alert_id=sample_alert.alert_id,
            officer_id=sample_officer.user_id,
        )
        db_session.add(assignment)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_alert_assignment_alert_relationship(
        self, db_session, sample_alert, sample_assignment
    ):
        db_session.refresh(sample_alert)

        assert sample_assignment.alert.alert_id == sample_alert.alert_id
        assert sample_assignment in sample_alert.assignments

    def test_alert_assignment_officer_relationship(
        self, db_session, sample_officer, sample_assignment
    ):
        db_session.refresh(sample_officer)

        assert sample_assignment.officer.user_id == sample_officer.user_id
        assert sample_assignment in sample_officer.assignments

    def test_alert_assignment_assigner_relationship(
        self, db_session, sample_coordinator, sample_assignment
    ):
        db_session.refresh(sample_assignment)

        assert sample_assignment.assigner.user_id == sample_coordinator.user_id


ASSIGN_API = "/api/v1/alert-assignments"


def make_assignment(db_session, alert, officer, coordinator, minutes_ago=0, **changes):
    values = {
        "alert_id": alert.alert_id,
        "officer_id": officer.user_id,
        "assigned_by": coordinator.user_id,
        "assigned_at": datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc)
        - timedelta(minutes=minutes_ago),
    }
    values.update(changes)
    assignment = AlertAssignment(**values)
    db_session.add(assignment)
    db_session.commit()
    db_session.refresh(assignment)
    return assignment


def make_second_alert(db_session, sample_zone, sample_reading, **changes):
    from models.alert import Alert

    values = {
        "zone_id": sample_zone.zone_id,
        "reading_id": sample_reading.reading_id,
        "cluster_label": 1,
        "point_count": 4,
        "confidence": Decimal("0.6000"),
        "centroid_latitude": Decimal("-16.860000"),
        "centroid_longitude": Decimal("28.060000"),
    }
    values.update(changes)
    alert = Alert(**values)
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)
    return alert


def assign_body(alert, officer):
    return AlertAssignmentCreate(alert_id=alert.alert_id, officer_id=officer.user_id)


def assignment_stand_in_role_check(*roles):
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
                status_code=403, detail="You do not have permission to do this."
            )
        return user

    return checker


ASSIGNMENT_REAL_SECURITY = hasattr(security, "create_access_token") and hasattr(
    security, "require_any_user"
)

if not ASSIGNMENT_REAL_SECURITY:
    security.require_coordinator = assignment_stand_in_role_check(
        UserRole.PATROL_COORDINATOR
    )
    security.require_officer = assignment_stand_in_role_check(UserRole.PATROL_OFFICER)
    security.require_any_user = assignment_stand_in_role_check(
        UserRole.PATROL_COORDINATOR, UserRole.PATROL_OFFICER
    )


def assignment_headers(user):
    if ASSIGNMENT_REAL_SECURITY:
        token = security.create_access_token(user.user_id, user.role.value)
        return {"Authorization": f"Bearer {token}"}
    return {"X-Test-User": str(user.user_id)}


@pytest.fixture
def assignment_client(db_session):
    from routers import alert_assignment as assignment_router

    app = FastAPI()
    if ASSIGNMENT_REAL_SECURITY:
        security.register_error_handlers(app)
    app.include_router(assignment_router.router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


class TestAlertAssignmentRepository:
    def test_create_saves_all_fields(
        self, db_session, sample_alert, sample_officer, sample_coordinator
    ):
        assignment = AlertAssignment(
            alert_id=sample_alert.alert_id,
            officer_id=sample_officer.user_id,
            assigned_by=sample_coordinator.user_id,
        )

        saved = alert_assignment_repository.create(db_session, assignment)
        db_session.expire_all()
        found = alert_assignment_repository.get(db_session, saved.assignment_id)

        assert found.alert_id == sample_alert.alert_id
        assert found.officer_id == sample_officer.user_id
        assert found.assigned_by == sample_coordinator.user_id

    def test_create_fills_defaults(
        self, db_session, sample_alert, sample_officer, sample_coordinator
    ):
        assignment = AlertAssignment(
            alert_id=sample_alert.alert_id,
            officer_id=sample_officer.user_id,
            assigned_by=sample_coordinator.user_id,
        )

        saved = alert_assignment_repository.create(db_session, assignment)

        assert isinstance(saved.assignment_id, uuid.UUID)
        assert saved.status == AssignmentStatus.ASSIGNED
        assert saved.assigned_at is not None
        assert saved.acknowledged_at is None
        assert saved.reported_at is None
        assert saved.ended_at is None

    def test_create_returns_same_object(
        self, db_session, sample_alert, sample_officer, sample_coordinator
    ):
        assignment = AlertAssignment(
            alert_id=sample_alert.alert_id,
            officer_id=sample_officer.user_id,
            assigned_by=sample_coordinator.user_id,
        )

        assert alert_assignment_repository.create(db_session, assignment) is assignment

    @pytest.mark.parametrize("assignment_status", list(AssignmentStatus))
    def test_create_each_status(
        self,
        db_session,
        sample_alert,
        sample_officer,
        sample_coordinator,
        assignment_status,
    ):
        assignment = make_assignment(
            db_session,
            sample_alert,
            sample_officer,
            sample_coordinator,
            status=assignment_status,
        )
        db_session.expire_all()

        assert (
            alert_assignment_repository.get(db_session, assignment.assignment_id).status
            == assignment_status
        )

    def test_get_found(self, db_session, sample_assignment):
        found = alert_assignment_repository.get(
            db_session, sample_assignment.assignment_id
        )

        assert found.assignment_id == sample_assignment.assignment_id

    def test_get_unknown_id(self, db_session):
        assert alert_assignment_repository.get(db_session, uuid.uuid4()) is None

    def test_get_all_empty(self, db_session):
        assert alert_assignment_repository.get_all(db_session) == []

    @pytest.mark.parametrize("count", [1, 3, 5])
    def test_get_all_counts(
        self, db_session, sample_alert, sample_officer, sample_coordinator, count
    ):
        for minutes in range(count):
            make_assignment(
                db_session,
                sample_alert,
                sample_officer,
                sample_coordinator,
                minutes_ago=minutes,
            )

        assert len(alert_assignment_repository.get_all(db_session)) == count

    def test_get_all_every_officer(
        self,
        db_session,
        sample_alert,
        sample_officer,
        second_officer,
        sample_coordinator,
    ):
        make_assignment(db_session, sample_alert, sample_officer, sample_coordinator)
        make_assignment(db_session, sample_alert, second_officer, sample_coordinator)

        officers = {
            assignment.officer_id
            for assignment in alert_assignment_repository.get_all(db_session)
        }

        assert officers == {sample_officer.user_id, second_officer.user_id}

    def test_update_status_and_times(self, db_session, sample_assignment):
        now = datetime.now(timezone.utc)
        sample_assignment.status = AssignmentStatus.ACKNOWLEDGED
        sample_assignment.acknowledged_at = now

        alert_assignment_repository.update(db_session, sample_assignment)
        db_session.expire_all()
        found = alert_assignment_repository.get(
            db_session, sample_assignment.assignment_id
        )

        assert found.status == AssignmentStatus.ACKNOWLEDGED
        assert found.acknowledged_at == now

    def test_update_ended_at(self, db_session, sample_assignment):
        now = datetime.now(timezone.utc)
        sample_assignment.ended_at = now

        saved = alert_assignment_repository.update(db_session, sample_assignment)

        assert saved is sample_assignment
        assert saved.ended_at == now

    @pytest.mark.parametrize("field", ["alert_id", "officer_id", "assigned_by"])
    def test_create_required_field_missing(
        self, db_session, sample_alert, sample_officer, sample_coordinator, field
    ):
        values = {
            "alert_id": sample_alert.alert_id,
            "officer_id": sample_officer.user_id,
            "assigned_by": sample_coordinator.user_id,
        }
        values[field] = None

        with pytest.raises(IntegrityError):
            alert_assignment_repository.create(db_session, AlertAssignment(**values))

        db_session.rollback()

    @pytest.mark.parametrize("field", ["alert_id", "officer_id", "assigned_by"])
    def test_create_unknown_link_rejected(
        self, db_session, sample_alert, sample_officer, sample_coordinator, field
    ):
        values = {
            "alert_id": sample_alert.alert_id,
            "officer_id": sample_officer.user_id,
            "assigned_by": sample_coordinator.user_id,
        }
        values[field] = uuid.uuid4()

        with pytest.raises(IntegrityError):
            alert_assignment_repository.create(db_session, AlertAssignment(**values))

        db_session.rollback()

    def test_create_duplicate_id_rejected(
        self, db_session, sample_assignment, sample_alert, sample_officer
    ):
        assignment_id = sample_assignment.assignment_id
        db_session.expunge_all()
        copy = AlertAssignment(
            assignment_id=assignment_id,
            alert_id=sample_alert.alert_id,
            officer_id=sample_officer.user_id,
            assigned_by=sample_officer.user_id,
        )

        with pytest.raises(IntegrityError):
            alert_assignment_repository.create(db_session, copy)

        db_session.rollback()

    # ---- positive cases
    @pytest.mark.parametrize("assignment_status", list(AssignmentStatus))
    def test_repository_update_each_status(
        self, db_session, sample_assignment, assignment_status
    ):
        sample_assignment.status = assignment_status

        alert_assignment_repository.update(db_session, sample_assignment)
        db_session.expire_all()

        assert (
            alert_assignment_repository.get(
                db_session, sample_assignment.assignment_id
            ).status
            == assignment_status
        )

    @pytest.mark.parametrize("field", ["acknowledged_at", "reported_at", "ended_at"])
    def test_repository_saves_each_time_field(
        self, db_session, sample_alert, sample_officer, sample_coordinator, field
    ):
        when = datetime(2026, 10, 11, 1, 30, tzinfo=timezone.utc)
        assignment = make_assignment(
            db_session,
            sample_alert,
            sample_officer,
            sample_coordinator,
            **{field: when},
        )
        db_session.expire_all()

        assert (
            getattr(
                alert_assignment_repository.get(db_session, assignment.assignment_id),
                field,
            )
            == when
        )

    # ---- edge cases
    @pytest.mark.parametrize("field", ["acknowledged_at", "reported_at", "ended_at"])
    def test_repository_time_fields_can_be_empty(
        self, db_session, sample_alert, sample_officer, sample_coordinator, field
    ):
        assignment = make_assignment(
            db_session,
            sample_alert,
            sample_officer,
            sample_coordinator,
            **{field: None},
        )

        assert getattr(assignment, field) is None

    def test_repository_keeps_assigned_time(
        self, db_session, sample_alert, sample_officer, sample_coordinator
    ):
        assignment = make_assignment(
            db_session, sample_alert, sample_officer, sample_coordinator, minutes_ago=90
        )
        db_session.expire_all()

        found = alert_assignment_repository.get(db_session, assignment.assignment_id)

        assert found.assigned_at == datetime(2026, 10, 10, 20, 30, tzinfo=timezone.utc)

    def test_repository_get_all_across_alerts(
        self,
        db_session,
        sample_alert,
        sample_officer,
        sample_coordinator,
        sample_zone,
        sample_reading,
    ):
        other_alert = make_second_alert(db_session, sample_zone, sample_reading)
        make_assignment(db_session, sample_alert, sample_officer, sample_coordinator)
        make_assignment(db_session, other_alert, sample_officer, sample_coordinator)

        alerts = {
            assignment.alert_id
            for assignment in alert_assignment_repository.get_all(db_session)
        }

        assert alerts == {sample_alert.alert_id, other_alert.alert_id}

    def test_repository_same_officer_many_assignments(
        self, db_session, sample_alert, sample_officer, sample_coordinator
    ):
        for minutes in range(4):
            make_assignment(
                db_session,
                sample_alert,
                sample_officer,
                sample_coordinator,
                minutes_ago=minutes,
            )

        assert len(alert_assignment_repository.get_all(db_session)) == 4


class TestAlertAssignmentSchema:
    def test_create_happy_path(self):
        alert_id = uuid.uuid4()
        officer_id = uuid.uuid4()

        data = AlertAssignmentCreate(alert_id=str(alert_id), officer_id=str(officer_id))

        assert data.alert_id == alert_id
        assert data.officer_id == officer_id

    @pytest.mark.parametrize("field", ["alert_id", "officer_id"])
    def test_create_missing_field(self, field):
        values = {"alert_id": str(uuid.uuid4()), "officer_id": str(uuid.uuid4())}
        del values[field]

        with pytest.raises(ValidationError):
            AlertAssignmentCreate(**values)

    @pytest.mark.parametrize("value", ["", "abc", "123", None, 42])
    @pytest.mark.parametrize("field", ["alert_id", "officer_id"])
    def test_create_bad_id(self, field, value):
        values = {"alert_id": str(uuid.uuid4()), "officer_id": str(uuid.uuid4())}
        values[field] = value

        with pytest.raises(ValidationError):
            AlertAssignmentCreate(**values)

    @pytest.mark.parametrize(
        "field, value",
        [
            ("assigned_by", str(uuid.uuid4())),
            ("status", "reported"),
            ("assigned_at", "2026-10-10T22:00:00Z"),
            ("ended_at", "2026-10-10T22:00:00Z"),
            ("assignment_id", str(uuid.uuid4())),
        ],
    )
    def test_create_server_fields_rejected(self, field, value):
        values = {
            "alert_id": str(uuid.uuid4()),
            "officer_id": str(uuid.uuid4()),
            field: value,
        }

        with pytest.raises(ValidationError):
            AlertAssignmentCreate(**values)

    def test_read_from_model(
        self, sample_assignment, sample_alert, sample_officer, sample_coordinator
    ):
        data = AlertAssignmentRead.model_validate(sample_assignment)

        assert data.assignment_id == sample_assignment.assignment_id
        assert data.alert_id == sample_alert.alert_id
        assert data.officer_id == sample_officer.user_id
        assert data.assigned_by == sample_coordinator.user_id
        assert data.status == AssignmentStatus.ASSIGNED

    def test_read_exact_fields(self, sample_assignment):
        data = AlertAssignmentRead.model_validate(sample_assignment).model_dump(
            mode="json"
        )

        assert set(data) == {
            "assignment_id",
            "alert_id",
            "officer_id",
            "assigned_by",
            "status",
            "assigned_at",
            "acknowledged_at",
            "reported_at",
            "ended_at",
        }

    def test_read_open_assignment_times_are_empty(self, sample_assignment):
        data = AlertAssignmentRead.model_validate(sample_assignment).model_dump(
            mode="json"
        )

        assert data["acknowledged_at"] is None
        assert data["reported_at"] is None
        assert data["ended_at"] is None

    @pytest.mark.parametrize("assignment_status", list(AssignmentStatus))
    def test_read_status_as_text(
        self,
        db_session,
        sample_alert,
        sample_officer,
        sample_coordinator,
        assignment_status,
    ):
        assignment = make_assignment(
            db_session,
            sample_alert,
            sample_officer,
            sample_coordinator,
            status=assignment_status,
        )

        data = AlertAssignmentRead.model_validate(assignment).model_dump(mode="json")

        assert data["status"] == assignment_status.value

    def test_read_bad_status_rejected(self):
        with pytest.raises(ValidationError):
            AlertAssignmentRead(
                assignment_id=uuid.uuid4(),
                alert_id=uuid.uuid4(),
                officer_id=uuid.uuid4(),
                assigned_by=uuid.uuid4(),
                status="on_holiday",
                assigned_at="2026-10-10T22:00:00Z",
                acknowledged_at=None,
                reported_at=None,
                ended_at=None,
            )

    # ---- positive cases
    def test_schema_create_accepts_uuid_objects(self):
        alert_id = uuid.uuid4()
        officer_id = uuid.uuid4()

        data = AlertAssignmentCreate(alert_id=alert_id, officer_id=officer_id)

        assert (data.alert_id, data.officer_id) == (alert_id, officer_id)

    def test_schema_create_accepts_upper_case_ids(self):
        alert_id = uuid.uuid4()

        data = AlertAssignmentCreate(
            alert_id=str(alert_id).upper(), officer_id=str(uuid.uuid4())
        )

        assert data.alert_id == alert_id

    def test_schema_create_same_id_twice_is_valid_shape(self):
        same = uuid.uuid4()

        assert AlertAssignmentCreate(alert_id=same, officer_id=same).alert_id == same

    # ---- negative cases
    @pytest.mark.parametrize(
        "field",
        [
            "assignment_id",
            "alert_id",
            "officer_id",
            "assigned_by",
            "status",
            "assigned_at",
            "acknowledged_at",
            "reported_at",
            "ended_at",
        ],
    )
    def test_schema_read_missing_field(self, field):
        values = {
            "assignment_id": uuid.uuid4(),
            "alert_id": uuid.uuid4(),
            "officer_id": uuid.uuid4(),
            "assigned_by": uuid.uuid4(),
            "status": "assigned",
            "assigned_at": "2026-10-10T22:00:00Z",
            "acknowledged_at": None,
            "reported_at": None,
            "ended_at": None,
        }
        del values[field]

        with pytest.raises(ValidationError):
            AlertAssignmentRead(**values)

    @pytest.mark.parametrize(
        "field", ["assigned_at", "acknowledged_at", "reported_at", "ended_at"]
    )
    def test_schema_read_bad_time(self, field):
        values = {
            "assignment_id": uuid.uuid4(),
            "alert_id": uuid.uuid4(),
            "officer_id": uuid.uuid4(),
            "assigned_by": uuid.uuid4(),
            "status": "assigned",
            "assigned_at": "2026-10-10T22:00:00Z",
            "acknowledged_at": None,
            "reported_at": None,
            "ended_at": None,
        }
        values[field] = "last night"

        with pytest.raises(ValidationError):
            AlertAssignmentRead(**values)

    # ---- positive cases
    @pytest.mark.parametrize("field", ["acknowledged_at", "reported_at", "ended_at"])
    def test_schema_read_filled_times(
        self, db_session, sample_alert, sample_officer, sample_coordinator, field
    ):
        when = datetime(2026, 10, 11, 1, 30, tzinfo=timezone.utc)
        assignment = make_assignment(
            db_session,
            sample_alert,
            sample_officer,
            sample_coordinator,
            **{field: when},
        )

        data = AlertAssignmentRead.model_validate(assignment).model_dump(mode="json")

        assert data[field].startswith("2026-10-11T01:30:00")

    def test_schema_read_ids_as_text(self, sample_assignment):
        data = AlertAssignmentRead.model_validate(sample_assignment).model_dump(
            mode="json"
        )

        for field in ["assignment_id", "alert_id", "officer_id", "assigned_by"]:
            assert data[field] == str(getattr(sample_assignment, field))


class TestAlertAssignmentService:
    def test_assign_new_alert(
        self, db_session, sample_coordinator, sample_officer, sample_alert
    ):
        assignment = alert_assignment_service.assign_alert(
            db_session, sample_coordinator, assign_body(sample_alert, sample_officer)
        )

        assert assignment.officer_id == sample_officer.user_id
        assert assignment.assigned_by == sample_coordinator.user_id
        assert assignment.status == AssignmentStatus.ASSIGNED
        assert assignment.ended_at is None

    def test_assign_updates_alert(
        self, db_session, sample_coordinator, sample_officer, sample_alert
    ):
        alert_assignment_service.assign_alert(
            db_session, sample_coordinator, assign_body(sample_alert, sample_officer)
        )

        assert sample_alert.officer_id == sample_officer.user_id
        assert sample_alert.assigned_by == sample_coordinator.user_id
        assert sample_alert.assignment_status == AssignmentStatus.ASSIGNED
        assert sample_alert.assigned_at is not None
        assert sample_alert.status == AlertStatus.IN_PROGRESS

    def test_reassign_ends_previous(
        self,
        db_session,
        sample_coordinator,
        second_officer,
        sample_alert,
        sample_assignment,
    ):
        new = alert_assignment_service.assign_alert(
            db_session, sample_coordinator, assign_body(sample_alert, second_officer)
        )
        db_session.refresh(sample_assignment)

        assert sample_assignment.status == AssignmentStatus.REASSIGNED
        assert sample_assignment.ended_at is not None
        assert new.officer_id == second_officer.user_id
        assert sample_alert.officer_id == second_officer.user_id

    def test_reassign_keeps_one_active(
        self,
        db_session,
        sample_coordinator,
        second_officer,
        sample_alert,
        sample_assignment,
    ):
        alert_assignment_service.assign_alert(
            db_session, sample_coordinator, assign_body(sample_alert, second_officer)
        )

        active = alert_assignment_service.list_assignments(
            db_session,
            sample_coordinator,
            alert_id=sample_alert.alert_id,
            active_only=True,
        )

        assert [assignment.officer_id for assignment in active] == [
            second_officer.user_id
        ]

    def test_assign_same_officer_twice(
        self,
        db_session,
        sample_coordinator,
        sample_officer,
        sample_alert,
        sample_assignment,
    ):
        with pytest.raises(HTTPException) as error:
            alert_assignment_service.assign_alert(
                db_session,
                sample_coordinator,
                assign_body(sample_alert, sample_officer),
            )

        assert error.value.status_code == 409

    def test_assign_after_failed_assignment(
        self,
        db_session,
        sample_coordinator,
        sample_officer,
        sample_alert,
        sample_assignment,
    ):
        alert_assignment_service.mark_failed(
            db_session, sample_coordinator, sample_assignment.assignment_id
        )

        again = alert_assignment_service.assign_alert(
            db_session, sample_coordinator, assign_body(sample_alert, sample_officer)
        )

        assert again.status == AssignmentStatus.ASSIGNED
        assert again.assignment_id != sample_assignment.assignment_id

    def test_assign_unknown_alert(self, db_session, sample_coordinator, sample_officer):
        body = AlertAssignmentCreate(
            alert_id=uuid.uuid4(), officer_id=sample_officer.user_id
        )

        with pytest.raises(HTTPException) as error:
            alert_assignment_service.assign_alert(db_session, sample_coordinator, body)

        assert error.value.status_code == 404

    def test_assign_unknown_officer(self, db_session, sample_coordinator, sample_alert):
        body = AlertAssignmentCreate(
            alert_id=sample_alert.alert_id, officer_id=uuid.uuid4()
        )

        with pytest.raises(HTTPException) as error:
            alert_assignment_service.assign_alert(db_session, sample_coordinator, body)

        assert error.value.status_code == 404

    def test_assign_to_coordinator_rejected(
        self, db_session, sample_coordinator, sample_alert
    ):
        with pytest.raises(HTTPException) as error:
            alert_assignment_service.assign_alert(
                db_session,
                sample_coordinator,
                assign_body(sample_alert, sample_coordinator),
            )

        assert error.value.status_code == 400

    def test_assign_to_inactive_officer_rejected(
        self, db_session, sample_coordinator, sample_officer, sample_alert
    ):
        sample_officer.is_active = False
        db_session.commit()

        with pytest.raises(HTTPException) as error:
            alert_assignment_service.assign_alert(
                db_session,
                sample_coordinator,
                assign_body(sample_alert, sample_officer),
            )

        assert error.value.status_code == 400

    @pytest.mark.parametrize(
        "closed_status", [AlertStatus.DISMISSED, AlertStatus.CLOSED]
    )
    def test_assign_finished_alert_rejected(
        self,
        db_session,
        sample_coordinator,
        sample_officer,
        sample_alert,
        closed_status,
    ):
        sample_alert.status = closed_status
        db_session.commit()

        with pytest.raises(HTTPException) as error:
            alert_assignment_service.assign_alert(
                db_session,
                sample_coordinator,
                assign_body(sample_alert, sample_officer),
            )

        assert error.value.status_code == 409

    def test_assign_by_officer_refused(self, db_session, sample_officer, sample_alert):
        with pytest.raises(HTTPException) as error:
            alert_assignment_service.assign_alert(
                db_session, sample_officer, assign_body(sample_alert, sample_officer)
            )

        assert error.value.status_code == 403

    def test_assign_by_inactive_coordinator_refused(
        self, db_session, sample_coordinator, sample_officer, sample_alert
    ):
        sample_coordinator.is_active = False

        with pytest.raises(HTTPException) as error:
            alert_assignment_service.assign_alert(
                db_session,
                sample_coordinator,
                assign_body(sample_alert, sample_officer),
            )

        assert error.value.status_code == 403

    def test_assign_without_user_refused(
        self, db_session, sample_officer, sample_alert
    ):
        with pytest.raises(HTTPException) as error:
            alert_assignment_service.assign_alert(
                db_session, None, assign_body(sample_alert, sample_officer)
            )

        assert error.value.status_code == 403

    # ---- get
    def test_get_as_coordinator(
        self, db_session, sample_coordinator, sample_assignment
    ):
        found = alert_assignment_service.get_assignment(
            db_session, sample_coordinator, sample_assignment.assignment_id
        )

        assert found.assignment_id == sample_assignment.assignment_id

    def test_get_own_as_officer(self, db_session, sample_officer, sample_assignment):
        found = alert_assignment_service.get_assignment(
            db_session, sample_officer, sample_assignment.assignment_id
        )

        assert found.officer_id == sample_officer.user_id

    def test_get_other_officers_hidden(
        self, db_session, second_officer, sample_assignment
    ):
        with pytest.raises(HTTPException) as error:
            alert_assignment_service.get_assignment(
                db_session, second_officer, sample_assignment.assignment_id
            )

        assert error.value.status_code == 404

    def test_get_unknown(self, db_session, sample_coordinator):
        with pytest.raises(HTTPException) as error:
            alert_assignment_service.get_assignment(
                db_session, sample_coordinator, uuid.uuid4()
            )

        assert error.value.status_code == 404

    def test_get_without_user(self, db_session, sample_assignment):
        with pytest.raises(HTTPException) as error:
            alert_assignment_service.get_assignment(
                db_session, None, sample_assignment.assignment_id
            )

        assert error.value.status_code == 403

    # ---- list
    def test_list_coordinator_sees_all(
        self,
        db_session,
        sample_coordinator,
        sample_alert,
        sample_officer,
        second_officer,
    ):
        make_assignment(db_session, sample_alert, sample_officer, sample_coordinator)
        make_assignment(db_session, sample_alert, second_officer, sample_coordinator)

        assert (
            len(
                alert_assignment_service.list_assignments(
                    db_session, sample_coordinator
                )
            )
            == 2
        )

    def test_list_officer_sees_own(
        self,
        db_session,
        sample_coordinator,
        sample_alert,
        sample_officer,
        second_officer,
    ):
        make_assignment(db_session, sample_alert, sample_officer, sample_coordinator)
        make_assignment(db_session, sample_alert, second_officer, sample_coordinator)

        results = alert_assignment_service.list_assignments(db_session, sample_officer)

        assert [assignment.officer_id for assignment in results] == [
            sample_officer.user_id
        ]

    def test_list_officer_cannot_ask_for_others(
        self,
        db_session,
        sample_coordinator,
        sample_alert,
        sample_officer,
        second_officer,
    ):
        make_assignment(db_session, sample_alert, sample_officer, sample_coordinator)

        results = alert_assignment_service.list_assignments(
            db_session, second_officer, officer_id=sample_officer.user_id
        )

        assert results == []

    def test_list_filter_by_officer(
        self,
        db_session,
        sample_coordinator,
        sample_alert,
        sample_officer,
        second_officer,
    ):
        make_assignment(db_session, sample_alert, sample_officer, sample_coordinator)
        wanted = make_assignment(
            db_session, sample_alert, second_officer, sample_coordinator
        )

        results = alert_assignment_service.list_assignments(
            db_session, sample_coordinator, officer_id=second_officer.user_id
        )

        assert [assignment.assignment_id for assignment in results] == [
            wanted.assignment_id
        ]

    def test_list_filter_by_alert(
        self,
        db_session,
        sample_coordinator,
        sample_alert,
        sample_officer,
        sample_zone,
        sample_reading,
    ):
        other_alert = make_second_alert(db_session, sample_zone, sample_reading)
        wanted = make_assignment(
            db_session, sample_alert, sample_officer, sample_coordinator
        )
        make_assignment(db_session, other_alert, sample_officer, sample_coordinator)

        results = alert_assignment_service.list_assignments(
            db_session, sample_coordinator, alert_id=sample_alert.alert_id
        )

        assert [assignment.assignment_id for assignment in results] == [
            wanted.assignment_id
        ]

    @pytest.mark.parametrize("assignment_status", list(AssignmentStatus))
    def test_list_filter_by_status(
        self,
        db_session,
        sample_coordinator,
        sample_alert,
        sample_officer,
        assignment_status,
    ):
        for each in AssignmentStatus:
            make_assignment(
                db_session,
                sample_alert,
                sample_officer,
                sample_coordinator,
                status=each,
            )

        results = alert_assignment_service.list_assignments(
            db_session, sample_coordinator, assignment_status=assignment_status
        )

        assert [assignment.status for assignment in results] == [assignment_status]

    def test_list_active_only(
        self, db_session, sample_coordinator, sample_alert, sample_officer
    ):
        make_assignment(
            db_session,
            sample_alert,
            sample_officer,
            sample_coordinator,
            ended_at=datetime.now(timezone.utc),
        )
        open_one = make_assignment(
            db_session, sample_alert, sample_officer, sample_coordinator
        )

        results = alert_assignment_service.list_assignments(
            db_session, sample_coordinator, active_only=True
        )

        assert [assignment.assignment_id for assignment in results] == [
            open_one.assignment_id
        ]

    def test_list_newest_first(
        self, db_session, sample_coordinator, sample_alert, sample_officer
    ):
        old = make_assignment(
            db_session, sample_alert, sample_officer, sample_coordinator, minutes_ago=60
        )
        new = make_assignment(
            db_session, sample_alert, sample_officer, sample_coordinator, minutes_ago=1
        )

        results = alert_assignment_service.list_assignments(
            db_session, sample_coordinator
        )

        assert [assignment.assignment_id for assignment in results] == [
            new.assignment_id,
            old.assignment_id,
        ]

    @pytest.mark.parametrize(
        "limit, offset, expected",
        [(1, 0, 1), (2, 0, 2), (50, 0, 3), (2, 2, 1), (10, 3, 0)],
    )
    def test_list_paging(
        self,
        db_session,
        sample_coordinator,
        sample_alert,
        sample_officer,
        limit,
        offset,
        expected,
    ):
        for minutes in range(3):
            make_assignment(
                db_session,
                sample_alert,
                sample_officer,
                sample_coordinator,
                minutes_ago=minutes,
            )

        results = alert_assignment_service.list_assignments(
            db_session, sample_coordinator, limit=limit, offset=offset
        )

        assert len(results) == expected

    def test_list_empty(self, db_session, sample_coordinator):
        assert (
            alert_assignment_service.list_assignments(db_session, sample_coordinator)
            == []
        )

    def test_list_without_user(self, db_session):
        with pytest.raises(HTTPException) as error:
            alert_assignment_service.list_assignments(db_session, None)

        assert error.value.status_code == 403

    # ---- acknowledge
    def test_acknowledge_own(
        self, db_session, sample_officer, sample_alert, sample_assignment
    ):
        result = alert_assignment_service.acknowledge(
            db_session, sample_officer, sample_assignment.assignment_id
        )

        assert result.status == AssignmentStatus.ACKNOWLEDGED
        assert result.acknowledged_at is not None
        assert sample_alert.assignment_status == AssignmentStatus.ACKNOWLEDGED

    def test_acknowledge_twice(self, db_session, sample_officer, sample_assignment):
        alert_assignment_service.acknowledge(
            db_session, sample_officer, sample_assignment.assignment_id
        )

        with pytest.raises(HTTPException) as error:
            alert_assignment_service.acknowledge(
                db_session, sample_officer, sample_assignment.assignment_id
            )

        assert error.value.status_code == 409

    def test_acknowledge_other_officers(
        self, db_session, second_officer, sample_assignment
    ):
        with pytest.raises(HTTPException) as error:
            alert_assignment_service.acknowledge(
                db_session, second_officer, sample_assignment.assignment_id
            )

        assert error.value.status_code == 404

    def test_acknowledge_ended(self, db_session, sample_officer, sample_assignment):
        sample_assignment.ended_at = datetime.now(timezone.utc)
        db_session.commit()

        with pytest.raises(HTTPException) as error:
            alert_assignment_service.acknowledge(
                db_session, sample_officer, sample_assignment.assignment_id
            )

        assert error.value.status_code == 409

    @pytest.mark.parametrize(
        "current", [AssignmentStatus.REPORTED, AssignmentStatus.FAILED]
    )
    def test_acknowledge_wrong_status(
        self, db_session, sample_officer, sample_assignment, current
    ):
        sample_assignment.status = current
        db_session.commit()

        with pytest.raises(HTTPException) as error:
            alert_assignment_service.acknowledge(
                db_session, sample_officer, sample_assignment.assignment_id
            )

        assert error.value.status_code == 409

    def test_acknowledge_by_coordinator(
        self, db_session, sample_coordinator, sample_assignment
    ):
        with pytest.raises(HTTPException) as error:
            alert_assignment_service.acknowledge(
                db_session, sample_coordinator, sample_assignment.assignment_id
            )

        assert error.value.status_code == 403

    def test_acknowledge_unknown(self, db_session, sample_officer):
        with pytest.raises(HTTPException) as error:
            alert_assignment_service.acknowledge(
                db_session, sample_officer, uuid.uuid4()
            )

        assert error.value.status_code == 404

    # ---- mark failed
    def test_mark_failed(
        self, db_session, sample_coordinator, sample_alert, sample_assignment
    ):
        result = alert_assignment_service.mark_failed(
            db_session, sample_coordinator, sample_assignment.assignment_id
        )

        assert result.status == AssignmentStatus.FAILED
        assert result.ended_at is not None
        assert sample_alert.officer_id is None
        assert sample_alert.assignment_status == AssignmentStatus.FAILED

    def test_mark_failed_after_acknowledge(
        self, db_session, sample_coordinator, sample_officer, sample_assignment
    ):
        alert_assignment_service.acknowledge(
            db_session, sample_officer, sample_assignment.assignment_id
        )

        result = alert_assignment_service.mark_failed(
            db_session, sample_coordinator, sample_assignment.assignment_id
        )

        assert result.status == AssignmentStatus.FAILED

    def test_mark_failed_twice(self, db_session, sample_coordinator, sample_assignment):
        alert_assignment_service.mark_failed(
            db_session, sample_coordinator, sample_assignment.assignment_id
        )

        with pytest.raises(HTTPException) as error:
            alert_assignment_service.mark_failed(
                db_session, sample_coordinator, sample_assignment.assignment_id
            )

        assert error.value.status_code == 409

    def test_mark_failed_reported(
        self, db_session, sample_coordinator, sample_assignment
    ):
        sample_assignment.status = AssignmentStatus.REPORTED
        db_session.commit()

        with pytest.raises(HTTPException) as error:
            alert_assignment_service.mark_failed(
                db_session, sample_coordinator, sample_assignment.assignment_id
            )

        assert error.value.status_code == 409

    def test_mark_failed_by_officer(
        self, db_session, sample_officer, sample_assignment
    ):
        with pytest.raises(HTTPException) as error:
            alert_assignment_service.mark_failed(
                db_session, sample_officer, sample_assignment.assignment_id
            )

        assert error.value.status_code == 403

    def test_mark_failed_unknown(self, db_session, sample_coordinator):
        with pytest.raises(HTTPException) as error:
            alert_assignment_service.mark_failed(
                db_session, sample_coordinator, uuid.uuid4()
            )

        assert error.value.status_code == 404

    # ---- positive cases
    @pytest.mark.parametrize(
        "start_status, end_status",
        [
            (AlertStatus.NEW, AlertStatus.IN_PROGRESS),
            (AlertStatus.IN_PROGRESS, AlertStatus.IN_PROGRESS),
        ],
    )
    def test_service_assign_alert_status_change(
        self,
        db_session,
        sample_coordinator,
        sample_officer,
        sample_alert,
        start_status,
        end_status,
    ):
        sample_alert.status = start_status
        db_session.commit()

        alert_assignment_service.assign_alert(
            db_session, sample_coordinator, assign_body(sample_alert, sample_officer)
        )

        assert sample_alert.status == end_status

    def test_service_assign_times_match(
        self, db_session, sample_coordinator, sample_officer, sample_alert
    ):
        assignment = alert_assignment_service.assign_alert(
            db_session, sample_coordinator, assign_body(sample_alert, sample_officer)
        )

        assert assignment.assigned_at == sample_alert.assigned_at

    def test_service_officer_can_hold_two_alerts(
        self,
        db_session,
        sample_coordinator,
        sample_officer,
        sample_alert,
        sample_zone,
        sample_reading,
    ):
        other_alert = make_second_alert(db_session, sample_zone, sample_reading)

        alert_assignment_service.assign_alert(
            db_session, sample_coordinator, assign_body(sample_alert, sample_officer)
        )
        alert_assignment_service.assign_alert(
            db_session, sample_coordinator, assign_body(other_alert, sample_officer)
        )

        active = alert_assignment_service.list_assignments(
            db_session, sample_officer, active_only=True
        )

        assert {assignment.alert_id for assignment in active} == {
            sample_alert.alert_id,
            other_alert.alert_id,
        }

    # ---- edge cases
    def test_service_reassign_back_and_forth(
        self,
        db_session,
        sample_coordinator,
        sample_officer,
        second_officer,
        sample_alert,
        sample_assignment,
    ):
        alert_assignment_service.assign_alert(
            db_session, sample_coordinator, assign_body(sample_alert, second_officer)
        )
        alert_assignment_service.assign_alert(
            db_session, sample_coordinator, assign_body(sample_alert, sample_officer)
        )

        history = alert_assignment_service.list_assignments(
            db_session, sample_coordinator, alert_id=sample_alert.alert_id
        )
        active = [assignment for assignment in history if assignment.ended_at is None]

        assert len(history) == 3
        assert [assignment.officer_id for assignment in active] == [
            sample_officer.user_id
        ]
        assert sorted(assignment.status.value for assignment in history) == [
            "assigned",
            "reassigned",
            "reassigned",
        ]

    def test_service_reassign_after_acknowledge(
        self,
        db_session,
        sample_coordinator,
        sample_officer,
        second_officer,
        sample_alert,
        sample_assignment,
    ):
        alert_assignment_service.acknowledge(
            db_session, sample_officer, sample_assignment.assignment_id
        )

        alert_assignment_service.assign_alert(
            db_session, sample_coordinator, assign_body(sample_alert, second_officer)
        )
        db_session.refresh(sample_assignment)

        assert sample_assignment.status == AssignmentStatus.REASSIGNED
        assert sample_assignment.acknowledged_at is not None

    def test_service_reassign_clears_reported_time(
        self,
        db_session,
        sample_coordinator,
        second_officer,
        sample_alert,
        sample_assignment,
    ):
        sample_alert.reported_at = datetime.now(timezone.utc)
        db_session.commit()

        alert_assignment_service.assign_alert(
            db_session, sample_coordinator, assign_body(sample_alert, second_officer)
        )

        assert sample_alert.reported_at is None
        assert sample_alert.assignment_status == AssignmentStatus.ASSIGNED

    def test_service_failed_assignment_stays_failed(
        self,
        db_session,
        sample_coordinator,
        second_officer,
        sample_alert,
        sample_assignment,
    ):
        alert_assignment_service.mark_failed(
            db_session, sample_coordinator, sample_assignment.assignment_id
        )

        alert_assignment_service.assign_alert(
            db_session, sample_coordinator, assign_body(sample_alert, second_officer)
        )
        db_session.refresh(sample_assignment)

        assert sample_assignment.status == AssignmentStatus.FAILED

    def test_service_mark_failed_keeps_alert_in_progress(
        self, db_session, sample_coordinator, sample_alert, sample_assignment
    ):
        alert_assignment_service.mark_failed(
            db_session, sample_coordinator, sample_assignment.assignment_id
        )

        assert sample_alert.status == AlertStatus.IN_PROGRESS

    def test_service_acknowledge_keeps_assignment_open(
        self, db_session, sample_officer, sample_assignment
    ):
        result = alert_assignment_service.acknowledge(
            db_session, sample_officer, sample_assignment.assignment_id
        )

        assert result.ended_at is None

    def test_service_acknowledge_after_failed(
        self, db_session, sample_coordinator, sample_officer, sample_assignment
    ):
        alert_assignment_service.mark_failed(
            db_session, sample_coordinator, sample_assignment.assignment_id
        )

        with pytest.raises(HTTPException) as error:
            alert_assignment_service.acknowledge(
                db_session, sample_officer, sample_assignment.assignment_id
            )

        assert error.value.status_code == 409

    # ---- negative: inactive or missing users for every action
    def test_service_acknowledge_inactive_officer(
        self, db_session, sample_officer, sample_assignment
    ):
        sample_officer.is_active = False

        with pytest.raises(HTTPException) as error:
            alert_assignment_service.acknowledge(
                db_session, sample_officer, sample_assignment.assignment_id
            )

        assert error.value.status_code == 403

    def test_service_acknowledge_without_user(self, db_session, sample_assignment):
        with pytest.raises(HTTPException) as error:
            alert_assignment_service.acknowledge(
                db_session, None, sample_assignment.assignment_id
            )

        assert error.value.status_code == 403

    def test_service_mark_failed_inactive_coordinator(
        self, db_session, sample_coordinator, sample_assignment
    ):
        sample_coordinator.is_active = False

        with pytest.raises(HTTPException) as error:
            alert_assignment_service.mark_failed(
                db_session, sample_coordinator, sample_assignment.assignment_id
            )

        assert error.value.status_code == 403

    def test_service_mark_failed_without_user(self, db_session, sample_assignment):
        with pytest.raises(HTTPException) as error:
            alert_assignment_service.mark_failed(
                db_session, None, sample_assignment.assignment_id
            )

        assert error.value.status_code == 403

    def test_service_get_inactive_user(
        self, db_session, sample_officer, sample_assignment
    ):
        sample_officer.is_active = False

        with pytest.raises(HTTPException) as error:
            alert_assignment_service.get_assignment(
                db_session, sample_officer, sample_assignment.assignment_id
            )

        assert error.value.status_code == 403

    def test_service_list_inactive_user(self, db_session, sample_officer):
        sample_officer.is_active = False

        with pytest.raises(HTTPException) as error:
            alert_assignment_service.list_assignments(db_session, sample_officer)

        assert error.value.status_code == 403

    # ---- positive cases
    def test_service_coordinator_sees_ended_assignment(
        self, db_session, sample_coordinator, sample_assignment
    ):
        alert_assignment_service.mark_failed(
            db_session, sample_coordinator, sample_assignment.assignment_id
        )

        found = alert_assignment_service.get_assignment(
            db_session, sample_coordinator, sample_assignment.assignment_id
        )

        assert found.status == AssignmentStatus.FAILED

    def test_service_list_all_filters_together(
        self,
        db_session,
        sample_coordinator,
        sample_officer,
        second_officer,
        sample_alert,
        sample_zone,
        sample_reading,
    ):
        other_alert = make_second_alert(db_session, sample_zone, sample_reading)
        wanted = make_assignment(
            db_session, sample_alert, sample_officer, sample_coordinator
        )
        make_assignment(db_session, sample_alert, second_officer, sample_coordinator)
        make_assignment(db_session, other_alert, sample_officer, sample_coordinator)
        make_assignment(
            db_session,
            sample_alert,
            sample_officer,
            sample_coordinator,
            ended_at=datetime.now(timezone.utc),
        )
        make_assignment(
            db_session,
            sample_alert,
            sample_officer,
            sample_coordinator,
            status=AssignmentStatus.ACKNOWLEDGED,
        )

        results = alert_assignment_service.list_assignments(
            db_session,
            sample_coordinator,
            alert_id=sample_alert.alert_id,
            officer_id=sample_officer.user_id,
            assignment_status=AssignmentStatus.ASSIGNED,
            active_only=True,
        )

        assert [assignment.assignment_id for assignment in results] == [
            wanted.assignment_id
        ]

    def test_service_officer_filter_by_alert(
        self,
        db_session,
        sample_coordinator,
        sample_officer,
        sample_alert,
        sample_zone,
        sample_reading,
    ):
        other_alert = make_second_alert(db_session, sample_zone, sample_reading)
        make_assignment(db_session, sample_alert, sample_officer, sample_coordinator)
        wanted = make_assignment(
            db_session, other_alert, sample_officer, sample_coordinator
        )

        results = alert_assignment_service.list_assignments(
            db_session, sample_officer, alert_id=other_alert.alert_id
        )

        assert [assignment.assignment_id for assignment in results] == [
            wanted.assignment_id
        ]

    @pytest.mark.parametrize(
        "offset, expected", [(0, 4), (1, 3), (3, 1), (4, 0), (100, 0)]
    )
    def test_service_offset_boundaries(
        self,
        db_session,
        sample_coordinator,
        sample_officer,
        sample_alert,
        offset,
        expected,
    ):
        for minutes in range(4):
            make_assignment(
                db_session,
                sample_alert,
                sample_officer,
                sample_coordinator,
                minutes_ago=minutes,
            )

        results = alert_assignment_service.list_assignments(
            db_session, sample_coordinator, offset=offset
        )

        assert len(results) == expected


class TestAlertAssignmentRouter:
    # ---- POST assign
    def test_assign(
        self, assignment_client, sample_coordinator, sample_officer, sample_alert
    ):
        response = assignment_client.post(
            ASSIGN_API,
            json={
                "alert_id": str(sample_alert.alert_id),
                "officer_id": str(sample_officer.user_id),
            },
            headers=assignment_headers(sample_coordinator),
        )

        assert response.status_code == 201
        assert response.json()["officer_id"] == str(sample_officer.user_id)
        assert response.json()["assigned_by"] == str(sample_coordinator.user_id)
        assert response.json()["status"] == "assigned"

    def test_assign_response_fields(
        self, assignment_client, sample_coordinator, sample_officer, sample_alert
    ):
        response = assignment_client.post(
            ASSIGN_API,
            json={
                "alert_id": str(sample_alert.alert_id),
                "officer_id": str(sample_officer.user_id),
            },
            headers=assignment_headers(sample_coordinator),
        )

        assert set(response.json()) == {
            "assignment_id",
            "alert_id",
            "officer_id",
            "assigned_by",
            "status",
            "assigned_at",
            "acknowledged_at",
            "reported_at",
            "ended_at",
        }

    def test_reassign(
        self,
        assignment_client,
        sample_coordinator,
        second_officer,
        sample_alert,
        sample_assignment,
    ):
        response = assignment_client.post(
            ASSIGN_API,
            json={
                "alert_id": str(sample_alert.alert_id),
                "officer_id": str(second_officer.user_id),
            },
            headers=assignment_headers(sample_coordinator),
        )

        assert response.status_code == 201
        assert response.json()["officer_id"] == str(second_officer.user_id)

    def test_assign_same_officer_twice(
        self,
        assignment_client,
        sample_coordinator,
        sample_officer,
        sample_alert,
        sample_assignment,
    ):
        response = assignment_client.post(
            ASSIGN_API,
            json={
                "alert_id": str(sample_alert.alert_id),
                "officer_id": str(sample_officer.user_id),
            },
            headers=assignment_headers(sample_coordinator),
        )

        assert response.status_code == 409

    def test_assign_unknown_alert(
        self, assignment_client, sample_coordinator, sample_officer
    ):
        response = assignment_client.post(
            ASSIGN_API,
            json={
                "alert_id": str(uuid.uuid4()),
                "officer_id": str(sample_officer.user_id),
            },
            headers=assignment_headers(sample_coordinator),
        )

        assert response.status_code == 404

    def test_assign_to_coordinator(
        self, assignment_client, sample_coordinator, sample_alert
    ):
        response = assignment_client.post(
            ASSIGN_API,
            json={
                "alert_id": str(sample_alert.alert_id),
                "officer_id": str(sample_coordinator.user_id),
            },
            headers=assignment_headers(sample_coordinator),
        )

        assert response.status_code == 400

    def test_assign_by_officer(self, assignment_client, sample_officer, sample_alert):
        response = assignment_client.post(
            ASSIGN_API,
            json={
                "alert_id": str(sample_alert.alert_id),
                "officer_id": str(sample_officer.user_id),
            },
            headers=assignment_headers(sample_officer),
        )

        assert response.status_code == 403

    def test_assign_requires_login(
        self, assignment_client, sample_officer, sample_alert
    ):
        response = assignment_client.post(
            ASSIGN_API,
            json={
                "alert_id": str(sample_alert.alert_id),
                "officer_id": str(sample_officer.user_id),
            },
        )

        assert response.status_code == 401

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"alert_id": "abc", "officer_id": "def"},
            {"officer_id": "00000000-0000-0000-0000-000000000000"},
            {"alert_id": "00000000-0000-0000-0000-000000000000"},
            {
                "alert_id": "00000000-0000-0000-0000-000000000000",
                "officer_id": "00000000-0000-0000-0000-000000000000",
                "status": "reported",
            },
        ],
    )
    def test_assign_bad_body(self, assignment_client, sample_coordinator, body):
        response = assignment_client.post(
            ASSIGN_API, json=body, headers=assignment_headers(sample_coordinator)
        )

        assert response.status_code == 422

    # ---- GET list
    def test_list_as_coordinator(
        self, assignment_client, sample_coordinator, sample_assignment
    ):
        response = assignment_client.get(
            ASSIGN_API, headers=assignment_headers(sample_coordinator)
        )

        assert response.status_code == 200
        assert [item["assignment_id"] for item in response.json()] == [
            str(sample_assignment.assignment_id)
        ]

    def test_list_as_officer_own_only(
        self,
        assignment_client,
        db_session,
        sample_officer,
        second_officer,
        sample_alert,
        sample_coordinator,
    ):
        make_assignment(db_session, sample_alert, sample_officer, sample_coordinator)
        make_assignment(db_session, sample_alert, second_officer, sample_coordinator)

        response = assignment_client.get(
            ASSIGN_API, headers=assignment_headers(second_officer)
        )

        assert [item["officer_id"] for item in response.json()] == [
            str(second_officer.user_id)
        ]

    def test_list_filter_by_status(
        self, assignment_client, sample_coordinator, sample_assignment
    ):
        assigned = assignment_client.get(
            ASSIGN_API,
            params={"status": "assigned"},
            headers=assignment_headers(sample_coordinator),
        )
        failed = assignment_client.get(
            ASSIGN_API,
            params={"status": "failed"},
            headers=assignment_headers(sample_coordinator),
        )

        assert len(assigned.json()) == 1
        assert failed.json() == []

    def test_list_active_only(
        self,
        assignment_client,
        db_session,
        sample_coordinator,
        sample_officer,
        sample_alert,
    ):
        make_assignment(
            db_session,
            sample_alert,
            sample_officer,
            sample_coordinator,
            ended_at=datetime.now(timezone.utc),
        )
        make_assignment(db_session, sample_alert, sample_officer, sample_coordinator)

        response = assignment_client.get(
            ASSIGN_API,
            params={"active_only": True},
            headers=assignment_headers(sample_coordinator),
        )

        assert len(response.json()) == 1
        assert response.json()[0]["ended_at"] is None

    @pytest.mark.parametrize(
        "params",
        [
            {"limit": 0},
            {"limit": 201},
            {"offset": -1},
            {"status": "on_holiday"},
            {"alert_id": "abc"},
        ],
    )
    def test_list_bad_query(self, assignment_client, sample_coordinator, params):
        response = assignment_client.get(
            ASSIGN_API, params=params, headers=assignment_headers(sample_coordinator)
        )

        assert response.status_code == 422

    def test_list_requires_login(self, assignment_client):
        assert assignment_client.get(ASSIGN_API).status_code == 401

    def test_get_one(self, assignment_client, sample_officer, sample_assignment):
        response = assignment_client.get(
            f"{ASSIGN_API}/{sample_assignment.assignment_id}",
            headers=assignment_headers(sample_officer),
        )

        assert response.status_code == 200
        assert response.json()["assignment_id"] == str(sample_assignment.assignment_id)

    def test_get_other_officers(
        self, assignment_client, second_officer, sample_assignment
    ):
        response = assignment_client.get(
            f"{ASSIGN_API}/{sample_assignment.assignment_id}",
            headers=assignment_headers(second_officer),
        )

        assert response.status_code == 404

    def test_get_unknown(self, assignment_client, sample_coordinator):
        response = assignment_client.get(
            f"{ASSIGN_API}/{uuid.uuid4()}",
            headers=assignment_headers(sample_coordinator),
        )

        assert response.status_code == 404

    def test_get_bad_id(self, assignment_client, sample_coordinator):
        response = assignment_client.get(
            f"{ASSIGN_API}/abc", headers=assignment_headers(sample_coordinator)
        )

        assert response.status_code == 422

    def test_acknowledge(self, assignment_client, sample_officer, sample_assignment):
        response = assignment_client.post(
            f"{ASSIGN_API}/acknowledge/{sample_assignment.alert_id}",
            headers=assignment_headers(sample_officer),
        )
        assert response.status_code == 200

    def test_acknowledge_by_coordinator(
        self, assignment_client, sample_coordinator, sample_assignment
    ):
        response = assignment_client.post(
            f"{ASSIGN_API}/acknowledge/{sample_assignment.alert_id}",
            headers=assignment_headers(sample_coordinator),
        )
        assert response.status_code == 403

    def test_acknowledge_twice(
        self, assignment_client, sample_officer, sample_assignment
    ):
        url = f"{ASSIGN_API}/acknowledge/{sample_assignment.alert_id}"
        assignment_client.post(url, headers=assignment_headers(sample_officer))

        assert (
            assignment_client.post(
                url, headers=assignment_headers(sample_officer)
            ).status_code
            == 409
        )

    def test_mark_failed(
        self, assignment_client, sample_coordinator, sample_assignment
    ):
        response = assignment_client.post(
            f"{ASSIGN_API}/{sample_assignment.assignment_id}/fail",
            headers=assignment_headers(sample_coordinator),
        )

        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        assert response.json()["ended_at"] is not None

    def test_mark_failed_by_officer(
        self, assignment_client, sample_officer, sample_assignment
    ):
        response = assignment_client.post(
            f"{ASSIGN_API}/{sample_assignment.assignment_id}/fail",
            headers=assignment_headers(sample_officer),
        )

        assert response.status_code == 403

    def test_mark_failed_twice(
        self, assignment_client, sample_coordinator, sample_assignment
    ):
        url = f"{ASSIGN_API}/{sample_assignment.assignment_id}/fail"
        assignment_client.post(url, headers=assignment_headers(sample_coordinator))

        assert (
            assignment_client.post(
                url, headers=assignment_headers(sample_coordinator)
            ).status_code
            == 409
        )

    @pytest.mark.parametrize("method", ["put", "patch", "delete"])
    def test_assignments_cannot_be_edited_or_deleted(
        self, assignment_client, sample_coordinator, sample_assignment, method
    ):
        response = getattr(assignment_client, method)(
            f"{ASSIGN_API}/{sample_assignment.assignment_id}",
            headers=assignment_headers(sample_coordinator),
        )

        assert response.status_code == 405

    def test_router_assign_times(
        self, assignment_client, sample_coordinator, sample_officer, sample_alert
    ):
        response = assignment_client.post(
            ASSIGN_API,
            json={
                "alert_id": str(sample_alert.alert_id),
                "officer_id": str(sample_officer.user_id),
            },
            headers=assignment_headers(sample_coordinator),
        )

        assert response.json()["assigned_at"] is not None
        assert response.json()["acknowledged_at"] is None
        assert response.json()["ended_at"] is None

    def test_router_list_response_fields(
        self, assignment_client, sample_coordinator, sample_assignment
    ):
        item = assignment_client.get(
            ASSIGN_API, headers=assignment_headers(sample_coordinator)
        ).json()[0]

        assert set(item) == {
            "assignment_id",
            "alert_id",
            "officer_id",
            "assigned_by",
            "status",
            "assigned_at",
            "acknowledged_at",
            "reported_at",
            "ended_at",
        }

    def test_router_list_filter_by_officer(
        self,
        assignment_client,
        db_session,
        sample_coordinator,
        sample_officer,
        second_officer,
        sample_alert,
    ):
        make_assignment(db_session, sample_alert, sample_officer, sample_coordinator)
        make_assignment(db_session, sample_alert, second_officer, sample_coordinator)

        response = assignment_client.get(
            ASSIGN_API,
            params={"officer_id": str(second_officer.user_id)},
            headers=assignment_headers(sample_coordinator),
        )

        assert [item["officer_id"] for item in response.json()] == [
            str(second_officer.user_id)
        ]

    def test_router_list_filter_by_alert(
        self,
        assignment_client,
        db_session,
        sample_coordinator,
        sample_officer,
        sample_alert,
        sample_zone,
        sample_reading,
    ):
        other_alert = make_second_alert(db_session, sample_zone, sample_reading)
        make_assignment(db_session, sample_alert, sample_officer, sample_coordinator)
        make_assignment(db_session, other_alert, sample_officer, sample_coordinator)

        response = assignment_client.get(
            ASSIGN_API,
            params={"alert_id": str(other_alert.alert_id)},
            headers=assignment_headers(sample_coordinator),
        )

        assert [item["alert_id"] for item in response.json()] == [
            str(other_alert.alert_id)
        ]

    @pytest.mark.parametrize(
        "params, expected", [({"limit": 1}, 1), ({"limit": 200}, 2), ({"offset": 2}, 0)]
    )
    def test_router_list_paging_limits(
        self,
        assignment_client,
        db_session,
        sample_coordinator,
        sample_officer,
        sample_alert,
        params,
        expected,
    ):
        make_assignment(db_session, sample_alert, sample_officer, sample_coordinator)
        make_assignment(
            db_session, sample_alert, sample_officer, sample_coordinator, minutes_ago=5
        )

        response = assignment_client.get(
            ASSIGN_API, params=params, headers=assignment_headers(sample_coordinator)
        )

        assert response.status_code == 200
        assert len(response.json()) == expected

    def test_router_get_as_coordinator(
        self, assignment_client, sample_coordinator, sample_assignment
    ):
        response = assignment_client.get(
            f"{ASSIGN_API}/{sample_assignment.assignment_id}",
            headers=assignment_headers(sample_coordinator),
        )

        assert response.status_code == 200

    @pytest.mark.parametrize(
        "closed_status", [AlertStatus.DISMISSED, AlertStatus.CLOSED]
    )
    def test_router_assign_finished_alert(
        self,
        assignment_client,
        db_session,
        sample_coordinator,
        sample_officer,
        sample_alert,
        closed_status,
    ):
        sample_alert.status = closed_status
        db_session.commit()

        response = assignment_client.post(
            ASSIGN_API,
            json={
                "alert_id": str(sample_alert.alert_id),
                "officer_id": str(sample_officer.user_id),
            },
            headers=assignment_headers(sample_coordinator),
        )

        assert response.status_code == 409

    def test_router_assign_inactive_officer(
        self,
        assignment_client,
        db_session,
        sample_coordinator,
        sample_officer,
        sample_alert,
    ):
        sample_officer.is_active = False
        db_session.commit()

        response = assignment_client.post(
            ASSIGN_API,
            json={
                "alert_id": str(sample_alert.alert_id),
                "officer_id": str(sample_officer.user_id),
            },
            headers=assignment_headers(sample_coordinator),
        )

        assert response.status_code == 400

    def test_router_assign_unknown_officer(
        self, assignment_client, sample_coordinator, sample_alert
    ):
        response = assignment_client.post(
            ASSIGN_API,
            json={
                "alert_id": str(sample_alert.alert_id),
                "officer_id": str(uuid.uuid4()),
            },
            headers=assignment_headers(sample_coordinator),
        )

        assert response.status_code == 404

    def test_router_assign_not_json(self, assignment_client, sample_coordinator):
        headers = {
            **assignment_headers(sample_coordinator),
            "Content-Type": "application/json",
        }

        response = assignment_client.post(
            ASSIGN_API, content="assign Tendai please", headers=headers
        )

        assert response.status_code == 422

    def test_router_assign_inactive_coordinator(
        self,
        assignment_client,
        db_session,
        sample_coordinator,
        sample_officer,
        sample_alert,
    ):
        headers = assignment_headers(sample_coordinator)
        sample_coordinator.is_active = False
        db_session.commit()

        response = assignment_client.post(
            ASSIGN_API,
            json={
                "alert_id": str(sample_alert.alert_id),
                "officer_id": str(sample_officer.user_id),
            },
            headers=headers,
        )

        assert response.status_code == 401

    def test_router_acknowledge_requires_login(
        self, assignment_client, sample_assignment
    ):
        response = assignment_client.post(
            f"{ASSIGN_API}/acknowledge/{sample_assignment.alert_id}"
        )
        assert response.status_code == 401

    def test_router_acknowledge_unknown(self, assignment_client, sample_officer):
        response = assignment_client.post(
            f"{ASSIGN_API}/acknowledge/{uuid.uuid4()}",
            headers=assignment_headers(sample_officer),
        )

        assert response.status_code == 404

    def test_router_acknowledge_bad_id(self, assignment_client, sample_officer):
        response = assignment_client.post(
            f"{ASSIGN_API}/abc/acknowledge", headers=assignment_headers(sample_officer)
        )

        assert response.status_code == 422

    def test_router_acknowledge_after_failed(
        self, assignment_client, sample_coordinator, sample_officer, sample_assignment
    ):
        assignment_client.post(
            f"{ASSIGN_API}/{sample_assignment.assignment_id}/fail",
            headers=assignment_headers(sample_coordinator),
        )

        response = assignment_client.post(
            f"{ASSIGN_API}/acknowledge/{sample_assignment.alert_id}",
            headers=assignment_headers(sample_officer),
        )
        assert response.status_code == 404

    def test_router_fail_requires_login(self, assignment_client, sample_assignment):
        assert (
            assignment_client.post(
                f"{ASSIGN_API}/{sample_assignment.assignment_id}/fail"
            ).status_code
            == 401
        )

    def test_router_fail_unknown(self, assignment_client, sample_coordinator):
        response = assignment_client.post(
            f"{ASSIGN_API}/{uuid.uuid4()}/fail",
            headers=assignment_headers(sample_coordinator),
        )

        assert response.status_code == 404

    def test_router_acknowledge_bad_id(self, assignment_client, sample_officer):
        response = assignment_client.post(
            f"{ASSIGN_API}/acknowledge/abc", headers=assignment_headers(sample_officer)
        )
        assert response.status_code == 422

    def test_router_fail_reported(
        self, assignment_client, db_session, sample_coordinator, sample_assignment
    ):
        sample_assignment.status = AssignmentStatus.REPORTED
        db_session.commit()

        response = assignment_client.post(
            f"{ASSIGN_API}/{sample_assignment.assignment_id}/fail",
            headers=assignment_headers(sample_coordinator),
        )

        assert response.status_code == 409

    def test_router_get_requires_login(self, assignment_client, sample_assignment):
        assert (
            assignment_client.get(
                f"{ASSIGN_API}/{sample_assignment.assignment_id}"
            ).status_code
            == 401
        )

    @pytest.mark.parametrize("method", ["put", "patch", "delete"])
    def test_router_list_cannot_be_changed(
        self, assignment_client, sample_coordinator, method
    ):
        response = getattr(assignment_client, method)(
            ASSIGN_API, headers=assignment_headers(sample_coordinator)
        )

        assert response.status_code == 405

    @pytest.mark.parametrize("action", ["acknowledge", "fail"])
    @pytest.mark.parametrize("method", ["get", "put", "delete"])
    def test_router_actions_are_post_only(
        self, assignment_client, sample_coordinator, sample_assignment, action, method
    ):
        path = (
            f"{ASSIGN_API}/acknowledge/{sample_assignment.alert_id}"
            if action == "acknowledge"
            else f"{ASSIGN_API}/{sample_assignment.assignment_id}/fail"
        )

        response = getattr(assignment_client, method)(
            path,
            headers=assignment_headers(sample_coordinator),
        )
        assert response.status_code == 405
