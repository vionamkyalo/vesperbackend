from datetime import date

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from core import security
from database import get_db
from models.alert import Alert
from models.zone_light_reading import ZoneLightReading
from schemas.detection import DetectionPoint, DetectionRun
from services.detection import detection_service

NIGHT = date(2026, 10, 10)  # a dark-moon night


def lights(count, radiance=50.0, near_shore=False):
    return [
        DetectionPoint(
            latitude=-16.85 + i * 0.001,
            longitude=28.05 + i * 0.001,
            radiance=radiance,
            near_shore=near_shore,
        )
        for i in range(count)
    ]


class TestDetectionService:
    def test_quiet_night_saves_zero_reading(
        self, db_session, sample_coordinator, sample_zone
    ):
        result = detection_service.run(
            db_session, sample_coordinator, DetectionRun(observation_date=NIGHT)
        )
        reading = db_session.query(ZoneLightReading).one()

        assert result.readings_saved == 1
        assert reading.light_index == 0
        assert reading.hotspot_pixel_count == 0
        assert reading.cluster_count == 0
        assert result.alerts == []

    def test_cluster_above_baseline_raises_alert(
        self, db_session, sample_coordinator, sample_zone, sample_baseline
    ):
        result = detection_service.run(
            db_session,
            sample_coordinator,
            DetectionRun(observation_date=NIGHT, points=lights(4)),
        )
        alert = db_session.query(Alert).one()

        assert len(result.alerts) == 1
        assert alert.zone_id == sample_zone.zone_id
        assert alert.point_count == 4
        assert result.alerts[0].confidence == pytest.approx(0.9709, abs=1e-4)

    def test_no_baseline_means_no_alert(
        self, db_session, sample_coordinator, sample_zone
    ):
        result = detection_service.run(
            db_session,
            sample_coordinator,
            DetectionRun(observation_date=NIGHT, points=lights(4)),
        )
        reading = db_session.query(ZoneLightReading).one()

        assert reading.cluster_count == 1
        assert result.alerts == []

    def test_dim_and_near_shore_lights_ignored(
        self, db_session, sample_coordinator, sample_zone
    ):
        points = lights(3, radiance=5.0) + lights(3, near_shore=True)

        detection_service.run(
            db_session,
            sample_coordinator,
            DetectionRun(observation_date=NIGHT, points=points),
        )
        reading = db_session.query(ZoneLightReading).one()

        assert reading.hotspot_pixel_count == 0

    def test_same_night_twice_conflicts(
        self, db_session, sample_coordinator, sample_zone
    ):
        run = DetectionRun(observation_date=NIGHT)
        detection_service.run(db_session, sample_coordinator, run)

        with pytest.raises(HTTPException) as error:
            detection_service.run(db_session, sample_coordinator, run)

        assert error.value.status_code == 409

    def test_officer_forbidden(self, db_session, sample_officer, sample_zone):
        with pytest.raises(HTTPException) as error:
            detection_service.run(
                db_session, sample_officer, DetectionRun(observation_date=NIGHT)
            )

        assert error.value.status_code == 403


class TestDetectionRouter:
    @pytest.fixture
    def client(self, db_session):
        from routers import detection as detection_router

        app = FastAPI()
        security.register_error_handlers(app)
        app.include_router(detection_router.router, prefix="/vesper")
        app.dependency_overrides[get_db] = lambda: db_session

        with TestClient(app) as test_client:
            yield test_client

    def test_run_as_coordinator(self, client, sample_coordinator, sample_zone):
        token = security.create_access_token(
            sample_coordinator.user_id, sample_coordinator.role.value
        )
        response = client.post(
            "/vesper/detections/run",
            json={"observation_date": "2026-10-10", "points": []},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
        assert response.json()["readings_saved"] == 1
