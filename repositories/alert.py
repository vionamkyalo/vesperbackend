import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.alert import Alert, AlertStatus
from models.zone import Zone
from models.zone_light_reading import ZoneLightReading
from schemas.alert import AlertListQuery


class AlertRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, alert_id: uuid.UUID) -> Alert | None:
        return self.db.get(Alert, alert_id)

    def get_by_reading_and_cluster(
        self, reading_id: uuid.UUID, cluster_label: int
    ) -> Alert | None:
        return (
            self.db.query(Alert)
            .filter(
                Alert.reading_id == reading_id, Alert.cluster_label == cluster_label
            )
            .first()
        )

    def get_zone(self, zone_id: uuid.UUID) -> Zone | None:
        return self.db.get(Zone, zone_id)

    def get_reading(self, reading_id: uuid.UUID) -> ZoneLightReading | None:
        return self.db.get(ZoneLightReading, reading_id)

    @staticmethod
    def _page(q, skip: int, limit: int) -> tuple[list[Alert], int]:
        total = q.count()
        items = (
            q.order_by(Alert.created_at.desc(), Alert.alert_id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return items, total

    def list_filtered(self, query: AlertListQuery) -> tuple[list[Alert], int]:
        q = self.db.query(Alert)
        if query.zone_id is not None:
            q = q.filter(Alert.zone_id == query.zone_id)
        if query.status is not None:
            q = q.filter(Alert.status == query.status)
        if query.verification_result is not None:
            q = q.filter(Alert.verification_result == query.verification_result)
        if query.officer_id is not None:
            q = q.filter(Alert.officer_id == query.officer_id)
        if query.min_confidence is not None:
            q = q.filter(Alert.confidence >= query.min_confidence)
        if query.created_from is not None:
            q = q.filter(Alert.created_at >= query.created_from)
        if query.created_to is not None:
            q = q.filter(Alert.created_at <= query.created_to)
        return self._page(q, query.skip, query.limit)

    def list_for_officer(
        self, officer_id: uuid.UUID, status: AlertStatus | None, skip: int, limit: int
    ) -> tuple[list[Alert], int]:
        q = self.db.query(Alert).filter(Alert.officer_id == officer_id)
        if status is not None:
            q = q.filter(Alert.status == status)
        return self._page(q, skip, limit)

    def create(self, alert: Alert) -> Alert:
        self.db.add(alert)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise
        self.db.refresh(alert)
        return alert

    def update(self, alert: Alert) -> Alert:
        self.db.commit()
        self.db.refresh(alert)
        return alert
