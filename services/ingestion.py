import json
import logging
import shutil
import tempfile
import urllib.request
from datetime import date
from pathlib import Path

import h5py
import numpy as np
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.config import get_settings
from models.user import User
from models.zone import Zone
from schemas.detection import DetectionPoint, DetectionRun, IngestionResult
from services.detection import detection_service
from services.zone_baseline import zone_baseline_service

logger = logging.getLogger(__name__)

GRID_FIELDS = "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields"
TILE_DEGREES = 10


def tile_origin(tile: str):
    """Top-left corner (west longitude, north latitude) of a tile like 'h20v10'."""
    h, v = int(tile[1:3]), int(tile[4:6])
    return -180 + h * TILE_DEGREES, 90 - v * TILE_DEGREES


def _attr(dataset, name, default):
    return float(np.ravel(dataset.attrs.get(name, default))[0])


def _radiance_dataset(fields):
    for name in fields:
        if name.startswith("DNB_At_Sensor_Radiance"):
            return fields[name]
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="File has no DNB radiance layer.",
    )


def read_points(path, tile, bbox, min_radiance):
    """Read a VNP46A1 file and return the night's clear, lit points over the lake box."""
    min_lon, min_lat, max_lon, max_lat = bbox

    with h5py.File(path, "r") as file:
        fields = file[GRID_FIELDS]
        radiance_ds = _radiance_dataset(fields)
        raw = radiance_ds[...].astype("float64")
        fill = _attr(radiance_ds, "_FillValue", 65535)
        scale = _attr(radiance_ds, "scale_factor", 1.0)
        offset = _attr(radiance_ds, "add_offset", 0.0)
        cloud = fields["QF_Cloud_Mask"][...].astype("uint16")

    rows, cols = raw.shape
    step = TILE_DEGREES / rows
    west, north = tile_origin(tile)
    lons = west + (np.arange(cols) + 0.5) * step
    lats = north - (np.arange(rows) + 0.5) * step

    row_mask = (lats >= min_lat) & (lats <= max_lat)
    col_mask = (lons >= min_lon) & (lons <= max_lon)
    box = np.ix_(row_mask, col_mask)
    raw, cloud = raw[box], cloud[box]
    lats, lons = lats[row_mask], lons[col_mask]

    valid = raw != fill
    night = (cloud & 1) == 0
    clear = ((cloud >> 6) & 0b11) <= 1
    usable = valid & night & clear
    clear_fraction = float(usable.mean()) if usable.size else 0.0

    radiance = raw * scale + offset
    lit = usable & (radiance >= min_radiance)
    points = [
        DetectionPoint(
            latitude=float(lats[r]),
            longitude=float(lons[c]),
            radiance=float(radiance[r, c]),
        )
        for r, c in zip(*np.nonzero(lit))
    ]
    return points, clear_fraction


def _get(url, token):
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    return urllib.request.urlopen(request, timeout=120)


class IngestionService:
    def download(self, observation_date: date) -> Path:
        settings = get_settings()
        token = settings.earthdata_token.get_secret_value()
        if not token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Earthdata token is not configured.",
            )

        day_of_year = observation_date.timetuple().tm_yday
        folder = (
            f"{settings.laads_base_url}/{settings.laads_archive_set}/"
            f"{settings.viirs_daily_product}/{observation_date.year}/{day_of_year:03d}"
        )
        with _get(f"{folder}.json", token) as response:
            listing = json.load(response)
        items = listing.get("content", []) if isinstance(listing, dict) else listing

        name = next(
            (
                item["name"]
                for item in items
                if f".{settings.viirs_tile}." in item.get("name", "")
                and item["name"].endswith(".h5")
            ),
            None,
        )
        if name is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="NASA has no file for this night yet.",
            )

        target = Path(tempfile.mkdtemp()) / name
        with _get(f"{folder}/{name}", token) as response, open(target, "wb") as out:
            shutil.copyfileobj(response, out)
        logger.info(f"downloaded {name}")
        return target

    def run_for_night(
        self,
        db: Session,
        current_user: User,
        observation_date: date,
        h5_path: Path | None = None,
    ) -> IngestionResult:
        zone_baseline_service.check_coordinator(current_user)
        settings = get_settings()

        zones = db.query(Zone).filter(Zone.is_active.is_(True)).all()
        if not zones:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="There are no active zones to process.",
            )
        min_radiance = min(float(zone.radiance_threshold) for zone in zones)

        downloaded = h5_path is None
        path = self.download(observation_date) if downloaded else h5_path
        try:
            points, clear_fraction = read_points(
                path, settings.viirs_tile, settings.kariba_bbox, min_radiance
            )
        finally:
            if downloaded:
                shutil.rmtree(Path(path).parent, ignore_errors=True)

        if clear_fraction < settings.min_clear_fraction:
            logger.info(f"{observation_date} skipped: only {clear_fraction:.0%} clear")
            return IngestionResult(
                observation_date=observation_date,
                skipped=True,
                clear_fraction=round(clear_fraction, 4),
                points_found=len(points),
            )

        detection = detection_service.run(
            db,
            current_user,
            DetectionRun(observation_date=observation_date, points=points),
        )
        return IngestionResult(
            observation_date=observation_date,
            skipped=False,
            clear_fraction=round(clear_fraction, 4),
            points_found=len(points),
            detection=detection,
        )


ingestion_service = IngestionService()
