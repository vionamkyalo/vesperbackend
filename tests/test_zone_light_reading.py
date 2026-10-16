import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from models.zone_light_reading import IngestionStatus, ZoneLightReading


class TestZoneLightReading:
    def test_create_zone_light_reading_happy_path(self, db_session, sample_zone):
        reading = ZoneLightReading(
            zone_id=sample_zone.zone_id,
            observation_date=date(2026, 9, 1),
            ingestion_status=IngestionStatus.RECEIVED,
            light_index=Decimal("88.1234"),
            valid_pixel_count=300,
            hotspot_pixel_count=5,
            cluster_count=1,
        )
        db_session.add(reading)
        db_session.commit()
        db_session.refresh(reading)

        assert reading.reading_id is not None
        assert isinstance(reading.reading_id, uuid.UUID)
        assert reading.zone_id == sample_zone.zone_id
        assert reading.observation_date == date(2026, 9, 1)
        assert reading.ingestion_status == IngestionStatus.RECEIVED
        assert reading.light_index == Decimal("88.1234")
        assert reading.valid_pixel_count == 300
        assert reading.hotspot_pixel_count == 5
        assert reading.cluster_count == 1
        assert reading.created_at is not None

    def test_zone_light_reading_optional_fields(self, db_session, sample_zone):
        reading = ZoneLightReading(
            zone_id=sample_zone.zone_id,
            observation_date=date(2026, 9, 2),
        )
        db_session.add(reading)
        db_session.commit()
        db_session.refresh(reading)

        assert reading.light_index is None
        assert reading.valid_pixel_count is None
        assert reading.hotspot_pixel_count is None
        assert reading.cluster_count is None
        assert reading.ingestion_status == IngestionStatus.PENDING
        assert reading.created_at is not None

    @pytest.mark.parametrize(
        "status",
        [
            IngestionStatus.PENDING,
            IngestionStatus.RECEIVED,
            IngestionStatus.INGESTION_ERROR,
        ],
    )
    def test_zone_light_reading_ingestion_status_values(
        self, db_session, sample_zone, status
    ):
        reading = ZoneLightReading(
            zone_id=sample_zone.zone_id,
            observation_date=date(2026, 9, 3),
            ingestion_status=status,
        )
        db_session.add(reading)
        db_session.commit()
        db_session.refresh(reading)

        assert reading.ingestion_status == status

    def test_zone_light_reading_missing_required_fields(self, db_session):
        reading = ZoneLightReading()
        db_session.add(reading)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_light_reading_missing_zone_id(self, db_session):
        reading = ZoneLightReading(observation_date=date(2026, 9, 4))
        db_session.add(reading)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_light_reading_missing_observation_date(self, db_session, sample_zone):
        reading = ZoneLightReading(zone_id=sample_zone.zone_id)
        db_session.add(reading)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_light_reading_unique_zone_and_date(self, db_session, sample_zone):
        reading1 = ZoneLightReading(
            zone_id=sample_zone.zone_id,
            observation_date=date(2026, 9, 5),
        )
        db_session.add(reading1)
        db_session.commit()

        reading2 = ZoneLightReading(
            zone_id=sample_zone.zone_id,
            observation_date=date(2026, 9, 5),
        )
        db_session.add(reading2)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_light_reading_zone_relationship(
        self, db_session, sample_zone, sample_reading
    ):
        db_session.refresh(sample_zone)

        assert sample_reading.zone.zone_id == sample_zone.zone_id
        assert sample_reading in sample_zone.readings

    def test_zone_light_reading_alerts_relationship(
        self, db_session, sample_reading, sample_alert
    ):
        db_session.refresh(sample_reading)

        assert sample_alert.reading.reading_id == sample_reading.reading_id
        assert sample_alert in sample_reading.alerts
