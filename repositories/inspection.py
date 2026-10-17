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


inspection_repository = InspectionRepository()
