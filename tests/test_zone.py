import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from models.zone import Zone, ZoneType
from models.zone_setting_history import ZoneSettingHistory

ZONE_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [28.00, -16.90],
            [28.10, -16.90],
            [28.10, -16.80],
            [28.00, -16.80],
            [28.00, -16.90],
        ]
    ],
}


class TestZone:
    def test_create_zone_happy_path(self, db_session, sample_coordinator):
        confirmed_at = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
        zone = Zone(
            name="Bumi Hills",
            basin="Bumi",
            zone_type=ZoneType.FISHING_ZONE,
            boundary=ZONE_POLYGON,
            boat_cap=40,
            closure_start=date(2026, 11, 1),
            closure_end=date(2026, 11, 5),
            radiance_threshold=Decimal("12.5000"),
            cluster_radius_m=Decimal("1000.00"),
            min_cluster_points=3,
            confidence_threshold=Decimal("0.5000"),
            is_active=True,
            updated_by=sample_coordinator.user_id,
            rules_confirmed_by=sample_coordinator.user_id,
            rules_confirmed_at=confirmed_at,
        )
        db_session.add(zone)
        db_session.commit()
        db_session.refresh(zone)

        assert zone.zone_id is not None
        assert isinstance(zone.zone_id, uuid.UUID)
        assert zone.name == "Bumi Hills"
        assert zone.basin == "Bumi"
        assert zone.zone_type == ZoneType.FISHING_ZONE
        assert zone.boundary == ZONE_POLYGON
        assert zone.boat_cap == 40
        assert zone.closure_start == date(2026, 11, 1)
        assert zone.closure_end == date(2026, 11, 5)
        assert zone.radiance_threshold == Decimal("12.5000")
        assert zone.cluster_radius_m == Decimal("1000.00")
        assert zone.min_cluster_points == 3
        assert zone.confidence_threshold == Decimal("0.5000")
        assert zone.is_active is True
        assert zone.updated_by == sample_coordinator.user_id
        assert zone.rules_confirmed_by == sample_coordinator.user_id
        assert zone.rules_confirmed_at == confirmed_at
        assert zone.created_at is not None
        assert zone.updated_at is not None

    def test_zone_optional_fields(self, db_session):
        zone = Zone(
            name="Sengwa",
            basin="Sengwa",
            zone_type=ZoneType.FISHING_ZONE,
            boundary=ZONE_POLYGON,
            radiance_threshold=Decimal("10"),
            cluster_radius_m=Decimal("500"),
        )
        db_session.add(zone)
        db_session.commit()
        db_session.refresh(zone)

        assert zone.boat_cap is None
        assert zone.closure_start is None
        assert zone.closure_end is None
        assert zone.updated_by is None
        assert zone.rules_confirmed_by is None
        assert zone.rules_confirmed_at is None
        assert zone.min_cluster_points == 3
        assert zone.confidence_threshold == Decimal("0.5000")
        assert zone.is_active is True
        assert zone.created_at is not None

    @pytest.mark.parametrize(
        "zone_type",
        [
            ZoneType.FISHING_ZONE,
            ZoneType.RESTRICTED_AREA,
        ],
    )
    def test_zone_type_values(self, db_session, zone_type):
        zone = Zone(
            name="Type Test",
            basin="Sanyati",
            zone_type=zone_type,
            boundary=ZONE_POLYGON,
            radiance_threshold=Decimal("10"),
            cluster_radius_m=Decimal("500"),
        )
        db_session.add(zone)
        db_session.commit()
        db_session.refresh(zone)

        assert zone.zone_type == zone_type

    def test_zone_missing_required_fields(self, db_session):
        zone = Zone()
        db_session.add(zone)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_missing_name(self, db_session):
        zone = Zone(
            basin="Sanyati",
            zone_type=ZoneType.FISHING_ZONE,
            boundary=ZONE_POLYGON,
            radiance_threshold=Decimal("10"),
            cluster_radius_m=Decimal("500"),
        )
        db_session.add(zone)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_missing_boundary(self, db_session):
        zone = Zone(
            name="No Boundary",
            basin="Sanyati",
            zone_type=ZoneType.FISHING_ZONE,
            radiance_threshold=Decimal("10"),
            cluster_radius_m=Decimal("500"),
        )
        db_session.add(zone)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_missing_radiance_threshold(self, db_session):
        zone = Zone(
            name="No Threshold",
            basin="Sanyati",
            zone_type=ZoneType.FISHING_ZONE,
            boundary=ZONE_POLYGON,
            cluster_radius_m=Decimal("500"),
        )
        db_session.add(zone)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_missing_cluster_radius(self, db_session):
        zone = Zone(
            name="No Radius",
            basin="Sanyati",
            zone_type=ZoneType.FISHING_ZONE,
            boundary=ZONE_POLYGON,
            radiance_threshold=Decimal("10"),
        )
        db_session.add(zone)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_unique_name(self, db_session, sample_zone):
        zone = Zone(
            name=sample_zone.name,
            basin="Sanyati",
            zone_type=ZoneType.FISHING_ZONE,
            boundary=ZONE_POLYGON,
            radiance_threshold=Decimal("10"),
            cluster_radius_m=Decimal("500"),
        )
        db_session.add(zone)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_readings_relationship(self, db_session, sample_zone, sample_reading):
        db_session.refresh(sample_zone)

        assert sample_reading.zone.zone_id == sample_zone.zone_id
        assert sample_reading in sample_zone.readings

    def test_zone_baselines_relationship(
        self, db_session, sample_zone, sample_baseline
    ):
        db_session.refresh(sample_zone)

        assert sample_baseline.zone.zone_id == sample_zone.zone_id
        assert sample_baseline in sample_zone.baselines

    def test_zone_alerts_relationship(self, db_session, sample_zone, sample_alert):
        db_session.refresh(sample_zone)

        assert sample_alert.zone.zone_id == sample_zone.zone_id
        assert sample_alert in sample_zone.alerts

    def test_zone_inspections_relationship(
        self, db_session, sample_zone, landing_inspection
    ):
        db_session.refresh(sample_zone)

        assert landing_inspection.zone.zone_id == sample_zone.zone_id
        assert landing_inspection in sample_zone.inspections

    def test_zone_setting_history_relationship(
        self, db_session, sample_zone, sample_coordinator
    ):
        history = ZoneSettingHistory(
            zone_id=sample_zone.zone_id,
            radiance_threshold=Decimal("10"),
            cluster_radius_m=Decimal("1500"),
            min_cluster_points=3,
            confidence_threshold=Decimal("0.3"),
            changed_by=sample_coordinator.user_id,
        )
        db_session.add(history)
        db_session.commit()
        db_session.refresh(sample_zone)

        assert history.zone.zone_id == sample_zone.zone_id
        assert history in sample_zone.setting_history
