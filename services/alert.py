import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.alert import Alert, AlertStatus, VerificationResult
from models.user import User, UserRole
from models.zone_light_reading import IngestionStatus
from repositories.alert import AlertRepository
from schemas.alert import (
    AlertCreate,
    AlertListQuery,
    AlertPage,
    AlertRead,
    AlertStatusUpdate,
    AlertVerificationUpdate,
    MyAlertsQuery,
)

audit_log = logging.getLogger("vesper.audit")


def _on_segment(x: float, y: float, a: list, b: list, eps: float = 1e-12) -> bool:
    (x1, y1), (x2, y2) = (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    if abs(cross) > eps:
        return False
    return min(x1, x2) - eps <= x <= max(x1, x2) + eps and (
        min(y1, y2) - eps <= y <= max(y1, y2) + eps
    )


def _in_ring(x: float, y: float, ring: list) -> bool:
    inside = False
    count = len(ring)
    for i in range(count):
        a, b = ring[i], ring[(i + 1) % count]
        if _on_segment(x, y, a, b):
            return True
        xa, ya, xb, yb = float(a[0]), float(a[1]), float(b[0]), float(b[1])
        if (ya > y) != (yb > y):
            x_cross = xa + (y - ya) * (xb - xa) / (yb - ya)
            if x < x_cross:
                inside = not inside
    return inside


def _in_polygon(x: float, y: float, rings: list) -> bool:
    if not rings or not _in_ring(x, y, rings[0]):
        return False
    return not any(_in_ring(x, y, hole) for hole in rings[1:])


def point_in_geojson(
    lat: Decimal | float, lon: Decimal | float, geometry: dict | None
) -> bool | None:

    if not isinstance(geometry, dict):
        return None
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if not coordinates:
        return None
    x, y = float(lon), float(lat)
    if geometry_type == "Polygon":
        return _in_polygon(x, y, coordinates)
    if geometry_type == "MultiPolygon":
        return any(_in_polygon(x, y, polygon) for polygon in coordinates)
    return None


ALLOWED_STATUS_TRANSITIONS: dict[AlertStatus, set[AlertStatus]] = {
    AlertStatus.NEW: {AlertStatus.IN_PROGRESS, AlertStatus.DISMISSED},
    AlertStatus.IN_PROGRESS: {AlertStatus.CLOSED, AlertStatus.DISMISSED},
    AlertStatus.DISMISSED: set(),
    AlertStatus.CLOSED: set(),
}

INSUFFICIENT_DATA_DETAIL = (
    "Insufficient data: the satellite reading for this night was not received, "
    "so no alert can be raised from it"
)
DUPLICATE_ALERT_DETAIL = "An alert already exists for this reading and cluster"


class AlertService:
    def __init__(self, db: Session):
        self.repo = AlertRepository(db)

    def _get_or_404(self, alert_id: uuid.UUID) -> Alert:
        alert = self.repo.get_by_id(alert_id)
        if alert is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
        return alert

    @staticmethod
    def _to_page(items: list[Alert], total: int, skip: int, limit: int) -> AlertPage:
        return AlertPage(
            items=[AlertRead.model_validate(item) for item in items],
            total=total,
            skip=skip,
            limit=limit,
        )

    def create_alert(self, data: AlertCreate, current_user: User) -> Alert:
        zone = self.repo.get_zone(data.zone_id)
        if zone is None:
            raise HTTPException(404, "Zone not found")
        if not zone.is_active:
            raise HTTPException(
                409, "Zone is not active; alerts are not raised for inactive zones"
            )

        reading = self.repo.get_reading(data.reading_id)
        if reading is None:
            raise HTTPException(404, "Reading not found")
        if reading.zone_id != zone.zone_id:
            raise HTTPException(422, "Reading does not belong to the given zone")
        if reading.ingestion_status != IngestionStatus.RECEIVED:
            raise HTTPException(409, INSUFFICIENT_DATA_DETAIL)

        threshold = zone.confidence_threshold
        if threshold is not None and data.confidence < threshold:
            raise HTTPException(
                422,
                f"Confidence {data.confidence} is below the zone threshold "
                f"{threshold}; the cluster is not saved as an alert",
            )

        min_points = zone.min_cluster_points
        if min_points is not None and data.point_count < min_points:
            raise HTTPException(
                422,
                f"point_count {data.point_count} is below the zone minimum "
                f"of {min_points} points per cluster",
            )

        if (
            point_in_geojson(
                data.centroid_latitude, data.centroid_longitude, zone.boundary
            )
            is False
        ):
            raise HTTPException(422, "Cluster centroid lies outside the zone boundary")

        if self.repo.get_by_reading_and_cluster(data.reading_id, data.cluster_label):
            raise HTTPException(409, DUPLICATE_ALERT_DETAIL)

        alert = Alert(
            alert_id=uuid.uuid4(),
            zone_id=data.zone_id,
            reading_id=data.reading_id,
            cluster_label=data.cluster_label,
            point_count=data.point_count,
            confidence=data.confidence,
            centroid_latitude=data.centroid_latitude,
            centroid_longitude=data.centroid_longitude,
            status=AlertStatus.NEW,
            verification_result=VerificationResult.PENDING,
        )
        try:
            alert = self.repo.create(alert)
        except IntegrityError:
            raise HTTPException(409, DUPLICATE_ALERT_DETAIL)

        audit_log.info(
            "alert.created alert_id=%s zone_id=%s by=%s confidence=%s threshold=%s",
            alert.alert_id,
            alert.zone_id,
            current_user.user_id,
            alert.confidence,
            threshold,
        )
        return alert

    def list_alerts(self, query: AlertListQuery) -> AlertPage:
        items, total = self.repo.list_filtered(query)
        return self._to_page(items, total, query.skip, query.limit)

    def list_my_alerts(self, officer: User, query: MyAlertsQuery) -> AlertPage:
        items, total = self.repo.list_for_officer(
            officer.user_id, query.status, query.skip, query.limit
        )
        return self._to_page(items, total, query.skip, query.limit)

    def get_alert(self, alert_id: uuid.UUID, current_user: User) -> Alert:
        alert = self._get_or_404(alert_id)
        if (
            current_user.role == UserRole.PATROL_OFFICER
            and alert.officer_id != current_user.user_id
        ):
            raise HTTPException(403, "This alert is not assigned to you")
        return alert

    def update_alert_status(
        self, alert_id: uuid.UUID, data: AlertStatusUpdate, current_user: User
    ) -> Alert:
        alert = self._get_or_404(alert_id)
        if data.status == alert.status:
            return alert

        if data.status not in ALLOWED_STATUS_TRANSITIONS[alert.status]:
            raise HTTPException(
                409,
                f"Cannot change alert status from {alert.status.value} "
                f"to {data.status.value}",
            )
        if (
            data.status == AlertStatus.CLOSED
            and alert.verification_result == VerificationResult.PENDING
        ):
            raise HTTPException(
                409, "Record a verification result before closing the alert"
            )

        previous = alert.status
        alert.status = data.status
        alert = self.repo.update(alert)
        audit_log.info(
            "alert.status_changed alert_id=%s from=%s to=%s by=%s",
            alert.alert_id,
            previous.value,
            alert.status.value,
            current_user.user_id,
        )
        return alert

    def record_verification(
        self,
        alert_id: uuid.UUID,
        data: AlertVerificationUpdate,
        current_user: User,
        now: datetime | None = None,
    ) -> Alert:
        alert = self._get_or_404(alert_id)
        if alert.status != AlertStatus.IN_PROGRESS:
            raise HTTPException(409, "Only alerts that are in progress can be verified")

        alert.verification_result = data.verification_result
        alert.verified_at = now or datetime.now(timezone.utc)
        alert = self.repo.update(alert)
        audit_log.info(
            "alert.verified alert_id=%s result=%s by=%s",
            alert.alert_id,
            alert.verification_result.value,
            current_user.user_id,
        )
        return alert
