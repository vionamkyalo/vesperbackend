from sqlalchemy.orm import Session

from models.zone_light_reading import ZoneLightReading


class ZoneLightReadingRepository:
    def get(self, db: Session, reading_id):
        return db.get(ZoneLightReading, reading_id)

    def get_by_zone_and_date(self, db: Session, zone_id, observation_date):
        return (
            db.query(ZoneLightReading)
            .filter(
                ZoneLightReading.zone_id == zone_id,
                ZoneLightReading.observation_date == observation_date,
            )
            .first()
        )

    def create(self, db: Session, reading: ZoneLightReading):
        db.add(reading)
        db.commit()
        db.refresh(reading)
        return reading

    def save(self, db: Session, reading: ZoneLightReading):
        db.commit()
        db.refresh(reading)
        return reading

    def list_readings(
        self,
        db: Session,
        zone_id=None,
        observation_date=None,
        ingestion_status=None,
        limit=50,
        offset=0,
    ):
        query = db.query(ZoneLightReading)

        if zone_id is not None:
            query = query.filter(ZoneLightReading.zone_id == zone_id)
        if observation_date is not None:
            query = query.filter(ZoneLightReading.observation_date == observation_date)
        if ingestion_status is not None:
            query = query.filter(ZoneLightReading.ingestion_status == ingestion_status)

        return (
            query.order_by(
                ZoneLightReading.observation_date.desc(),
                ZoneLightReading.created_at.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )


zone_light_reading_repository = ZoneLightReadingRepository()
