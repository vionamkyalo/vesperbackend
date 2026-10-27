from sqlalchemy.orm import Session

from models.zone_baseline import ZoneBaseline
from models.zone_light_reading import IngestionStatus, ZoneLightReading


class ZoneBaselineRepository:
    def create(self, db: Session, baseline: ZoneBaseline):
        db.add(baseline)
        db.commit()
        db.refresh(baseline)
        return baseline

    def get(self, db: Session, baseline_id):
        return (
            db.query(ZoneBaseline)
            .filter(ZoneBaseline.baseline_id == baseline_id)
            .first()
        )

    def get_by_zone_band(self, db: Session, zone_id, moon_band):
        return (
            db.query(ZoneBaseline)
            .filter(
                ZoneBaseline.zone_id == zone_id,
                ZoneBaseline.moon_band == moon_band,
            )
            .first()
        )

    def list_baselines(
        self, db: Session, zone_id=None, moon_band=None, limit=50, offset=0
    ):
        query = db.query(ZoneBaseline)

        if zone_id is not None:
            query = query.filter(ZoneBaseline.zone_id == zone_id)
        if moon_band is not None:
            query = query.filter(ZoneBaseline.moon_band == moon_band)

        return (
            query.order_by(ZoneBaseline.zone_id, ZoneBaseline.moon_band)
            .offset(offset)
            .limit(limit)
            .all()
        )

    def update(self, db: Session, baseline: ZoneBaseline):
        db.add(baseline)
        db.commit()
        db.refresh(baseline)
        return baseline

    def list_received_readings(self, db: Session, zone_id, since, until):
        return (
            db.query(ZoneLightReading)
            .filter(
                ZoneLightReading.zone_id == zone_id,
                ZoneLightReading.ingestion_status == IngestionStatus.RECEIVED,
                ZoneLightReading.light_index.is_not(None),
                ZoneLightReading.observation_date >= since,
                ZoneLightReading.observation_date <= until,
            )
            .order_by(ZoneLightReading.observation_date)
            .all()
        )


zone_baseline_repository = ZoneBaselineRepository()
