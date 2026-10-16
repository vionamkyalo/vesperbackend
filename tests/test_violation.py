import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from models.violation_report import ReviewStatus, ViolationReport, ViolationType


class TestViolationReport:
    def test_create_violation_report_happy_path(
        self, db_session, sample_inspection, sample_coordinator
    ):
        violation_id = uuid.uuid4()
        recorded_at = datetime(2026, 10, 10, 23, 0, tzinfo=timezone.utc)
        reviewed_at = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)
        report = ViolationReport(
            violation_id=violation_id,
            inspection_id=sample_inspection.inspection_id,
            violation_type=ViolationType.UNREGISTERED_RIG,
            rig_identifier="Blue hull, no mark",
            description="Rig had no registration mark",
            review_status=ReviewStatus.REVIEWED,
            reviewed_by=sample_coordinator.user_id,
            reviewed_at=reviewed_at,
            recorded_at=recorded_at,
        )
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)

        assert report.violation_id == violation_id
        assert isinstance(report.violation_id, uuid.UUID)
        assert report.inspection_id == sample_inspection.inspection_id
        assert report.violation_type == ViolationType.UNREGISTERED_RIG
        assert report.rig_identifier == "Blue hull, no mark"
        assert report.description == "Rig had no registration mark"
        assert report.review_status == ReviewStatus.REVIEWED
        assert report.reviewed_by == sample_coordinator.user_id
        assert report.reviewed_at == reviewed_at
        assert report.recorded_at == recorded_at
        assert report.synced_at is not None

    def test_violation_report_optional_fields(self, db_session, sample_inspection):
        report = ViolationReport(
            violation_id=uuid.uuid4(),
            inspection_id=sample_inspection.inspection_id,
            violation_type=ViolationType.MISSING_PERMIT,
            rig_identifier="KR-1042",
            description="No permit on board",
            recorded_at=datetime(2026, 10, 10, 23, 0, tzinfo=timezone.utc),
        )
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)

        assert report.reviewed_by is None
        assert report.reviewed_at is None
        assert report.review_status == ReviewStatus.SUBMITTED
        assert report.synced_at is not None

    @pytest.mark.parametrize(
        "violation_type",
        [
            ViolationType.UNREGISTERED_RIG,
            ViolationType.MISSING_PERMIT,
            ViolationType.FISHING_IN_CLOSED_AREA,
            ViolationType.FISHING_DURING_CLOSURE,
            ViolationType.RIG_CAP_EXCEEDED,
            ViolationType.UNAUTHORIZED_GEAR,
        ],
    )
    def test_violation_report_type_values(
        self, db_session, sample_inspection, violation_type
    ):
        report = ViolationReport(
            violation_id=uuid.uuid4(),
            inspection_id=sample_inspection.inspection_id,
            violation_type=violation_type,
            rig_identifier="KR-1",
            description="Observed issue",
            recorded_at=datetime(2026, 10, 10, 23, 0, tzinfo=timezone.utc),
        )
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)

        assert report.violation_type == violation_type

    @pytest.mark.parametrize(
        "review_status",
        [
            ReviewStatus.SUBMITTED,
            ReviewStatus.REVIEWED,
        ],
    )
    def test_violation_report_review_status_values(
        self, db_session, sample_inspection, review_status
    ):
        report = ViolationReport(
            violation_id=uuid.uuid4(),
            inspection_id=sample_inspection.inspection_id,
            violation_type=ViolationType.MISSING_PERMIT,
            rig_identifier="KR-2",
            description="Observed issue",
            review_status=review_status,
            recorded_at=datetime(2026, 10, 10, 23, 0, tzinfo=timezone.utc),
        )
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)

        assert report.review_status == review_status

    def test_violation_report_missing_required_fields(self, db_session):
        report = ViolationReport(violation_id=uuid.uuid4())
        db_session.add(report)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_violation_report_missing_inspection_id(self, db_session):
        report = ViolationReport(
            violation_id=uuid.uuid4(),
            violation_type=ViolationType.MISSING_PERMIT,
            rig_identifier="KR-3",
            description="Observed issue",
            recorded_at=datetime(2026, 10, 10, 23, 0, tzinfo=timezone.utc),
        )
        db_session.add(report)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_violation_report_missing_rig_identifier(
        self, db_session, sample_inspection
    ):
        report = ViolationReport(
            violation_id=uuid.uuid4(),
            inspection_id=sample_inspection.inspection_id,
            violation_type=ViolationType.MISSING_PERMIT,
            description="Observed issue",
            recorded_at=datetime(2026, 10, 10, 23, 0, tzinfo=timezone.utc),
        )
        db_session.add(report)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_violation_report_unknown_inspection(self, db_session):
        report = ViolationReport(
            violation_id=uuid.uuid4(),
            inspection_id=uuid.uuid4(),
            violation_type=ViolationType.MISSING_PERMIT,
            rig_identifier="KR-4",
            description="Observed issue",
            recorded_at=datetime(2026, 10, 10, 23, 0, tzinfo=timezone.utc),
        )
        db_session.add(report)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_violation_report_inspection_relationship(
        self, db_session, sample_inspection, sample_violation
    ):
        db_session.refresh(sample_inspection)

        assert (
            sample_violation.inspection.inspection_id == sample_inspection.inspection_id
        )
        assert sample_violation in sample_inspection.violation_reports

    def test_violation_report_reviewer_relationship(
        self, db_session, sample_violation, sample_coordinator
    ):
        sample_violation.reviewed_by = sample_coordinator.user_id
        db_session.commit()
        db_session.refresh(sample_violation)

        assert sample_violation.reviewer.user_id == sample_coordinator.user_id
