import uuid
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.security import require_coordinator
from database import get_db
from models.user import User
from models.zone_baseline import MoonBand
from schemas.zone_baseline import (
    ZoneBaselineFilter,
    ZoneBaselineRead,
    ZoneBaselineRecalculate,
    ZoneBaselineRecalculateResult,
)
from services.zone_baseline import zone_baseline_service

router = APIRouter(prefix="/zone-baselines", tags=["zone baselines"])


@router.get("", response_model=List[ZoneBaselineRead])
def list_baselines(
    zone_id: uuid.UUID | None = None,
    moon_band: MoonBand | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    filters = ZoneBaselineFilter(
        zone_id=zone_id, moon_band=moon_band, limit=limit, offset=offset
    )
    return zone_baseline_service.list_baselines(db, current_user, filters)


@router.post("/recalculate", response_model=ZoneBaselineRecalculateResult)
def recalculate_baselines(
    body: ZoneBaselineRecalculate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return zone_baseline_service.recalculate(db, current_user, body)


@router.get("/{baseline_id}", response_model=ZoneBaselineRead)
def get_baseline(
    baseline_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return zone_baseline_service.get_baseline(db, current_user, baseline_id)
