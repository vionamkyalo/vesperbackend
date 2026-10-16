import os

os.environ.setdefault("DATABASE_URL", "sqlite://")

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models.alert import Alert, AlertStatus
from models.alert_assignment import AlertAssignment, AssignmentStatus
from models.catch_check import CatchCheck
from models.inspection import Inspection, InspectionOutcome, InspectionType
from models.officer_location import OfficerLocation
from models.user import User, UserRole
from models.violation_report import ViolationReport, ViolationType
from models.zone import Zone, ZoneType
from models.zone_baseline import MoonBand, ZoneBaseline
from models.zone_light_reading import IngestionStatus, ZoneLightReading

PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$dGVzdHNhbHQ$dGVzdGhhc2g"
OBSERVATION_DATE = date(2026, 10, 10)
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


@pytest.fixture
def engine():
    test_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(test_engine, "connect")
    def enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(test_engine)
    yield test_engine
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture
def db_session(engine):
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.rollback()
    session.close()


def make_user(db_session, role, email, phone, first_name, last_name):
    user = User(
        first_name=first_name,
        last_name=last_name,
        phone_number=phone,
        email=email,
        password_hash=PASSWORD_HASH,
        role=role,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def sample_coordinator(db_session):
    return make_user(
        db_session,
        UserRole.PATROL_COORDINATOR,
        "rudo@example.org",
        "+263771000001",
        "Rudo",
        "Chikwanha",
    )


@pytest.fixture
def sample_officer(db_session):
    return make_user(
        db_session,
        UserRole.PATROL_OFFICER,
        "tendai@example.org",
        "+263771000002",
        "Tendai",
        "Moyo",
    )


@pytest.fixture
def second_officer(db_session):
    return make_user(
        db_session,
        UserRole.PATROL_OFFICER,
        "farai@example.org",
        "+263771000003",
        "Farai",
        "Ncube",
    )


@pytest.fixture
def sample_zone(db_session, sample_coordinator):
    zone = Zone(
        name="Sanyati Basin East",
        basin="Sanyati",
        zone_type=ZoneType.FISHING_ZONE,
        boundary=ZONE_POLYGON,
        radiance_threshold=Decimal("10.0000"),
        cluster_radius_m=Decimal("1500.00"),
        min_cluster_points=3,
        confidence_threshold=Decimal("0.3000"),
        updated_by=sample_coordinator.user_id,
        rules_confirmed_by=sample_coordinator.user_id,
        rules_confirmed_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    db_session.add(zone)
    db_session.commit()
    db_session.refresh(zone)
    return zone


@pytest.fixture
def sample_reading(db_session, sample_zone):
    reading = ZoneLightReading(
        zone_id=sample_zone.zone_id,
        observation_date=OBSERVATION_DATE,
        ingestion_status=IngestionStatus.RECEIVED,
        light_index=Decimal("500.0000"),
        valid_pixel_count=400,
        hotspot_pixel_count=12,
        cluster_count=2,
    )
    db_session.add(reading)
    db_session.commit()
    db_session.refresh(reading)
    return reading


@pytest.fixture
def sample_baseline(db_session, sample_zone):
    baseline = ZoneBaseline(
        zone_id=sample_zone.zone_id,
        moon_band=MoonBand.DARK,
        expected_light_index=Decimal("100.0000"),
        nights_used=10,
    )
    db_session.add(baseline)
    db_session.commit()
    db_session.refresh(baseline)
    return baseline


@pytest.fixture
def sample_alert(db_session, sample_zone, sample_reading):
    alert = Alert(
        zone_id=sample_zone.zone_id,
        reading_id=sample_reading.reading_id,
        cluster_label=0,
        point_count=6,
        confidence=Decimal("0.7500"),
        centroid_latitude=Decimal("-16.850000"),
        centroid_longitude=Decimal("28.050000"),
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)
    return alert


@pytest.fixture
def sample_assignment(db_session, sample_alert, sample_officer, sample_coordinator):
    now = datetime.now(timezone.utc)
    assignment = AlertAssignment(
        alert_id=sample_alert.alert_id,
        officer_id=sample_officer.user_id,
        assigned_by=sample_coordinator.user_id,
        assigned_at=now,
    )
    sample_alert.officer_id = sample_officer.user_id
    sample_alert.assigned_by = sample_coordinator.user_id
    sample_alert.assignment_status = AssignmentStatus.ASSIGNED
    sample_alert.assigned_at = now
    sample_alert.status = AlertStatus.IN_PROGRESS
    db_session.add(assignment)
    db_session.commit()
    db_session.refresh(assignment)
    return assignment


def make_inspection(
    db_session, officer, zone, alert=None, inspection_type=InspectionType.SITE
):
    inspection = Inspection(
        inspection_id=uuid.uuid4(),
        alert_id=alert.alert_id if alert else None,
        officer_id=officer.user_id,
        zone_id=zone.zone_id,
        inspection_type=inspection_type,
        outcome=InspectionOutcome.ACTIVITY_CONSISTENT,
        rigs_observed=4,
        latitude=Decimal("-16.850100"),
        longitude=Decimal("28.050200"),
        notes="Four rigs with lights on",
        inspected_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(inspection)
    db_session.commit()
    db_session.refresh(inspection)
    return inspection


@pytest.fixture
def sample_inspection(
    db_session, sample_officer, sample_zone, sample_alert, sample_assignment
):
    return make_inspection(db_session, sample_officer, sample_zone, sample_alert)


@pytest.fixture
def landing_inspection(db_session, sample_officer, sample_zone):
    return make_inspection(
        db_session, sample_officer, sample_zone, None, InspectionType.LANDING_SITE
    )


@pytest.fixture
def sample_violation(db_session, sample_inspection):
    report = ViolationReport(
        violation_id=uuid.uuid4(),
        inspection_id=sample_inspection.inspection_id,
        violation_type=ViolationType.MISSING_PERMIT,
        rig_identifier="KR-1042",
        description="No permit on board",
        recorded_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    db_session.add(report)
    db_session.commit()
    db_session.refresh(report)
    return report


@pytest.fixture
def sample_catch_check(db_session, landing_inspection):
    check = CatchCheck(
        catch_id=uuid.uuid4(),
        inspection_id=landing_inspection.inspection_id,
        rig_identifier="KR-2001",
        rig_nights=3,
        catch_weight_kg=Decimal("450.00"),
        checked_at=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    db_session.add(check)
    db_session.commit()
    db_session.refresh(check)
    return check


@pytest.fixture
def sample_location(db_session, sample_officer, sample_alert):
    location = OfficerLocation(
        location_id=uuid.uuid4(),
        officer_id=sample_officer.user_id,
        alert_id=sample_alert.alert_id,
        latitude=Decimal("-16.851000"),
        longitude=Decimal("28.049000"),
        accuracy_m=Decimal("12.50"),
        recorded_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db_session.add(location)
    db_session.commit()
    db_session.refresh(location)
    return location
