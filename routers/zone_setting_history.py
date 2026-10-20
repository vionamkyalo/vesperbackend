import uuid
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.security import require_coordinator
from database import get_db
from models.user import User
from schemas.zone_setting_history import ZoneSettingHistoryRead
from services.zone_setting_history import zone_setting_history_service

router = APIRouter(prefix="/zone-setting-history", tags=["zone setting history"])


@router.get("", response_model=List[ZoneSettingHistoryRead])
def list_history(
    zone_id: uuid.UUID | None = None,
    changed_by: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return zone_setting_history_service.list_history(
        db, current_user, zone_id, changed_by, limit, offset
    )


@router.get("/{history_id}", response_model=ZoneSettingHistoryRead)
def get_history(
    history_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return zone_setting_history_service.get_history(db, current_user, history_id)
