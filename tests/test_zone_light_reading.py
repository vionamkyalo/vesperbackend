import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from services.zone_baseline import moon_band_for
import core.security as security
from database import get_db, utcnow
from main import app
from models.zone_light_reading import IngestionStatus
from schemas.zone_light_reading import ZoneLightReadingCreate, ZoneLightReadingResults
from services.zone_light_reading import zone_light_reading_service

URL = "/api/zone-light-readings"
NIGHT = date(2025, 1, 15)


def results(**overrides):
    values = {
        "light_index": Decimal("1234.5678"),
        "valid_pixel_count": 500,
        "hotspot_pixel_count": 40,
        "cluster_count": 3,
    }
    values.update(overrides)
    return ZoneLightReadingResults(**values)


def create_reading(db_session, zone, night=NIGHT):
    reading, _ = zone_light_reading_service.create_reading(
        db_session,
        ZoneLightReadingCreate(zone_id=zone.zone_id, observation_date=night),
    )
    return reading


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def log_in_as(user):
    for name in dir(security):
        if name.startswith("get_current"):
            app.dependency_overrides[getattr(security, name)] = lambda: user


class TestResultsSchema:
    def test_valid_results_are_accepted(self):
        data = results()

        assert data.cluster_count == 3

    def test_more_hotspots_than_valid_pixels_is_rejected(self):
        with pytest.raises(ValidationError):
            results(hotspot_pixel_count=600)

    def test_more_clusters_than_hotspots_is_rejected(self):
        with pytest.raises(ValidationError):
            results(cluster_count=50)

    def test_negative_light_index_is_rejected(self):
        with pytest.raises(ValidationError):
            results(light_index=Decimal("-1"))


class TestCreateReading:
    def test_creates_pending_reading(self, db_session, sample_zone):
        reading, created = zone_light_reading_service.create_reading(
            db_session,
            ZoneLightReadingCreate(zone_id=sample_zone.zone_id, observation_date=NIGHT),
        )

        assert created is True
        assert reading.ingestion_status == IngestionStatus.PENDING
        assert reading.light_index is None

    def test_same_zone_and_night_returns_existing(self, db_session, sample_zone):
        first = create_reading(db_session, sample_zone)

        second, created = zone_light_reading_service.create_reading(
            db_session,
            ZoneLightReadingCreate(zone_id=sample_zone.zone_id, observation_date=NIGHT),
        )

        assert created is False
        assert second.reading_id == first.reading_id

    def test_future_night_is_rejected(self, db_session, sample_zone):
        tomorrow = utcnow().date() + timedelta(days=1)

        with pytest.raises(HTTPException) as error:
            create_reading(db_session, sample_zone, night=tomorrow)

        assert error.value.status_code == 400

    def test_unknown_zone_is_rejected(self, db_session):
        with pytest.raises(HTTPException) as error:
            zone_light_reading_service.create_reading(
                db_session,
                ZoneLightReadingCreate(zone_id=uuid.uuid4(), observation_date=NIGHT),
            )

        assert error.value.status_code == 404


class TestRecordResults:
    def test_records_results(self, db_session, sample_zone):
        reading = create_reading(db_session, sample_zone)

        updated = zone_light_reading_service.record_results(
            db_session, reading.reading_id, results()
        )

        assert updated.ingestion_status == IngestionStatus.RECEIVED
        assert updated.light_index == Decimal("1234.5678")
        assert updated.valid_pixel_count == 500
        assert updated.hotspot_pixel_count == 40
        assert updated.cluster_count == 3

    def test_results_cannot_be_recorded_twice(self, db_session, sample_zone):
        reading = create_reading(db_session, sample_zone)
        zone_light_reading_service.record_results(
            db_session, reading.reading_id, results()
        )

        with pytest.raises(HTTPException) as error:
            zone_light_reading_service.record_results(
                db_session, reading.reading_id, results()
            )

        assert error.value.status_code == 409

    def test_unknown_reading_returns_404(self, db_session):
        with pytest.raises(HTTPException) as error:
            zone_light_reading_service.record_results(
                db_session, uuid.uuid4(), results()
            )

        assert error.value.status_code == 404


class TestIngestionError:
    def test_marks_ingestion_error(self, db_session, sample_zone):
        reading = create_reading(db_session, sample_zone)

        updated = zone_light_reading_service.record_ingestion_error(
            db_session, reading.reading_id
        )

        assert updated.ingestion_status == IngestionStatus.INGESTION_ERROR
        assert updated.light_index is None

    def test_retry_after_error_records_results(self, db_session, sample_zone):
        reading = create_reading(db_session, sample_zone)
        zone_light_reading_service.record_ingestion_error(
            db_session, reading.reading_id
        )

        updated = zone_light_reading_service.record_results(
            db_session, reading.reading_id, results()
        )

        assert updated.ingestion_status == IngestionStatus.RECEIVED

    def test_received_reading_cannot_become_error(self, db_session, sample_zone):
        reading = create_reading(db_session, sample_zone)
        zone_light_reading_service.record_results(
            db_session, reading.reading_id, results()
        )

        with pytest.raises(HTTPException) as error:
            zone_light_reading_service.record_ingestion_error(
                db_session, reading.reading_id
            )

        assert error.value.status_code == 409


class TestRoutes:
    def test_coordinator_lists_readings_for_a_zone(
        self, client, db_session, sample_coordinator, sample_zone
    ):
        reading = create_reading(db_session, sample_zone)
        log_in_as(sample_coordinator)

        response = client.get(
            URL,
            params={
                "zone_id": str(sample_zone.zone_id),
                "observation_date": NIGHT.isoformat(),
            },
        )

        assert response.status_code == 200, response.json()
        ids = [item["reading_id"] for item in response.json()]
        assert ids == [str(reading.reading_id)]

    def test_coordinator_gets_one_reading(
        self, client, db_session, sample_coordinator, sample_zone
    ):
        reading = create_reading(db_session, sample_zone)
        log_in_as(sample_coordinator)

        response = client.get(f"{URL}/{reading.reading_id}")

        assert response.status_code == 200, response.json()
        assert response.json()["reading_id"] == str(reading.reading_id)
        assert response.json()["ingestion_status"] == "pending"

    def test_unknown_reading_returns_404(self, client, sample_coordinator):
        log_in_as(sample_coordinator)

        response = client.get(f"{URL}/{uuid.uuid4()}")

        assert response.status_code == 404, response.json()

    def test_officer_is_refused(self, client, sample_officer):
        log_in_as(sample_officer)

        response = client.get(URL)

        assert response.status_code == 403, response.json()

    def test_login_is_required(self, client):
        response = client.get(URL)

        assert response.status_code == 401, response.json()
        
    def test_reading_includes_moon_band_of_its_night(
        self, client, db_session, sample_coordinator, sample_zone
    ):
        reading = create_reading(db_session, sample_zone)
        log_in_as(sample_coordinator)

        response = client.get(f"{URL}/{reading.reading_id}")

        assert response.status_code == 200, response.json()
        assert response.json()["moon_band"] == moon_band_for(NIGHT).value