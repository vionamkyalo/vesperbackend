import uuid
from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from core.security import require_any_user, require_coordinator
from database import get_db
from models.user import User
from schemas.zone import (
    ZoneCreate,
    ZoneRead,
    ZoneSettings,
    ZoneUpdate,
)
from services.zone import zone_service

router = APIRouter(prefix="/zones", tags=["zones"])


@router.post("", response_model=ZoneRead, status_code=status.HTTP_201_CREATED)
def create_zone(
    body: ZoneCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return zone_service.create_zone(db, current_user, body)


@router.get("", response_model=List[ZoneRead])
def list_zones(
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_user),
):
    return zone_service.list_zones(db, current_user, active_only)


@router.get("/{zone_id}", response_model=ZoneRead)
def get_zone(
    zone_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_user),
):
    return zone_service.get_zone(db, current_user, zone_id)


@router.patch("/{zone_id}", response_model=ZoneRead)
def update_zone(
    zone_id: uuid.UUID,
    body: ZoneUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return zone_service.update_zone(db, current_user, zone_id, body)


@router.put("/{zone_id}/settings", response_model=ZoneRead)
def update_settings(
    zone_id: uuid.UUID,
    body: ZoneSettings,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return zone_service.update_settings(db, current_user, zone_id, body)


@router.post("/{zone_id}/confirm-rules", response_model=ZoneRead)
def confirm_rules(
    zone_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return zone_service.confirm_rules(db, current_user, zone_id)
