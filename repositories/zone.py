from sqlalchemy.orm import Session

from models.zone import Zone


class ZoneRepository:
    def create(self, db: Session, zone: Zone):
        db.add(zone)
        db.flush()
        db.refresh(zone)
        return zone

    def get(self, db: Session, zone_id):
        return db.query(Zone).filter(Zone.zone_id == zone_id).first()

    def get_all(self, db: Session):
        return db.query(Zone).all()

    def update(self, db: Session, zone: Zone):
        db.add(zone)
        db.commit()
        db.refresh(zone)
        return zone


zone_repository = ZoneRepository()
