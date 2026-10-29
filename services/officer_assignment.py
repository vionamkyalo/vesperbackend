import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.config import get_settings
from models.officer_assignment import OfficerLocation
from models.user import User, UserRole
from repositories.officer_assignment import OfficerLocationRepository
from schemas.officer_assignment import (
    ArrivalCheckRead,
    LocationListQuery,
    LocationPurgeResult,
    OfficerLocationCreate,
    OfficerLocationPage,
    OfficerLocationRead,
)

audit_log = logging.getLogger("vesper.audit")

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(
    lat1: Decimal | float,
    lon1: Decimal | float,
    lat2: Decimal | float,
    lon2: Decimal | float,
) -> float:

    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    d_phi = phi2 - phi1
    d_lambda = math.radians(float(lon2) - float(lon1))
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def evaluate_jump(
    previous: OfficerLocation | None, current: OfficerLocation, max_speed_kmh: float
) -> tuple[bool, float | None]:
    if previous is None:
        return False, None

    distance = haversine_m(
        previous.latitude, previous.longitude, current.latitude, current.longitude
    )
    tolerance = float(previous.accuracy_m or 0) + float(current.accuracy_m or 0)
    effective_distance = max(0.0, distance - tolerance)
    seconds = abs((current.recorded_at - previous.recorded_at).total_seconds())

    if seconds == 0:
        return effective_distance > 0, None

    speed_kmh = effective_distance / seconds * 3.6
    return speed_kmh > max_speed_kmh, round(speed_kmh, 2)


class OfficerLocationService:
    def __init__(self, db: Session):
        self.repo = OfficerLocationRepository(db)

    def _annotate_jumps(self, locations: list[OfficerLocation]) -> None:
        max_speed = get_settings().max_officer_speed_kmh
        by_officer: dict[uuid.UUID, list[OfficerLocation]] = {}
        for location in locations:
            by_officer.setdefault(location.officer_id, []).append(location)

        for officer_id, fixes in by_officer.items():
            fixes.sort(key=lambda fix: fix.recorded_at)
            first = fixes[0]
            previous = self.repo.get_previous_for_officer(
                officer_id, first.recorded_at, exclude_location_id=first.location_id
            )
            for fix in fixes:
                fix.jump_flagged, fix.speed_from_previous_kmh = evaluate_jump(
                    previous, fix, max_speed
                )
                previous = fix

    def _to_page(
        self, items: list[OfficerLocation], total: int, skip: int, limit: int
    ) -> OfficerLocationPage:
        self._annotate_jumps(items)
        return OfficerLocationPage(
            items=[OfficerLocationRead.model_validate(item) for item in items],
            total=total,
            skip=skip,
            limit=limit,
        )

    def record_location(
        self,
        data: OfficerLocationCreate,
        officer: User,
        now: datetime | None = None,
    ) -> OfficerLocation:

        settings = get_settings()
        now = now or _utcnow()

        if data.recorded_at > now + timedelta(
            minutes=settings.location_clock_skew_minutes
        ):
            raise HTTPException(422, "recorded_at is in the future")
        if data.recorded_at < now - timedelta(days=settings.location_retention_days):
            raise HTTPException(
                422,
                f"recorded_at is older than the {settings.location_retention_days}-day "
                "retention period",
            )

        if data.alert_id is not None:
            alert = self.repo.get_alert(data.alert_id)
            if alert is None:
                raise HTTPException(404, "Alert not found")
            if not self.repo.officer_was_assigned(alert, officer.user_id):
                raise HTTPException(
                    403, "A location can only be linked to an alert assigned to you"
                )

        # location_id is never accepted from the client: the server generates it.
        location = OfficerLocation(
            location_id=uuid.uuid4(),
            officer_id=officer.user_id,
            alert_id=data.alert_id,
            latitude=data.latitude,
            longitude=data.longitude,
            accuracy_m=data.accuracy_m,
            recorded_at=data.recorded_at,
        )
        location = self.repo.create(location)

        self._annotate_jumps([location])
        audit_log.info(
            "officer_location.recorded location_id=%s officer_id=%s alert_id=%s jump_flagged=%s",
            location.location_id,
            location.officer_id,
            location.alert_id,
            location.jump_flagged,
        )
        return location

    def list_my_locations(
        self, officer: User, query: LocationListQuery
    ) -> OfficerLocationPage:
        own_query = query.model_copy(update={"officer_id": officer.user_id})
        items, total = self.repo.list_filtered(own_query)
        return self._to_page(items, total, query.skip, query.limit)

    def list_locations(self, query: LocationListQuery) -> OfficerLocationPage:
        items, total = self.repo.list_filtered(query)
        return self._to_page(items, total, query.skip, query.limit)

    def latest_locations(self) -> list[OfficerLocation]:
        items = self.repo.latest_per_officer()
        self._annotate_jumps(items)
        return items

    def get_location(
        self, location_id: uuid.UUID, current_user: User
    ) -> OfficerLocation:
        location = self.repo.get_by_id(location_id)

        if location is None or (
            current_user.role == UserRole.PATROL_OFFICER
            and location.officer_id != current_user.user_id
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
        self._annotate_jumps([location])
        return location

    def check_arrival(
        self, alert_id: uuid.UUID, current_user: User
    ) -> ArrivalCheckRead:

        settings = get_settings()

        alert = self.repo.get_alert(alert_id)
        if alert is None:
            raise HTTPException(404, "Alert not found")

        if current_user.role == UserRole.PATROL_OFFICER:
            if not self.repo.officer_was_assigned(alert, current_user.user_id):
                raise HTTPException(403, "This alert is not assigned to you")
            officer_id = current_user.user_id
        else:
            officer_id = alert.officer_id

        zone = alert.zone
        radius = (
            float(zone.cluster_radius_m)
            if zone is not None and zone.cluster_radius_m
            else settings.default_arrival_radius_m
        )

        positions = self.repo.list_for_alert(alert_id, officer_id) if officer_id else []
        self._annotate_jumps(positions)

        closest_distance: float | None = None
        closest_id: uuid.UUID | None = None
        first_arrival: datetime | None = None
        ignored = 0
        for fix in positions:
            if fix.jump_flagged:
                ignored += 1
                continue
            distance = haversine_m(
                fix.latitude,
                fix.longitude,
                alert.centroid_latitude,
                alert.centroid_longitude,
            )
            if closest_distance is None or distance < closest_distance:
                closest_distance, closest_id = distance, fix.location_id
            if (
                max(0.0, distance - float(fix.accuracy_m or 0)) <= radius
                and first_arrival is None
            ):
                first_arrival = fix.recorded_at

        return ArrivalCheckRead(
            alert_id=alert.alert_id,
            officer_id=officer_id,
            arrived=first_arrival is not None,
            arrival_radius_m=radius,
            closest_distance_m=round(closest_distance, 2)
            if closest_distance is not None
            else None,
            closest_location_id=closest_id,
            first_arrival_at=first_arrival,
            positions_checked=len(positions),
            positions_ignored_as_jumps=ignored,
        )

    def purge_expired_locations(
        self, current_user: User | None = None, now: datetime | None = None
    ) -> LocationPurgeResult:

        settings = get_settings()
        now = now or _utcnow()
        cutoff = now - timedelta(days=settings.location_retention_days)

        expired_ids = self.repo.list_unlinked_older_than(cutoff)
        for fix, alert in self.repo.list_linked_to_finished_alerts():
            timestamps = [
                alert.verified_at,
                alert.reported_at,
                alert.assigned_at,
                alert.created_at,
                fix.recorded_at,
            ]
            if max(t for t in timestamps if t is not None) < cutoff:
                expired_ids.append(fix.location_id)

        deleted = self.repo.delete_by_ids(expired_ids)
        audit_log.info(
            "officer_location.purged count=%s cutoff=%s by=%s",
            deleted,
            cutoff.isoformat(),
            current_user.user_id if current_user else "scheduler",
        )
        return LocationPurgeResult(deleted_count=deleted, cutoff=cutoff)
