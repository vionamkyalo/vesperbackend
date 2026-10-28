import uuid
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.security import require_coordinator
from database import get_db
from models.user import User
from models.zone_light_reading import IngestionStatus
from schemas.zone_light_reading import ZoneLightReadingRead
from services.zone_light_reading import zone_light_reading_service


router = APIRouter(tags=["Zone light readings"])


@router.get(
    "",
    response_model=List[ZoneLightReadingRead],
)
def list_readings(
    zone_id: uuid.UUID | None = None,
    observation_date: date | None = None,
    ingestion_status: IngestionStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return zone_light_reading_service.list_readings(
        db, zone_id, observation_date, ingestion_status, limit, offset
    )


@router.get(
    "/{reading_id}",
    response_model=ZoneLightReadingRead,
)
def get_reading(
    reading_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return zone_light_reading_service.get_reading(db, reading_id)
