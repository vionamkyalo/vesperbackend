import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from models.alert_assignment import AlertAssignment, AssignmentStatus


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
