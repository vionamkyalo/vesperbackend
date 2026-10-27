from datetime import date
from types import SimpleNamespace

import h5py
import numpy as np
import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from models.zone_light_reading import ZoneLightReading
from services.ingestion import ingestion_service, read_points

GRID = "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields"
SIZE = 240
STEP = 10 / SIZE
BBOX = [26.5, -18.6, 29.5, -16.3]
NIGHT = date(2026, 10, 10)


def pixel(lat, lon):
    return int((-10 - lat) / STEP), int((lon - 20) / STEP)


def make_h5(path, bright=(), cloud_bits=0, day=False):
    raw = np.zeros((SIZE, SIZE), dtype="uint16")
    cloud = np.full((SIZE, SIZE), (cloud_bits << 6) | int(day), dtype="uint16")
    for lat, lon, value in bright:
        row, col = pixel(lat, lon)
        raw[row, col] = value
    with h5py.File(path, "w") as file:
        fields = file.create_group(GRID)
        radiance = fields.create_dataset("DNB_At_Sensor_Radiance_500m", data=raw)
        radiance.attrs["_FillValue"] = 65535
        radiance.attrs["scale_factor"] = 1.0
        fields.create_dataset("QF_Cloud_Mask", data=cloud)
    return path


class TestReadPoints:
    def test_bright_pixel_becomes_point(self, tmp_path):
        path = make_h5(tmp_path / "a.h5", bright=[(-16.85, 28.05, 500)])

        points, clear = read_points(path, "h20v10", BBOX, min_radiance=10)

        assert len(points) == 1
        assert points[0].radiance == 500
        assert points[0].latitude == pytest.approx(-16.85, abs=STEP)
        assert points[0].longitude == pytest.approx(28.05, abs=STEP)
        assert clear == 1.0

    def test_dim_pixel_dropped(self, tmp_path):
        path = make_h5(tmp_path / "a.h5", bright=[(-16.85, 28.05, 5)])
        assert read_points(path, "h20v10", BBOX, min_radiance=10)[0] == []

    def test_cloudy_pixels_dropped(self, tmp_path):
        path = make_h5(tmp_path / "a.h5", bright=[(-16.85, 28.05, 500)], cloud_bits=3)
        points, clear = read_points(path, "h20v10", BBOX, min_radiance=10)
        assert points == []
        assert clear == 0.0

    def test_daytime_pixels_dropped(self, tmp_path):
        path = make_h5(tmp_path / "a.h5", bright=[(-16.85, 28.05, 500)], day=True)
        assert read_points(path, "h20v10", BBOX, min_radiance=10)[0] == []

    def test_fill_value_dropped(self, tmp_path):
        path = make_h5(tmp_path / "a.h5", bright=[(-16.85, 28.05, 65535)])
        assert read_points(path, "h20v10", BBOX, min_radiance=10)[0] == []


class TestIngestionService:
    def test_clear_night_saves_readings(
        self, tmp_path, db_session, sample_coordinator, sample_zone
    ):
        path = make_h5(tmp_path / "a.h5", bright=[(-16.85, 28.05, 500)])

        result = ingestion_service.run_for_night(
            db_session, sample_coordinator, NIGHT, path
        )
        reading = db_session.query(ZoneLightReading).one()

        assert result.skipped is False
        assert result.detection.readings_saved == 1
        assert reading.hotspot_pixel_count == 1

    def test_cloudy_night_skipped(
        self, tmp_path, db_session, sample_coordinator, sample_zone
    ):
        path = make_h5(tmp_path / "a.h5", cloud_bits=3)

        result = ingestion_service.run_for_night(
            db_session, sample_coordinator, NIGHT, path
        )

        assert result.skipped is True
        assert db_session.query(ZoneLightReading).count() == 0

    def test_officer_forbidden(self, tmp_path, db_session, sample_officer, sample_zone):
        path = make_h5(tmp_path / "a.h5")
        with pytest.raises(HTTPException) as error:
            ingestion_service.run_for_night(db_session, sample_officer, NIGHT, path)
        assert error.value.status_code == 403

    def test_download_without_token(self, monkeypatch):
        monkeypatch.setattr(
            "services.ingestion.get_settings",
            lambda: SimpleNamespace(earthdata_token=SecretStr("")),
        )
        with pytest.raises(HTTPException) as error:
            ingestion_service.download(NIGHT)
        assert error.value.status_code == 503
