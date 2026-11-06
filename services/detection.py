import logging
import statistics
from decimal import Decimal

import numpy as np
from fastapi import HTTPException, status
from shapely.geometry import Point, shape
from sklearn.cluster import DBSCAN
from sqlalchemy.orm import Session

from models.alert import Alert
from models.user import User
from models.zone import Zone
from models.zone_light_reading import IngestionStatus, ZoneLightReading
from repositories.zone_baseline import zone_baseline_repository
from schemas.detection import (
    DetectionAlert,
    DetectionPoint,
    DetectionResult,
    DetectionRun,
)
from services.zone_baseline import moon_band_for, zone_baseline_service

logger = logging.getLogger(__name__)

EARTH_RADIUS_M = 6_371_000
SCORE_THRESHOLD = 3.0


def cluster_labels(points: list[DetectionPoint], radius_m: float, min_points: int):
    """DBSCAN on lat/lon in metres. -1 means noise (not part of a cluster)."""
    if len(points) < min_points:
        return [-1] * len(points)

    coords = np.radians([[p.latitude, p.longitude] for p in points])
    model = DBSCAN(
        eps=radius_m / EARTH_RADIUS_M,
        min_samples=min_points,
        metric="haversine",
        algorithm="ball_tree",
    )
    return model.fit(coords).labels_.tolist()


def spread_for(baseline, zone: Zone) -> float:
    """Never smaller than the light of one minimal cluster.

    A quiet zone's baseline can be 0 with a tiny spread, which would turn
    any small cluster into a near-100% alert.
    """
    minimal_cluster = float(zone.radiance_threshold) * zone.min_cluster_points
    return max(float(baseline.spread), minimal_cluster)


def confidence_from(score: float) -> float:
    """Map an anomaly score to 0–1: 0.5 at the threshold, approaching 1 as it grows."""
    return score / (score + SCORE_THRESHOLD)


class DetectionService:
    def run(self, db: Session, current_user: User, data: DetectionRun):
        zone_baseline_service.check_coordinator(current_user)

        already_run = (
            db.query(ZoneLightReading)
            .filter(ZoneLightReading.observation_date == data.observation_date)
            .first()
        )
        if already_run is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Detection has already been run for this night.",
            )

        moon_band = moon_band_for(data.observation_date)
        candidates = [p for p in data.points if not p.near_shore]
        zones = (
            db.query(Zone).filter(Zone.is_active.is_(True)).order_by(Zone.name).all()
        )

        readings_saved = 0
        alerts: list[DetectionAlert] = []

        for zone in zones:
            polygon = shape(zone.boundary)
            if polygon.is_empty or not polygon.is_valid:
                logger.warning(f"skipping zone {zone.zone_id}: invalid boundary")
                continue
            threshold = float(zone.radiance_threshold)
            inside = [
                p
                for p in candidates
                if p.radiance >= threshold
                and polygon.contains(Point(p.longitude, p.latitude))
            ]

            labels = cluster_labels(
                inside, float(zone.cluster_radius_m), zone.min_cluster_points
            )
            clusters: dict[int, list[DetectionPoint]] = {}
            for point, label in zip(inside, labels):
                if label != -1:
                    clusters.setdefault(label, []).append(point)

            light_index = sum(p.radiance for p in inside)
            reading = ZoneLightReading(
                zone_id=zone.zone_id,
                observation_date=data.observation_date,
                ingestion_status=IngestionStatus.RECEIVED,
                light_index=Decimal(f"{light_index:.4f}"),
                hotspot_pixel_count=len(inside),
                cluster_count=len(clusters),
            )
            db.add(reading)
            db.flush()
            readings_saved += 1

            baseline = zone_baseline_repository.get_by_zone_band(
                db, zone.zone_id, moon_band
            )
            if baseline is None or not clusters:
                continue

            score = (light_index - float(baseline.expected_light_index)) / spread_for(
                baseline, zone
            )
            confidence = confidence_from(score) if score > 0 else 0.0
            if score < SCORE_THRESHOLD or confidence < float(zone.confidence_threshold):
                continue

            for label, members in clusters.items():
                alert = Alert(
                    zone_id=zone.zone_id,
                    reading_id=reading.reading_id,
                    cluster_label=int(label),
                    point_count=len(members),
                    confidence=Decimal(f"{confidence:.4f}"),
                    centroid_latitude=Decimal(
                        f"{statistics.mean(p.latitude for p in members):.6f}"
                    ),
                    centroid_longitude=Decimal(
                        f"{statistics.mean(p.longitude for p in members):.6f}"
                    ),
                )
                db.add(alert)
                db.flush()
                alerts.append(
                    DetectionAlert(
                        alert_id=str(alert.alert_id),
                        zone_id=str(zone.zone_id),
                        cluster_label=int(label),
                        point_count=len(members),
                        score=round(score, 4),
                        confidence=round(confidence, 4),
                    )
                )

        db.commit()
        logger.info(
            f"detection run by {current_user.user_id} for {data.observation_date}: "
            f"{readings_saved} readings, {len(alerts)} alerts"
        )
        return DetectionResult(
            observation_date=data.observation_date,
            moon_band=moon_band,
            readings_saved=readings_saved,
            alerts=alerts,
        )


detection_service = DetectionService()
