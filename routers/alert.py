import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from core.security import (
    get_current_user,
    require_patrol_coordinator,
    require_patrol_officer,
)
from database import get_db
from models.user import User
from schemas.alert import (
    AlertCreate,
    AlertListQuery,
    AlertPage,
    AlertRead,
    AlertStatusUpdate,
    AlertVerificationUpdate,
    MyAlertsQuery,
)
from services.alert import AlertService

router = APIRouter(tags=["Alerts"])


@router.post("", response_model=AlertRead, status_code=status.HTTP_201_CREATED)
def create_alert(
    data: AlertCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_patrol_coordinator),
):
    return AlertService(db).create_alert(data, current_user)


@router.get("", response_model=AlertPage)
def list_alerts(
    query: Annotated[AlertListQuery, Query()],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_patrol_coordinator),
):
    return AlertService(db).list_alerts(query)


@router.get("/assigned/me", response_model=AlertPage)
def list_my_alerts(
    query: Annotated[MyAlertsQuery, Query()],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_patrol_officer),
):
    return AlertService(db).list_my_alerts(current_user, query)


@router.get("/{alert_id}", response_model=AlertRead)
def get_alert(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AlertService(db).get_alert(alert_id, current_user)


@router.patch("/{alert_id}/status", response_model=AlertRead)
def update_alert_status(
    alert_id: uuid.UUID,
    data: AlertStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_patrol_coordinator),
):
    return AlertService(db).update_alert_status(alert_id, data, current_user)


@router.patch("/{alert_id}/verification", response_model=AlertRead)
def record_verification(
    alert_id: uuid.UUID,
    data: AlertVerificationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_patrol_coordinator),
):
    return AlertService(db).record_verification(alert_id, data, current_user)
