import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from core.security import require_any_user, require_coordinator, require_officer
from database import get_db, utcnow
from main import app
from models.user import User, UserRole
from models.violation_report import ReviewStatus, ViolationType
from services.violation_report import violation_report_service


@pytest.fixture
def officer(db_session, sample_inspection):
    return db_session.get(User, sample_inspection.officer_id)


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def log_in_as(user):
    for dependency in (require_any_user, require_coordinator, require_officer):
        app.dependency_overrides[dependency] = lambda: user


class TestViolationReportRoutes:
    def test_officer_creates_report(self, client, officer, sample_inspection):
        log_in_as(officer)

        response = client.post(
            "/violation-reports",
            json={
                "inspection_id": str(sample_inspection.inspection_id),
                "violation_type": ViolationType.MISSING_PERMIT.value,
                "rig_identifier": "KR-1042",
                "description": "No permit on board",
                "recorded_at": (utcnow() - timedelta(hours=1)).isoformat(),
            },
        )

        assert response.status_code == 201
        # The server generates the id, so it must be a valid UUID.
        assert uuid.UUID(response.json()["violation_id"])

    def test_client_cannot_send_violation_id(self, client, officer, sample_inspection):
        log_in_as(officer)

        response = client.post(
            "/violation-reports",
            json={
                "violation_id": str(uuid.uuid4()),
                "inspection_id": str(sample_inspection.inspection_id),
                "violation_type": ViolationType.MISSING_PERMIT.value,
                "rig_identifier": "KR-1042",
                "description": "No permit on board",
                "recorded_at": (utcnow() - timedelta(hours=1)).isoformat(),
            },
        )

        assert response.status_code == 422

    def test_officer_lists_own_reports(self, client, officer, sample_violation):
        log_in_as(officer)

        response = client.get("/violation-reports")

        assert response.status_code == 200
        ids = [report["violation_id"] for report in response.json()]
        assert str(sample_violation.violation_id) in ids

    def test_officer_gets_own_report(self, client, officer, sample_violation):
        log_in_as(officer)

        response = client.get(f"/violation-reports/{sample_violation.violation_id}")

        assert response.status_code == 200
        assert response.json()["violation_id"] == str(sample_violation.violation_id)

    def test_coordinator_reviews_report(
        self, client, sample_coordinator, sample_violation
    ):
        log_in_as(sample_coordinator)

        response = client.post(
            f"/violation-reports/{sample_violation.violation_id}/review"
        )

        assert response.status_code == 200
        assert response.json()["review_status"] == ReviewStatus.REVIEWED.value

    def test_coordinator_deletes_report(
        self, client, sample_coordinator, sample_violation
    ):
        log_in_as(sample_coordinator)
        url = f"/violation-reports/{sample_violation.violation_id}"

        delete_response = client.delete(url)
        get_response = client.get(url)

        assert delete_response.status_code == 204
        assert get_response.status_code == 404

    def test_deleting_unknown_report_returns_404(self, client, sample_coordinator):
        log_in_as(sample_coordinator)

        response = client.delete(f"/violation-reports/{uuid.uuid4()}")

        assert response.status_code == 404


class TestViolationReportServiceExtras:
    def test_inactive_user_is_refused(self, db_session, sample_inspection):
        inactive_user = SimpleNamespace(
            user_id=uuid.uuid4(),
            role=UserRole("patrol_officer"),
            is_active=False,
        )

        with pytest.raises(HTTPException) as error:
            violation_report_service.list_reports(db_session, inactive_user)

        assert error.value.status_code == 403

    def test_coordinator_lists_all_reports(
        self, db_session, sample_coordinator, sample_violation
    ):
        reports = violation_report_service.list_reports(db_session, sample_coordinator)

        ids = [report.violation_id for report in reports]
        assert sample_violation.violation_id in ids
