import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.alert import Alert, AlertStatus
from models.alert_assignment import AlertAssignment
from models.officer_assignment import OfficerLocation
from schemas.officer_assignment import LocationListQuery

FINISHED_ALERT_STATUSES = (AlertStatus.CLOSED, AlertStatus.DISMISSED)
_DELETE_CHUNK = 500


class OfficerLocationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, location_id: uuid.UUID) -> OfficerLocation | None:
        return self.db.get(OfficerLocation, location_id)

    def get_alert(self, alert_id: uuid.UUID) -> Alert | None:
        return self.db.get(Alert, alert_id)

    def get_previous_for_officer(
        self,
        officer_id: uuid.UUID,
        at_or_before: datetime,
        exclude_location_id: uuid.UUID | None = None,
    ) -> OfficerLocation | None:
        q = self.db.query(OfficerLocation).filter(
            OfficerLocation.officer_id == officer_id,
            OfficerLocation.recorded_at <= at_or_before,
        )
        if exclude_location_id is not None:
            q = q.filter(OfficerLocation.location_id != exclude_location_id)
        return q.order_by(
            OfficerLocation.recorded_at.desc(), OfficerLocation.synced_at.desc()
        ).first()

    def officer_was_assigned(self, alert: Alert, officer_id: uuid.UUID) -> bool:

        if alert.officer_id == officer_id:
            return True
        return (
            self.db.query(AlertAssignment.assignment_id)
            .filter(
                AlertAssignment.alert_id == alert.alert_id,
                AlertAssignment.officer_id == officer_id,
            )
            .first()
            is not None
        )

    def list_filtered(
        self, query: LocationListQuery
    ) -> tuple[list[OfficerLocation], int]:
        q = self.db.query(OfficerLocation)
        if query.officer_id is not None:
            q = q.filter(OfficerLocation.officer_id == query.officer_id)
        if query.alert_id is not None:
            q = q.filter(OfficerLocation.alert_id == query.alert_id)
        if query.recorded_from is not None:
            q = q.filter(OfficerLocation.recorded_at >= query.recorded_from)
        if query.recorded_to is not None:
            q = q.filter(OfficerLocation.recorded_at <= query.recorded_to)
        total = q.count()
        items = (
            q.order_by(
                OfficerLocation.recorded_at.desc(), OfficerLocation.location_id.desc()
            )
            .offset(query.skip)
            .limit(query.limit)
            .all()
        )
        return items, total

    def list_for_alert(
        self, alert_id: uuid.UUID, officer_id: uuid.UUID | None = None
    ) -> list[OfficerLocation]:
        q = self.db.query(OfficerLocation).filter(OfficerLocation.alert_id == alert_id)
        if officer_id is not None:
            q = q.filter(OfficerLocation.officer_id == officer_id)
        return q.order_by(OfficerLocation.recorded_at.asc()).all()

    def latest_per_officer(self) -> list[OfficerLocation]:
        latest = (
            self.db.query(
                OfficerLocation.officer_id.label("officer_id"),
                func.max(OfficerLocation.recorded_at).label("latest_at"),
            )
            .group_by(OfficerLocation.officer_id)
            .subquery()
        )
        rows = (
            self.db.query(OfficerLocation)
            .join(
                latest,
                (OfficerLocation.officer_id == latest.c.officer_id)
                & (OfficerLocation.recorded_at == latest.c.latest_at),
            )
            .order_by(OfficerLocation.recorded_at.desc())
            .all()
        )

        seen: set[uuid.UUID] = set()
        unique_rows = []
        for row in rows:
            if row.officer_id not in seen:
                seen.add(row.officer_id)
                unique_rows.append(row)
        return unique_rows

    def list_unlinked_older_than(self, cutoff: datetime) -> list[uuid.UUID]:
        rows = (
            self.db.query(OfficerLocation.location_id)
            .filter(
                OfficerLocation.alert_id.is_(None), OfficerLocation.recorded_at < cutoff
            )
            .all()
        )
        return [row[0] for row in rows]

    def list_linked_to_finished_alerts(self) -> list[tuple[OfficerLocation, Alert]]:
        return (
            self.db.query(OfficerLocation, Alert)
            .join(Alert, OfficerLocation.alert_id == Alert.alert_id)
            .filter(Alert.status.in_(FINISHED_ALERT_STATUSES))
            .all()
        )

    def create(self, location: OfficerLocation) -> OfficerLocation:
        self.db.add(location)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise
        self.db.refresh(location)
        return location

    def delete_by_ids(self, location_ids: list[uuid.UUID]) -> int:
        deleted = 0
        for start in range(0, len(location_ids), _DELETE_CHUNK):
            chunk = location_ids[start : start + _DELETE_CHUNK]
            deleted += (
                self.db.query(OfficerLocation)
                .filter(OfficerLocation.location_id.in_(chunk))
                .delete(synchronize_session=False)
            )
        self.db.commit()
        self.db.expire_all()
        return deleted
