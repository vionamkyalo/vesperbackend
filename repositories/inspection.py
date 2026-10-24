from sqlalchemy.orm import Session

from models.inspection import Inspection


class InspectionRepository:
    def create(self, db: Session, inspection: Inspection):
        db.add(inspection)
        db.commit()
        db.refresh(inspection)
        return inspection

    def get(self, db: Session, inspection_id):
        return (
            db.query(Inspection)
            .filter(Inspection.inspection_id == inspection_id)
            .first()
        )

    def get_all(self, db: Session):
        return db.query(Inspection).all()

    def update(self, db: Session, inspection: Inspection):
        db.add(inspection)
        db.commit()
        db.refresh(inspection)
        return inspection

    def search(
        self,
        db: Session,
        *,
        officer_id=None,
        alert_id=None,
        zone_id=None,
        limit=50,
        offset=0,
    ):
        query = db.query(Inspection)
        if officer_id is not None:
            query = query.filter(Inspection.officer_id == officer_id)
        if alert_id is not None:
            query = query.filter(Inspection.alert_id == alert_id)
        if zone_id is not None:
            query = query.filter(Inspection.zone_id == zone_id)
        return (
            query.order_by(Inspection.inspected_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )


inspection_repository = InspectionRepository()
