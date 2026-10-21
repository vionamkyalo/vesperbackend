import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from models.officer_location import OfficerLocation


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
