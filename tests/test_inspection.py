import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from models.inspection import Inspection, InspectionOutcome, InspectionType


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
