import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import utcnow
from models.zone_light_reading import IngestionStatus, ZoneLightReading
from repositories.zone import zone_repository
from repositories.zone_light_reading import zone_light_reading_repository
from schemas.zone_light_reading import ZoneLightReadingCreate, ZoneLightReadingResults

logger = logging.getLogger(__name__)


class ZoneLightReadingService:
    def get_reading(self, db: Session, reading_id: uuid.UUID):
        reading = zone_light_reading_repository.get(db, reading_id)

        if reading is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Zone light reading was not found.",
            )

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
        return zone_light_reading_repository.list_readings(
            db, zone_id, observation_date, ingestion_status, limit, offset
        )

    def create_reading(self, db: Session, data: ZoneLightReadingCreate):
        if data.observation_date > utcnow().date():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="observation_date cannot be in the future.",
            )

        if zone_repository.get(db, data.zone_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Zone was not found.",
            )

        existing = zone_light_reading_repository.get_by_zone_and_date(
            db, data.zone_id, data.observation_date
        )
        if existing is not None:
            return existing, False

        reading = ZoneLightReading(
            zone_id=data.zone_id,
            observation_date=data.observation_date,
            ingestion_status=IngestionStatus.PENDING,
        )

        try:
            reading = zone_light_reading_repository.create(db, reading)
        except IntegrityError:
            db.rollback()
            existing = zone_light_reading_repository.get_by_zone_and_date(
                db, data.zone_id, data.observation_date
            )
            return existing, False

        logger.info(
            "zone light reading %s created for zone %s on %s",
            reading.reading_id,
            reading.zone_id,
            reading.observation_date,
        )
        return reading, True

    def record_results(
        self, db: Session, reading_id: uuid.UUID, data: ZoneLightReadingResults
    ):
        reading = self.get_reading(db, reading_id)

        if reading.ingestion_status == IngestionStatus.RECEIVED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Results have already been recorded for this reading.",
            )

        reading.light_index = data.light_index
        reading.valid_pixel_count = data.valid_pixel_count
        reading.hotspot_pixel_count = data.hotspot_pixel_count
        reading.cluster_count = data.cluster_count
        reading.ingestion_status = IngestionStatus.RECEIVED

        reading = zone_light_reading_repository.save(db, reading)
        logger.info("results recorded for zone light reading %s", reading_id)
        return reading

    def record_ingestion_error(self, db: Session, reading_id: uuid.UUID):
        reading = self.get_reading(db, reading_id)

        if reading.ingestion_status == IngestionStatus.RECEIVED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This reading already has results and cannot be marked "
                    "as an ingestion error."
                ),
            )

        reading.ingestion_status = IngestionStatus.INGESTION_ERROR
        reading.light_index = None
        reading.valid_pixel_count = None
        reading.hotspot_pixel_count = None
        reading.cluster_count = None

        reading = zone_light_reading_repository.save(db, reading)
        logger.warning("ingestion error recorded for zone light reading %s", reading_id)
        return reading


zone_light_reading_service = ZoneLightReadingService()
