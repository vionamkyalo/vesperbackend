import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from database import utcnow
from models.user import User, UserRole
from models.violation_report import ReviewStatus, ViolationType
from schemas.violation_report import ViolationReportCreate
from services.violation_report import violation_report_service


from models import (  # noqa: F401
    alert,
    alert_assignment,
    catch_check,
    inspection,
    officer_assignment,
    user,
    violation_report,
    zone,
    zone_baseline,
    zone_light_reading,
    zone_setting_history,
)


def make_payload(inspection_id, **overrides):
    values = {
        "inspection_id": inspection_id,
        "violation_type": ViolationType.MISSING_PERMIT,
        "rig_identifier": "KR-1042",
        "description": "No permit on board",
        "recorded_at": utcnow() - timedelta(hours=1),
    }
    values.update(overrides)
    return ViolationReportCreate(**values)


def make_other_officer():
    return SimpleNamespace(
        user_id=uuid.uuid4(),
        role=UserRole("patrol_officer"),
        is_active=True,
    )


@pytest.fixture
def officer(db_session, sample_inspection):
    return db_session.get(User, sample_inspection.officer_id)


class TestCreateReport:
    def test_officer_creates_report_for_own_inspection(
        self, db_session, officer, sample_inspection
    ):
        payload = make_payload(sample_inspection.inspection_id)

        report = violation_report_service.create_report(db_session, officer, payload)

        assert report.violation_id is not None
        assert report.inspection_id == sample_inspection.inspection_id
        assert report.violation_type == ViolationType.MISSING_PERMIT
        assert report.review_status == ReviewStatus.SUBMITTED

    def test_each_report_gets_its_own_server_generated_id(
        self, db_session, officer, sample_inspection
    ):
        payload = make_payload(sample_inspection.inspection_id)

        first = violation_report_service.create_report(db_session, officer, payload)
        second = violation_report_service.create_report(db_session, officer, payload)

        assert first.violation_id != second.violation_id

    def test_coordinator_cannot_create_report(
        self, db_session, sample_coordinator, sample_inspection
    ):
        payload = make_payload(sample_inspection.inspection_id)

        with pytest.raises(HTTPException) as error:
            violation_report_service.create_report(
                db_session, sample_coordinator, payload
            )

        assert error.value.status_code == 403

    def test_future_recorded_at_is_rejected(
        self, db_session, officer, sample_inspection
    ):
        payload = make_payload(
            sample_inspection.inspection_id,
            recorded_at=utcnow() + timedelta(hours=1),
        )

        with pytest.raises(HTTPException) as error:
            violation_report_service.create_report(db_session, officer, payload)

        assert error.value.status_code == 400

    def test_unknown_inspection_returns_404(self, db_session, officer):
        payload = make_payload(uuid.uuid4())

        with pytest.raises(HTTPException) as error:
            violation_report_service.create_report(db_session, officer, payload)

        assert error.value.status_code == 404

    def test_other_officers_inspection_returns_404(self, db_session, sample_inspection):
        payload = make_payload(sample_inspection.inspection_id)

        with pytest.raises(HTTPException) as error:
            violation_report_service.create_report(
                db_session, make_other_officer(), payload
            )

        assert error.value.status_code == 404


class TestGetReport:
    def test_owner_can_view_report(self, db_session, officer, sample_violation):
        report = violation_report_service.get_report(
            db_session, officer, sample_violation.violation_id
        )

        assert report.violation_id == sample_violation.violation_id

    def test_other_officer_cannot_view_report(self, db_session, sample_violation):
        with pytest.raises(HTTPException) as error:
            violation_report_service.get_report(
                db_session, make_other_officer(), sample_violation.violation_id
            )

        assert error.value.status_code == 404

    def test_coordinator_can_view_any_report(
        self, db_session, sample_coordinator, sample_violation
    ):
        report = violation_report_service.get_report(
            db_session, sample_coordinator, sample_violation.violation_id
        )

        assert report.violation_id == sample_violation.violation_id

    def test_unknown_report_returns_404(self, db_session, sample_coordinator):
        with pytest.raises(HTTPException) as error:
            violation_report_service.get_report(
                db_session, sample_coordinator, uuid.uuid4()
            )

        assert error.value.status_code == 404


class TestReviewReport:
    def test_coordinator_reviews_report(
        self, db_session, sample_coordinator, sample_violation
    ):
        report = violation_report_service.review_report(
            db_session, sample_coordinator, sample_violation.violation_id
        )

        assert report.review_status == ReviewStatus.REVIEWED
        assert report.reviewed_by == sample_coordinator.user_id
        assert report.reviewed_at is not None

    def test_report_cannot_be_reviewed_twice(
        self, db_session, sample_coordinator, sample_violation
    ):
        violation_report_service.review_report(
            db_session, sample_coordinator, sample_violation.violation_id
        )

        with pytest.raises(HTTPException) as error:
            violation_report_service.review_report(
                db_session, sample_coordinator, sample_violation.violation_id
            )

        assert error.value.status_code == 409

    def test_officer_cannot_review_report(self, db_session, officer, sample_violation):
        with pytest.raises(HTTPException) as error:
            violation_report_service.review_report(
                db_session, officer, sample_violation.violation_id
            )

        assert error.value.status_code == 403
