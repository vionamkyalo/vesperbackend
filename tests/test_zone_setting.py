import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from models.zone_setting_history import ZoneSettingHistory


class TestZoneSettingHistory:
    def test_create_zone_setting_history_happy_path(
        self, db_session, sample_zone, sample_coordinator
    ):
        history = ZoneSettingHistory(
            zone_id=sample_zone.zone_id,
            radiance_threshold=Decimal("15.0000"),
            cluster_radius_m=Decimal("800.00"),
            min_cluster_points=4,
            confidence_threshold=Decimal("0.6000"),
            changed_by=sample_coordinator.user_id,
        )
        db_session.add(history)
        db_session.commit()
        db_session.refresh(history)

        assert history.history_id is not None
        assert isinstance(history.history_id, uuid.UUID)
        assert history.zone_id == sample_zone.zone_id
        assert history.radiance_threshold == Decimal("15.0000")
        assert history.cluster_radius_m == Decimal("800.00")
        assert history.min_cluster_points == 4
        assert history.confidence_threshold == Decimal("0.6000")
        assert history.changed_by == sample_coordinator.user_id
        assert history.changed_at is not None

    def test_zone_setting_history_missing_required_fields(self, db_session):
        history = ZoneSettingHistory()
        db_session.add(history)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_setting_history_missing_zone_id(self, db_session, sample_coordinator):
        history = ZoneSettingHistory(
            radiance_threshold=Decimal("15"),
            cluster_radius_m=Decimal("800"),
            min_cluster_points=4,
            confidence_threshold=Decimal("0.6"),
            changed_by=sample_coordinator.user_id,
        )
        db_session.add(history)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_setting_history_missing_changed_by(self, db_session, sample_zone):
        history = ZoneSettingHistory(
            zone_id=sample_zone.zone_id,
            radiance_threshold=Decimal("15"),
            cluster_radius_m=Decimal("800"),
            min_cluster_points=4,
            confidence_threshold=Decimal("0.6"),
        )
        db_session.add(history)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_setting_history_missing_confidence_threshold(
        self, db_session, sample_zone, sample_coordinator
    ):
        history = ZoneSettingHistory(
            zone_id=sample_zone.zone_id,
            radiance_threshold=Decimal("15"),
            cluster_radius_m=Decimal("800"),
            min_cluster_points=4,
            changed_by=sample_coordinator.user_id,
        )
        db_session.add(history)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_setting_history_zone_relationship(
        self, db_session, sample_zone, sample_coordinator
    ):
        history = ZoneSettingHistory(
            zone_id=sample_zone.zone_id,
            radiance_threshold=Decimal("15"),
            cluster_radius_m=Decimal("800"),
            min_cluster_points=4,
            confidence_threshold=Decimal("0.6"),
            changed_by=sample_coordinator.user_id,
        )
        db_session.add(history)
        db_session.commit()
        db_session.refresh(sample_zone)

        assert history.zone.zone_id == sample_zone.zone_id
        assert history in sample_zone.setting_history

    def test_zone_setting_history_changer_relationship(
        self, db_session, sample_zone, sample_coordinator
    ):
        history = ZoneSettingHistory(
            zone_id=sample_zone.zone_id,
            radiance_threshold=Decimal("15"),
            cluster_radius_m=Decimal("800"),
            min_cluster_points=4,
            confidence_threshold=Decimal("0.6"),
            changed_by=sample_coordinator.user_id,
        )
        db_session.add(history)
        db_session.commit()
        db_session.refresh(history)

        assert history.changer.user_id == sample_coordinator.user_id
