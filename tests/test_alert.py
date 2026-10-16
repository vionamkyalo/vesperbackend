import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from models.alert import Alert, AlertStatus, VerificationResult
from models.alert_assignment import AssignmentStatus


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
