import io
import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.user import User, UserRole
from models.zone import Zone, ZoneType
from models.zone_setting_history import ZoneSettingHistory
from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.datastructures import Headers
from core import security
from database import get_db
from repositories.zone import zone_repository
from schemas.zone import GeoJSONPolygon, ZoneRead, ZoneSettings, ZoneUpdate
from services import zone as zone_module
from services.zone import (
    MAX_ZONE_FILE_BYTES,
    load_basins,
    load_zones,
    zone_service,
)


API = "/vesper/zones"

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


def square(west, south, east, north):
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [west, south],
                [east, south],
                [east, north],
                [west, north],
                [west, south],
            ]
        ],
    }


SANYATI_POLYGON = square(28.79, -16.685, 28.85, -16.625)
SANYATI_OVERLAP_POLYGON = square(28.81, -16.665, 28.87, -16.605)
SANYATI_SECOND_POLYGON = square(28.70, -16.74, 28.74, -16.70)
MLIBIZI_POLYGON = square(27.12, -17.909, 27.144, -17.885)
BUMI_POLYGON = square(28.38, -16.73, 28.44, -16.67)
CROSSED_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [28.79, -16.685],
            [28.85, -16.625],
            [28.85, -16.685],
            [28.79, -16.625],
            [28.79, -16.685],
        ]
    ],
}


TEST_BASINS = {
    "basins": [
        {"name": "Mlibizi", "boundary": square(27.0, -18.0, 27.3, -17.8)},
        {"name": "Binga", "boundary": square(27.3, -17.8, 27.7, -17.4)},
        {"name": "Sengwa", "boundary": square(27.7, -17.4, 28.3, -16.8)},
        {"name": "Bumi", "boundary": square(28.3, -16.8, 28.6, -16.5)},
        {"name": "Sanyati", "boundary": square(28.6, -16.8, 29.2, -16.4)},
    ]
}

TEST_ZONES = {
    "source": "Test zones",
    "defaults": {
        "zone_type": "fishing_zone",
        "radiance_threshold": "10.0000",
        "cluster_radius_m": "1500.00",
        "min_cluster_points": 3,
        "confidence_threshold": "0.5000",
    },
    "zones": [
        {
            "name": "Zone 1",
            "basin": "Sanyati",
            "managed_by": "ZimParks",
            "boundary": SANYATI_POLYGON,
        },
        {
            "name": "Zone 2",
            "basin": "Bumi",
            "managed_by": "Nyaminyami RDC",
            "boundary": BUMI_POLYGON,
        },
        {
            "name": "Zone 3",
            "basin": "Mlibizi",
            "zone_type": "restricted_area",
            "boundary": MLIBIZI_POLYGON,
        },
    ],
}


def write_source(folder, name, data):
    path = folder / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


@pytest.fixture(autouse=True)
def zone_sources(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "BASINS_SOURCE", write_source(tmp_path, "basins.json", TEST_BASINS)
    )
    monkeypatch.setenv("ZONES_SOURCE", write_source(tmp_path, "zones.json", TEST_ZONES))
    return tmp_path


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


def settings_body(**changes):
    body = {
        "radiance_threshold": "20.0000",
        "cluster_radius_m": "800.00",
        "min_cluster_points": 4,
        "confidence_threshold": "0.6000",
    }
    body.update(changes)
    return body


def stand_in_role_check(*roles):
    def checker(
        x_test_user: str | None = Header(default=None), db: Session = Depends(get_db)
    ):
        if x_test_user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        user = db.get(User, uuid.UUID(x_test_user))
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        if user.role not in roles:
            raise HTTPException(
                status_code=403, detail="You do not have permission to do this."
            )
        return user

    return checker


REAL_SECURITY = hasattr(security, "create_access_token") and hasattr(
    security, "require_any_user"
)

if not REAL_SECURITY:
    security.require_coordinator = stand_in_role_check(UserRole.PATROL_COORDINATOR)
    security.require_officer = stand_in_role_check(UserRole.PATROL_OFFICER)
    security.require_any_user = stand_in_role_check(
        UserRole.PATROL_COORDINATOR, UserRole.PATROL_OFFICER
    )


def auth_headers(user):
    if REAL_SECURITY:
        token = security.create_access_token(user.user_id, user.role.value)
        return {"Authorization": f"Bearer {token}"}
    return {"X-Test-User": str(user.user_id)}


@pytest.fixture
def client(db_session):
    from routers import zone as zone_router

    app = FastAPI()
    if REAL_SECURITY:
        security.register_error_handlers(app)
    app.include_router(zone_router.router, prefix="/vesper")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    if not REAL_SECURITY:
        # main.py may have imported the router before this file patched
        # core.security, so swap the stand-ins in the same way dev_zone_server.py does.
        app.dependency_overrides[zone_router.require_coordinator] = (
            security.require_coordinator
        )
        app.dependency_overrides[zone_router.require_any_user] = (
            security.require_any_user
        )
    with TestClient(app) as test_client:
        yield test_client


class TestZoneRepository:
    def test_create_zone(self, db_session, sample_coordinator):
        zone = Zone(
            name="Repo Zone",
            basin="Sanyati",
            zone_type=ZoneType.RESTRICTED_AREA,
            boundary=ZONE_POLYGON,
            radiance_threshold=Decimal("10"),
            cluster_radius_m=Decimal("500"),
        )

        saved = zone_repository.create(db_session, zone)
        db_session.commit()

        assert saved.zone_id is not None
        assert zone_repository.get(db_session, saved.zone_id) is saved

    def test_get_zone_not_found(self, db_session):
        assert zone_repository.get(db_session, uuid.uuid4()) is None

    def test_get_zone_by_id(self, db_session, sample_zone):
        assert (
            zone_repository.get(db_session, sample_zone.zone_id).name
            == "Sanyati Basin East"
        )
        assert zone_repository.get(db_session, uuid.uuid4()) is None

    def test_get_all_includes_inactive_zones(
        self, db_session, sample_zone, sample_coordinator
    ):
        inactive = Zone(
            name="Closed Zone",
            basin="Sanyati",
            zone_type=ZoneType.FISHING_ZONE,
            boundary=ZONE_POLYGON,
            radiance_threshold=Decimal("10"),
            cluster_radius_m=Decimal("500"),
            is_active=False,
        )
        db_session.add(inactive)
        db_session.commit()

        assert len(zone_repository.get_all(db_session)) == 2
        active = zone_service.list_zones(
            db_session, sample_coordinator, active_only=True
        )
        assert [zone.zone_id for zone in active] == [sample_zone.zone_id]


class TestZoneSchema:
    @pytest.mark.parametrize(
        "boundary",
        [
            {"type": "Point", "coordinates": [[[28.0, -16.9]]]},
            {
                "type": "Polygon",
                "coordinates": [[[28.0, -16.9], [28.1, -16.9], [28.0, -16.9]]],
            },
            {
                "type": "Polygon",
                "coordinates": [
                    [[28.0, -16.9], [28.1, -16.9], [28.1, -16.8], [28.0, -16.8]]
                ],
            },
            {
                "type": "Polygon",
                "coordinates": [
                    [[200.0, -16.9], [28.1, -16.9], [28.1, -16.8], [200.0, -16.9]]
                ],
            },
        ],
    )
    def test_geojson_polygon_rejects_bad_boundary(self, boundary):
        with pytest.raises(ValidationError):
            GeoJSONPolygon(**boundary)

    def test_zone_settings_valid(self):
        data = ZoneSettings(**settings_body())

        assert data.min_cluster_points == 4
        assert data.confidence_threshold == Decimal("0.6000")

    def test_zone_update_all_optional(self):
        data = ZoneUpdate()

        assert data.model_dump(exclude_unset=True) == {}

    def test_zone_update_rejects_settings_fields(self):
        with pytest.raises(ValidationError):
            ZoneUpdate(radiance_threshold="5")

    def test_zone_read_json_uses_numbers(self, sample_zone):
        data = ZoneRead.model_validate(sample_zone).model_dump(mode="json")

        assert data["name"] == "Sanyati Basin East"
        assert data["radiance_threshold"] == 10.0
        assert data["confidence_threshold"] == 0.3
        assert data["boundary"] == ZONE_POLYGON


class TestZoneService:
    def test_get_zone(self, db_session, sample_officer, sample_zone):
        assert (
            zone_service.get_zone(
                db_session, sample_officer, sample_zone.zone_id
            ).zone_id
            == sample_zone.zone_id
        )

    def test_get_zone_not_found(self, db_session, sample_officer):
        with pytest.raises(HTTPException) as error:
            zone_service.get_zone(db_session, sample_officer, uuid.uuid4())

        assert error.value.status_code == 404

    def test_get_zone_inactive_user(self, db_session, sample_officer, sample_zone):
        sample_officer.is_active = False

        with pytest.raises(HTTPException) as error:
            zone_service.get_zone(db_session, sample_officer, sample_zone.zone_id)

        assert error.value.status_code == 403

    def test_list_zones(self, db_session, sample_officer, sample_zone):
        assert [
            zone.zone_id for zone in zone_service.list_zones(db_session, sample_officer)
        ] == [sample_zone.zone_id]

    def test_update_zone(self, db_session, sample_coordinator, sample_zone):
        body = ZoneUpdate(zone_type=ZoneType.RESTRICTED_AREA, boat_cap=15)

        zone = zone_service.update_zone(
            db_session, sample_coordinator, sample_zone.zone_id, body
        )

        assert zone.zone_type == ZoneType.RESTRICTED_AREA
        assert zone.boat_cap == 15
        assert zone.rules_confirmed_at is not None

    def test_update_zone_boundary_clears_confirmation(
        self, db_session, sample_coordinator, sample_zone
    ):
        body = ZoneUpdate(boundary=SANYATI_POLYGON)

        zone = zone_service.update_zone(
            db_session, sample_coordinator, sample_zone.zone_id, body
        )

        assert zone.rules_confirmed_at is None
        assert zone.rules_confirmed_by is None

    def test_update_zone_keep_own_name(
        self, db_session, sample_coordinator, sample_zone
    ):
        body = ZoneUpdate(name="Sanyati Basin East")

        zone = zone_service.update_zone(
            db_session, sample_coordinator, sample_zone.zone_id, body
        )

        assert zone.name == "Sanyati Basin East"

    def test_update_zone_rejects_empty_required_field(
        self, db_session, sample_coordinator, sample_zone
    ):
        with pytest.raises(HTTPException) as error:
            zone_service.update_zone(
                db_session,
                sample_coordinator,
                sample_zone.zone_id,
                ZoneUpdate(basin=None),
            )

        assert error.value.status_code == 400

    def test_update_zone_rejects_bad_closure(
        self, db_session, sample_coordinator, sample_zone
    ):
        body = ZoneUpdate(
            closure_start=date(2026, 11, 5), closure_end=date(2026, 11, 1)
        )

        with pytest.raises(HTTPException) as error:
            zone_service.update_zone(
                db_session, sample_coordinator, sample_zone.zone_id, body
            )

        assert error.value.status_code == 400

    def test_update_settings_records_history(
        self, db_session, sample_coordinator, sample_zone
    ):
        body = ZoneSettings(**settings_body())

        zone = zone_service.update_settings(
            db_session, sample_coordinator, sample_zone.zone_id, body
        )
        history = (
            db_session.query(ZoneSettingHistory)
            .filter(ZoneSettingHistory.zone_id == sample_zone.zone_id)
            .all()
        )
        assert zone.min_cluster_points == 4
        assert zone.confidence_threshold == Decimal("0.6000")
        assert zone.rules_confirmed_at is None
        assert len(history) == 1
        assert history[0].changed_by == sample_coordinator.user_id

    def test_confirm_rules(self, db_session, sample_coordinator, sample_zone):
        zone_service.update_settings(
            db_session,
            sample_coordinator,
            sample_zone.zone_id,
            ZoneSettings(**settings_body()),
        )

        zone = zone_service.confirm_rules(
            db_session, sample_coordinator, sample_zone.zone_id
        )

        assert zone.rules_confirmed_by == sample_coordinator.user_id
        assert zone.rules_confirmed_at is not None

    @pytest.mark.parametrize(
        "start, end, day, expected",
        [
            (date(2026, 11, 1), date(2026, 11, 5), date(2026, 11, 3), True),
            (date(2026, 11, 1), date(2026, 11, 5), date(2026, 11, 5), True),
            (date(2026, 11, 1), date(2026, 11, 5), date(2026, 11, 6), False),
            (date(2026, 11, 1), None, date(2026, 11, 1), True),
            (date(2026, 11, 1), None, date(2026, 11, 2), False),
            (None, None, date(2026, 11, 3), False),
        ],
    )
    def test_is_closed_on(self, start, end, day, expected):
        zone = Zone(closure_start=start, closure_end=end)

        assert zone_service.is_closed_on(zone, day) is expected


class TestZoneRouter:
    def test_list_zones(self, client, sample_officer, sample_zone):
        response = client.get(
            API, params={"active_only": True}, headers=auth_headers(sample_officer)
        )

        assert response.status_code == 200
        assert response.json()[0]["zone_id"] == str(sample_zone.zone_id)

    def test_get_zone(self, client, sample_officer, sample_zone):
        response = client.get(
            f"{API}/{sample_zone.zone_id}", headers=auth_headers(sample_officer)
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Sanyati Basin East"

    def test_get_zone_not_found(self, client, sample_officer):
        assert (
            client.get(
                f"{API}/{uuid.uuid4()}", headers=auth_headers(sample_officer)
            ).status_code
            == 404
        )

    def test_update_zone(self, client, sample_coordinator, sample_zone):
        response = client.patch(
            f"{API}/{sample_zone.zone_id}",
            json={"boat_cap": 12},
            headers=auth_headers(sample_coordinator),
        )

        assert response.status_code == 200
        assert response.json()["boat_cap"] == 12

    def test_update_zone_officer_forbidden(self, client, sample_officer, sample_zone):
        response = client.patch(
            f"{API}/{sample_zone.zone_id}",
            json={"boat_cap": 12},
            headers=auth_headers(sample_officer),
        )

        assert response.status_code == 403

    def test_update_settings_and_confirm(self, client, sample_coordinator, sample_zone):
        headers = auth_headers(sample_coordinator)

        settings = client.put(
            f"{API}/{sample_zone.zone_id}/settings",
            json=settings_body(),
            headers=headers,
        )
        confirmed = client.post(
            f"{API}/{sample_zone.zone_id}/confirm-rules", headers=headers
        )

        assert settings.status_code == 200
        assert settings.json()["rules_confirmed_at"] is None
        assert confirmed.status_code == 200
        assert confirmed.json()["rules_confirmed_by"] == str(sample_coordinator.user_id)

    def test_update_settings_bad_body(self, client, sample_coordinator, sample_zone):
        response = client.put(
            f"{API}/{sample_zone.zone_id}/settings",
            json=settings_body(min_cluster_points=0),
            headers=auth_headers(sample_coordinator),
        )

        assert response.status_code == 422


class TestZoneBoundary:
    def test_basins_file_has_five_basins(self):
        assert [basin["name"] for basin in load_basins()] == [
            "Mlibizi",
            "Binga",
            "Sengwa",
            "Bumi",
            "Sanyati",
        ]

    def test_list_basins(self, sample_officer):
        basins = zone_service.list_basins(sample_officer)

        assert len(basins) == 5
        assert all(basin["boundary"]["type"] == "Polygon" for basin in basins)

    def test_update_zone_move_to_another_basin(
        self, db_session, sample_coordinator, sample_zone
    ):
        body = ZoneUpdate(basin="Mlibizi", boundary=MLIBIZI_POLYGON)

        zone = zone_service.update_zone(
            db_session, sample_coordinator, sample_zone.zone_id, body
        )

        assert zone.basin == "Mlibizi"
        assert zone.rules_confirmed_at is None

    def test_update_zone_basin_without_matching_boundary(
        self, db_session, sample_coordinator, sample_zone
    ):
        with pytest.raises(HTTPException) as error:
            zone_service.update_zone(
                db_session,
                sample_coordinator,
                sample_zone.zone_id,
                ZoneUpdate(basin="Mlibizi"),
            )

        assert error.value.status_code == 400

    def test_router_list_basins(self, client, sample_officer):
        response = client.get(f"{API}/basins", headers=auth_headers(sample_officer))

        assert response.status_code == 200
        assert response.json()[0]["name"] == "Mlibizi"
        assert response.json()[0]["boundary"]["type"] == "Polygon"

    def test_router_list_basins_requires_login(self, client):
        assert client.get(f"{API}/basins").status_code == 401

    def test_basins_match_zone_source(self):
        basins = {basin["name"] for basin in load_basins()}

        assert {zone.basin for zone in load_zones().zones} <= basins


class TestZoneSource:
    def test_load_basins_from_file(self):
        assert len(load_basins()) == 5

    def test_load_zones_from_file(self):
        data = load_zones()

        assert [zone.name for zone in data.zones] == ["Zone 1", "Zone 2", "Zone 3"]
        assert data.defaults.min_cluster_points == 3

    def test_load_basins_from_url(self, monkeypatch):
        opened = []

        def fake_urlopen(url, timeout):
            opened.append(url)
            return io.BytesIO(json.dumps(TEST_BASINS).encode("utf-8"))

        monkeypatch.setattr(zone_module, "urlopen", fake_urlopen)
        monkeypatch.setenv("BASINS_SOURCE", "https://example.org/kariba_basins.json")

        assert len(load_basins()) == 5
        assert opened == ["https://example.org/kariba_basins.json"]

    def test_missing_source_setting(self, monkeypatch):
        monkeypatch.delenv("BASINS_SOURCE")

        with pytest.raises(HTTPException) as error:
            load_basins()

        assert error.value.status_code == 503
        assert "BASINS_SOURCE" in error.value.detail

    def test_source_file_not_found(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZONES_SOURCE", str(tmp_path / "missing.json"))

        with pytest.raises(HTTPException) as error:
            load_zones()

        assert error.value.status_code == 503

    def test_source_is_not_json(self, monkeypatch, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("not json", encoding="utf-8")
        monkeypatch.setenv("ZONES_SOURCE", str(path))

        with pytest.raises(HTTPException) as error:
            load_zones()

        assert error.value.status_code == 503

    def test_source_in_wrong_format(self, monkeypatch, tmp_path):
        monkeypatch.setenv(
            "BASINS_SOURCE", write_source(tmp_path, "bad.json", {"zones": []})
        )

        with pytest.raises(HTTPException) as error:
            load_basins()

        assert error.value.status_code == 503
        assert "expected format" in error.value.detail


class TestZoneImport:
    def test_import_zones(self, db_session, sample_coordinator):
        created = zone_service.import_zones(db_session, sample_coordinator)

        assert [zone.name for zone in created] == ["Zone 1", "Zone 2", "Zone 3"]
        assert all(zone.is_active is False for zone in created)
        assert all(zone.rules_confirmed_at is None for zone in created)
        assert created[0].radiance_threshold == Decimal("10.0000")
        assert created[0].zone_type == ZoneType.FISHING_ZONE
        assert created[2].zone_type == ZoneType.RESTRICTED_AREA

    def test_import_zones_twice(self, db_session, sample_coordinator):
        zone_service.import_zones(db_session, sample_coordinator)

        assert zone_service.import_zones(db_session, sample_coordinator) == []
        assert db_session.query(Zone).count() == 3

    def test_import_zones_officer_forbidden(self, db_session, sample_officer):
        with pytest.raises(HTTPException) as error:
            zone_service.import_zones(db_session, sample_officer)

        assert error.value.status_code == 403

    def test_import_zones_outside_basin(
        self, db_session, sample_coordinator, monkeypatch, tmp_path
    ):
        data = json.loads(json.dumps(TEST_ZONES))
        data["zones"][0]["basin"] = "Binga"
        monkeypatch.setenv("ZONES_SOURCE", write_source(tmp_path, "z.json", data))

        with pytest.raises(HTTPException) as error:
            zone_service.import_zones(db_session, sample_coordinator)

        assert error.value.status_code == 400
        assert db_session.query(Zone).count() == 0

    def test_import_zones_overlapping_each_other(
        self, db_session, sample_coordinator, monkeypatch, tmp_path
    ):
        data = json.loads(json.dumps(TEST_ZONES))
        data["zones"][1] = {
            "name": "Zone 2",
            "basin": "Sanyati",
            "boundary": SANYATI_OVERLAP_POLYGON,
        }
        monkeypatch.setenv("ZONES_SOURCE", write_source(tmp_path, "z.json", data))

        with pytest.raises(HTTPException) as error:
            zone_service.import_zones(db_session, sample_coordinator)

        assert error.value.status_code == 409
        assert db_session.query(Zone).count() == 0

    def test_import_zones_missing_source(
        self, db_session, sample_coordinator, monkeypatch
    ):
        monkeypatch.delenv("ZONES_SOURCE")

        with pytest.raises(HTTPException) as error:
            zone_service.import_zones(db_session, sample_coordinator)

        assert error.value.status_code == 503

    def test_router_import_zones(self, client, sample_coordinator):
        headers = auth_headers(sample_coordinator)

        first = client.post(f"{API}/import", headers=headers)
        second = client.post(f"{API}/import", headers=headers)

        assert first.status_code == 200
        assert [zone["name"] for zone in first.json()] == ["Zone 1", "Zone 2", "Zone 3"]
        assert second.status_code == 200
        assert second.json() == []

    def test_router_import_zones_officer_forbidden(self, client, sample_officer):
        response = client.post(f"{API}/import", headers=auth_headers(sample_officer))

        assert response.status_code == 403

    def test_router_import_zones_requires_login(self, client):
        assert client.post(f"{API}/import").status_code == 401


def zones_upload(data, name="zones.json", content_type="application/json"):
    body = data if isinstance(data, (bytes, str)) else json.dumps(data)
    return {"file": (name, body, content_type)}


def upload(db, user, content, name="zones.json", content_type="application/json"):
    headers = Headers({"content-type": content_type} if content_type else {})
    file = UploadFile(file=io.BytesIO(content), filename=name, headers=headers)
    return zone_service.import_zones(db, user, file)


class TestZoneUpload:
    def test_import_uploaded_file(self, db_session, sample_coordinator, monkeypatch):
        monkeypatch.delenv("ZONES_SOURCE")
        content = json.dumps(TEST_ZONES).encode("utf-8")

        created = upload(db_session, sample_coordinator, content)

        assert [zone.name for zone in created] == ["Zone 1", "Zone 2", "Zone 3"]

    def test_uploaded_file_not_json(self, db_session, sample_coordinator):
        with pytest.raises(HTTPException) as error:
            upload(db_session, sample_coordinator, b"not json")

        assert error.value.status_code == 400
        assert "valid JSON" in error.value.detail

    def test_uploaded_file_wrong_format(self, db_session, sample_coordinator):
        with pytest.raises(HTTPException) as error:
            upload(db_session, sample_coordinator, json.dumps({"zones": []}).encode())

        assert error.value.status_code == 400
        assert "expected zones format" in error.value.detail

    def test_uploaded_file_too_large(self, db_session, sample_coordinator):
        with pytest.raises(HTTPException) as error:
            upload(db_session, sample_coordinator, b" " * (MAX_ZONE_FILE_BYTES + 1))

        assert error.value.status_code == 413

    def test_uploaded_zone_outside_basin(self, db_session, sample_coordinator):
        data = json.loads(json.dumps(TEST_ZONES))
        data["zones"][0]["basin"] = "Binga"

        with pytest.raises(HTTPException) as error:
            upload(db_session, sample_coordinator, json.dumps(data).encode())

        assert error.value.status_code == 400
        assert error.value.detail.startswith("Zone 1:")
        assert db_session.query(Zone).count() == 0

    def test_router_upload(self, client, sample_coordinator):
        headers = auth_headers(sample_coordinator)

        first = client.post(
            f"{API}/import", files=zones_upload(TEST_ZONES), headers=headers
        )
        second = client.post(
            f"{API}/import", files=zones_upload(TEST_ZONES), headers=headers
        )

        assert first.status_code == 200
        assert len(first.json()) == 3
        assert second.json() == []

    def test_router_upload_not_json(self, client, sample_coordinator):
        response = client.post(
            f"{API}/import",
            files=zones_upload("not json"),
            headers=auth_headers(sample_coordinator),
        )

        assert response.status_code == 400

    def test_router_upload_officer_forbidden(self, client, sample_officer):
        response = client.post(
            f"{API}/import",
            files=zones_upload(TEST_ZONES),
            headers=auth_headers(sample_officer),
        )

        assert response.status_code == 403

    def test_router_without_file_uses_source(self, client, sample_coordinator):
        response = client.post(
            f"{API}/import", headers=auth_headers(sample_coordinator)
        )

        assert response.status_code == 200
        assert len(response.json()) == 3

    @pytest.mark.parametrize(
        "name, content_type",
        [
            ("zones.txt", "application/json"),
            ("zones.csv", "text/csv"),
            ("zones.json", "text/plain"),
            ("zones.json", "application/octet-stream"),
            ("zones", None),
        ],
    )
    def test_upload_must_be_json(
        self, db_session, sample_coordinator, name, content_type
    ):
        content = json.dumps(TEST_ZONES).encode("utf-8")

        with pytest.raises(HTTPException) as error:
            upload(db_session, sample_coordinator, content, name, content_type)

        assert error.value.status_code == 415
        assert db_session.query(Zone).count() == 0

    def test_upload_json_with_charset(self, db_session, sample_coordinator):
        content = json.dumps(TEST_ZONES).encode("utf-8")

        created = upload(
            db_session,
            sample_coordinator,
            content,
            "ZONES.JSON",
            "application/json; charset=utf-8",
        )

        assert len(created) == 3

    def test_router_upload_text_file(self, client, sample_coordinator):
        response = client.post(
            f"{API}/import",
            files=zones_upload(TEST_ZONES, "zones.txt", "text/plain"),
            headers=auth_headers(sample_coordinator),
        )

        assert response.status_code == 415
        assert response.json()["detail"] == "Upload the zones as a .json file."
