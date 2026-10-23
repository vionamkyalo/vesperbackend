import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from core import security
from database import get_db, utcnow
from models.zone import Zone, ZoneType
from models.zone_baseline import MoonBand, ZoneBaseline
from models.zone_light_reading import IngestionStatus, ZoneLightReading
from repositories.zone_baseline import zone_baseline_repository
from schemas.zone_baseline import (
    ZoneBaselineFilter,
    ZoneBaselineRead,
    ZoneBaselineRecalculate,
)
from services.zone_baseline import (
    moon_band_for,
    moon_illumination,
    zone_baseline_service,
)

BASELINE_API = "/vesper/zone-baselines"

SECOND_ZONE_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [28.30, -16.70],
            [28.40, -16.70],
            [28.40, -16.60],
            [28.30, -16.60],
            [28.30, -16.70],
        ]
    ],
}


def recent_nights(band, count, days_back=90):
    today = utcnow().date()
    nights = []
    for offset in range(1, days_back):
        day = today - timedelta(days=offset)
        if moon_band_for(day) == band:
            nights.append(day)
        if len(nights) == count:
            return nights
    raise AssertionError(f"Not enough {band.value} nights in {days_back} days")


def add_reading(db, zone, day, light_index, ingestion_status=IngestionStatus.RECEIVED):
    reading = ZoneLightReading(
        zone_id=zone.zone_id,
        observation_date=day,
        ingestion_status=ingestion_status,
        light_index=None if light_index is None else Decimal(light_index),
    )
    db.add(reading)
    db.commit()
    return reading


def add_band_readings(db, zone, band, values):
    for day, value in zip(recent_nights(band, len(values)), values):
        add_reading(db, zone, day, value)


def baseline_headers(user):
    token = security.create_access_token(user.user_id, user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def baseline_client(db_session):
    from routers import zone_baseline as baseline_router

    app = FastAPI()
    security.register_error_handlers(app)
    app.include_router(baseline_router.router, prefix="/vesper")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def second_zone(db_session):
    zone = Zone(
        name="Bumi North",
        basin="Bumi",
        zone_type=ZoneType.FISHING_ZONE,
        boundary=SECOND_ZONE_POLYGON,
        radiance_threshold=Decimal("10.0000"),
        cluster_radius_m=Decimal("1500.00"),
    )
    db_session.add(zone)
    db_session.commit()
    db_session.refresh(zone)
    return zone


class TestMoonBand:
    @pytest.mark.parametrize(
        "day, band",
        [
            (date(2024, 4, 8), MoonBand.DARK),
            (date(2024, 4, 15), MoonBand.PARTIAL),
            (date(2024, 4, 23), MoonBand.BRIGHT),
            (date(2026, 10, 10), MoonBand.DARK),
            (date(2026, 10, 18), MoonBand.PARTIAL),
            (date(2026, 10, 26), MoonBand.BRIGHT),
        ],
    )
    def test_known_moon_phases(self, day, band):
        assert moon_band_for(day) == band

    def test_illumination_is_a_fraction(self):
        for offset in range(60):
            value = moon_illumination(date(2026, 1, 1) + timedelta(days=offset))
            assert 0 <= value <= 1


class TestZoneBaselineRepository:
    def test_create_and_get(self, db_session, sample_zone):
        baseline = zone_baseline_repository.create(
            db_session,
            ZoneBaseline(
                zone_id=sample_zone.zone_id,
                moon_band=MoonBand.BRIGHT,
                expected_light_index=Decimal("80.0000"),
                nights_used=6,
            ),
        )

        assert (
            zone_baseline_repository.get(db_session, baseline.baseline_id) is baseline
        )
        assert zone_baseline_repository.get(db_session, uuid.uuid4()) is None

    def test_get_by_zone_band(self, db_session, sample_baseline):
        found = zone_baseline_repository.get_by_zone_band(
            db_session, sample_baseline.zone_id, MoonBand.DARK
        )
        missing = zone_baseline_repository.get_by_zone_band(
            db_session, sample_baseline.zone_id, MoonBand.BRIGHT
        )

        assert found.baseline_id == sample_baseline.baseline_id
        assert missing is None

    def test_list_filters(self, db_session, sample_baseline, second_zone):
        db_session.add(
            ZoneBaseline(
                zone_id=second_zone.zone_id,
                moon_band=MoonBand.PARTIAL,
                expected_light_index=Decimal("50.0000"),
                nights_used=5,
            )
        )
        db_session.commit()

        assert len(zone_baseline_repository.list_baselines(db_session)) == 2
        assert [
            item.zone_id
            for item in zone_baseline_repository.list_baselines(
                db_session, zone_id=second_zone.zone_id
            )
        ] == [second_zone.zone_id]
        assert [
            item.moon_band
            for item in zone_baseline_repository.list_baselines(
                db_session, moon_band=MoonBand.DARK
            )
        ] == [MoonBand.DARK]
        assert len(zone_baseline_repository.list_baselines(db_session, limit=1)) == 1
        assert len(zone_baseline_repository.list_baselines(db_session, offset=2)) == 0

    def test_received_readings_only(self, db_session, sample_zone):
        today = utcnow().date()
        add_reading(db_session, sample_zone, today - timedelta(days=1), "10")
        add_reading(
            db_session,
            sample_zone,
            today - timedelta(days=2),
            "20",
            IngestionStatus.PENDING,
        )
        add_reading(
            db_session,
            sample_zone,
            today - timedelta(days=3),
            "30",
            IngestionStatus.INGESTION_ERROR,
        )
        add_reading(db_session, sample_zone, today - timedelta(days=4), None)
        add_reading(db_session, sample_zone, today - timedelta(days=200), "40")

        readings = zone_baseline_repository.list_received_readings(
            db_session, sample_zone.zone_id, today - timedelta(days=90), today
        )

        assert [reading.light_index for reading in readings] == [Decimal("10")]


class TestZoneBaselineSchema:
    def test_read_json_uses_numbers(self, sample_baseline):
        data = ZoneBaselineRead.model_validate(sample_baseline).model_dump(mode="json")

        assert data["expected_light_index"] == 100.0
        assert data["moon_band"] == "dark"
        assert data["nights_used"] == 10

    def test_recalculate_defaults(self):
        data = ZoneBaselineRecalculate()

        assert data.zone_id is None
        assert data.lookback_days == 90
        assert data.min_nights == 5

    @pytest.mark.parametrize(
        "body",
        [
            {"lookback_days": 6},
            {"lookback_days": 366},
            {"min_nights": 0},
            {"min_nights": 61},
            {"unknown": 1},
        ],
    )
    def test_recalculate_rejects_bad_values(self, body):
        with pytest.raises(ValidationError):
            ZoneBaselineRecalculate(**body)

    def test_filter_limits(self):
        with pytest.raises(ValidationError):
            ZoneBaselineFilter(limit=0)
        with pytest.raises(ValidationError):
            ZoneBaselineFilter(limit=201)
        with pytest.raises(ValidationError):
            ZoneBaselineFilter(offset=-1)


class TestZoneBaselineService:
    def test_list_baselines(self, db_session, sample_coordinator, sample_baseline):
        baselines = zone_baseline_service.list_baselines(
            db_session, sample_coordinator, ZoneBaselineFilter()
        )

        assert [item.baseline_id for item in baselines] == [sample_baseline.baseline_id]

    def test_list_baselines_officer_forbidden(self, db_session, sample_officer):
        with pytest.raises(HTTPException) as error:
            zone_baseline_service.list_baselines(
                db_session, sample_officer, ZoneBaselineFilter()
            )

        assert error.value.status_code == 403

    def test_list_baselines_inactive_user(self, db_session, sample_coordinator):
        sample_coordinator.is_active = False

        with pytest.raises(HTTPException) as error:
            zone_baseline_service.list_baselines(
                db_session, sample_coordinator, ZoneBaselineFilter()
            )

        assert error.value.status_code == 403

    def test_get_baseline(self, db_session, sample_coordinator, sample_baseline):
        found = zone_baseline_service.get_baseline(
            db_session, sample_coordinator, sample_baseline.baseline_id
        )

        assert found.baseline_id == sample_baseline.baseline_id

    def test_get_baseline_officer_forbidden(
        self, db_session, sample_officer, sample_baseline
    ):
        with pytest.raises(HTTPException) as error:
            zone_baseline_service.get_baseline(
                db_session, sample_officer, sample_baseline.baseline_id
            )

        assert error.value.status_code == 403

    def test_get_baseline_not_found(self, db_session, sample_coordinator):
        with pytest.raises(HTTPException) as error:
            zone_baseline_service.get_baseline(
                db_session, sample_coordinator, uuid.uuid4()
            )

        assert error.value.status_code == 404

    def test_recalculate_uses_median_per_band(
        self, db_session, sample_coordinator, sample_zone
    ):
        add_band_readings(
            db_session, sample_zone, MoonBand.DARK, ["10", "20", "30", "40", "1000"]
        )

        result = zone_baseline_service.recalculate(
            db_session, sample_coordinator, ZoneBaselineRecalculate()
        )

        assert len(result.updated) == 1
        assert result.updated[0].moon_band == MoonBand.DARK
        assert result.updated[0].expected_light_index == Decimal("30.0000")
        assert result.updated[0].nights_used == 5
        assert {item.moon_band for item in result.skipped} == {
            MoonBand.PARTIAL,
            MoonBand.BRIGHT,
        }

    def test_recalculate_skips_bands_with_too_few_nights(
        self, db_session, sample_coordinator, sample_zone
    ):
        add_band_readings(db_session, sample_zone, MoonBand.BRIGHT, ["50", "60"])

        result = zone_baseline_service.recalculate(
            db_session, sample_coordinator, ZoneBaselineRecalculate(min_nights=3)
        )
        bright = [item for item in result.skipped if item.moon_band == MoonBand.BRIGHT]

        assert result.updated == []
        assert bright[0].nights_found == 2
        assert db_session.query(ZoneBaseline).count() == 0

    def test_recalculate_updates_existing_baseline(
        self, db_session, sample_coordinator, sample_zone, sample_baseline
    ):
        add_band_readings(db_session, sample_zone, MoonBand.DARK, ["5", "7", "9"])

        result = zone_baseline_service.recalculate(
            db_session, sample_coordinator, ZoneBaselineRecalculate(min_nights=3)
        )

        assert result.updated[0].baseline_id == sample_baseline.baseline_id
        assert result.updated[0].expected_light_index == Decimal("7.0000")
        assert result.updated[0].nights_used == 3
        assert db_session.query(ZoneBaseline).count() == 1

    def test_recalculate_one_zone(
        self, db_session, sample_coordinator, sample_zone, second_zone
    ):
        add_band_readings(db_session, sample_zone, MoonBand.DARK, ["1", "2", "3"])
        add_band_readings(db_session, second_zone, MoonBand.DARK, ["4", "5", "6"])

        result = zone_baseline_service.recalculate(
            db_session,
            sample_coordinator,
            ZoneBaselineRecalculate(zone_id=second_zone.zone_id, min_nights=3),
        )

        assert [item.zone_id for item in result.updated] == [second_zone.zone_id]
        assert result.updated[0].expected_light_index == Decimal("5.0000")

    def test_recalculate_unknown_zone(self, db_session, sample_coordinator):
        with pytest.raises(HTTPException) as error:
            zone_baseline_service.recalculate(
                db_session,
                sample_coordinator,
                ZoneBaselineRecalculate(zone_id=uuid.uuid4()),
            )

        assert error.value.status_code == 404

    def test_recalculate_officer_forbidden(self, db_session, sample_officer):
        with pytest.raises(HTTPException) as error:
            zone_baseline_service.recalculate(
                db_session, sample_officer, ZoneBaselineRecalculate()
            )

        assert error.value.status_code == 403

    def test_recalculate_ignores_old_readings(
        self, db_session, sample_coordinator, sample_zone
    ):
        old_day = utcnow().date() - timedelta(days=120)
        for offset in range(5):
            add_reading(db_session, sample_zone, old_day - timedelta(days=offset), "99")

        result = zone_baseline_service.recalculate(
            db_session, sample_coordinator, ZoneBaselineRecalculate(min_nights=1)
        )

        assert result.updated == []


class TestZoneBaselineRouter:
    def test_list(self, baseline_client, sample_coordinator, sample_baseline):
        response = baseline_client.get(
            BASELINE_API, headers=baseline_headers(sample_coordinator)
        )

        assert response.status_code == 200
        assert response.json()[0]["baseline_id"] == str(sample_baseline.baseline_id)
        assert response.json()[0]["expected_light_index"] == 100.0

    def test_list_officer_forbidden(self, baseline_client, sample_officer):
        response = baseline_client.get(
            BASELINE_API, headers=baseline_headers(sample_officer)
        )

        assert response.status_code == 403

    def test_list_filter_by_band(
        self, baseline_client, sample_coordinator, sample_baseline
    ):
        response = baseline_client.get(
            BASELINE_API,
            params={"moon_band": "bright"},
            headers=baseline_headers(sample_coordinator),
        )

        assert response.status_code == 200
        assert response.json() == []

    def test_list_bad_band(self, baseline_client, sample_coordinator):
        response = baseline_client.get(
            BASELINE_API,
            params={"moon_band": "blue"},
            headers=baseline_headers(sample_coordinator),
        )

        assert response.status_code == 422

    def test_list_requires_login(self, baseline_client):
        assert baseline_client.get(BASELINE_API).status_code == 401

    def test_get(self, baseline_client, sample_coordinator, sample_baseline):
        response = baseline_client.get(
            f"{BASELINE_API}/{sample_baseline.baseline_id}",
            headers=baseline_headers(sample_coordinator),
        )

        assert response.status_code == 200
        assert response.json()["moon_band"] == "dark"

    def test_get_officer_forbidden(
        self, baseline_client, sample_officer, sample_baseline
    ):
        response = baseline_client.get(
            f"{BASELINE_API}/{sample_baseline.baseline_id}",
            headers=baseline_headers(sample_officer),
        )

        assert response.status_code == 403

    def test_get_not_found(self, baseline_client, sample_coordinator):
        response = baseline_client.get(
            f"{BASELINE_API}/{uuid.uuid4()}",
            headers=baseline_headers(sample_coordinator),
        )

        assert response.status_code == 404

    def test_recalculate(
        self, baseline_client, db_session, sample_coordinator, sample_zone
    ):
        add_band_readings(db_session, sample_zone, MoonBand.DARK, ["2", "4", "6"])

        response = baseline_client.post(
            f"{BASELINE_API}/recalculate",
            json={"min_nights": 3},
            headers=baseline_headers(sample_coordinator),
        )

        assert response.status_code == 200
        assert response.json()["updated"][0]["expected_light_index"] == 4.0
        assert len(response.json()["skipped"]) == 2

    def test_recalculate_officer_forbidden(self, baseline_client, sample_officer):
        response = baseline_client.post(
            f"{BASELINE_API}/recalculate",
            json={},
            headers=baseline_headers(sample_officer),
        )

        assert response.status_code == 403

    def test_recalculate_bad_body(self, baseline_client, sample_coordinator):
        response = baseline_client.post(
            f"{BASELINE_API}/recalculate",
            json={"lookback_days": 1},
            headers=baseline_headers(sample_coordinator),
        )

        assert response.status_code == 422
