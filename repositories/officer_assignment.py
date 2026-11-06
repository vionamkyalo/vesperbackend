import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.alert import Alert, AlertStatus
from models.alert_assignment import AlertAssignment
from models.officer_assignment import OfficerAssignment
from schemas.officer_assignment import AssignmentListQuery

FINISHED_ALERT_STATUSES = (AlertStatus.CLOSED, AlertStatus.DISMISSED)
_DELETE_CHUNK = 500


class OfficerAssignmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, location_id: uuid.UUID) -> OfficerAssignment | None:
        return self.db.get(OfficerAssignment, location_id)

    def get_alert(self, alert_id: uuid.UUID) -> Alert | None:
        return self.db.get(Alert, alert_id)

    def get_previous_for_officer(
        self,
        officer_id: uuid.UUID,
        at_or_before: datetime,
        exclude_location_id: uuid.UUID | None = None,
    ) -> OfficerAssignment | None:
        q = self.db.query(OfficerAssignment).filter(
            OfficerAssignment.officer_id == officer_id,
            OfficerAssignment.recorded_at <= at_or_before,
        )
        if exclude_location_id is not None:
            q = q.filter(OfficerAssignment.location_id != exclude_location_id)
        return q.order_by(
            OfficerAssignment.recorded_at.desc(), OfficerAssignment.synced_at.desc()
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
        self, query: AssignmentListQuery
    ) -> tuple[list[OfficerAssignment], int]:
        q = self.db.query(OfficerAssignment)
        if query.officer_id is not None:
            q = q.filter(OfficerAssignment.officer_id == query.officer_id)
        if query.alert_id is not None:
            q = q.filter(OfficerAssignment.alert_id == query.alert_id)
        if query.recorded_from is not None:
            q = q.filter(OfficerAssignment.recorded_at >= query.recorded_from)
        if query.recorded_to is not None:
            q = q.filter(OfficerAssignment.recorded_at <= query.recorded_to)
        total = q.count()
        items = (
            q.order_by(
                OfficerAssignment.recorded_at.desc(),
                OfficerAssignment.location_id.desc(),
            )
            .offset(query.skip)
            .limit(query.limit)
            .all()
        )
        return items, total

    def list_for_alert(
        self, alert_id: uuid.UUID, officer_id: uuid.UUID | None = None
    ) -> list[OfficerAssignment]:
        q = self.db.query(OfficerAssignment).filter(
            OfficerAssignment.alert_id == alert_id
        )
        if officer_id is not None:
            q = q.filter(OfficerAssignment.officer_id == officer_id)
        return q.order_by(OfficerAssignment.recorded_at.asc()).all()

    def latest_per_officer(self) -> list[OfficerAssignment]:
        latest = (
            self.db.query(
                OfficerAssignment.officer_id.label("officer_id"),
                func.max(OfficerAssignment.recorded_at).label("latest_at"),
            )
            .group_by(OfficerAssignment.officer_id)
            .subquery()
        )
        rows = (
            self.db.query(OfficerAssignment)
            .join(
                latest,
                (OfficerAssignment.officer_id == latest.c.officer_id)
                & (OfficerAssignment.recorded_at == latest.c.latest_at),
            )
            .order_by(OfficerAssignment.recorded_at.desc())
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
            self.db.query(OfficerAssignment.location_id)
            .filter(
                OfficerAssignment.alert_id.is_(None),
                OfficerAssignment.recorded_at < cutoff,
            )
            .all()
        )
        return [row[0] for row in rows]

    def list_linked_to_finished_alerts(self) -> list[tuple[OfficerAssignment, Alert]]:
        return (
            self.db.query(OfficerAssignment, Alert)
            .join(Alert, OfficerAssignment.alert_id == Alert.alert_id)
            .filter(Alert.status.in_(FINISHED_ALERT_STATUSES))
            .all()
        )

    def create(self, location: OfficerAssignment) -> OfficerAssignment:
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
                self.db.query(OfficerAssignment)
                .filter(OfficerAssignment.location_id.in_(chunk))
                .delete(synchronize_session=False)
            )
        self.db.commit()
        self.db.expire_all()
        return deleted
