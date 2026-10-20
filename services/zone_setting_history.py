import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.user import User, UserRole
from models.zone import Zone
from models.zone_setting_history import ZoneSettingHistory
from repositories.zone_setting_history import zone_setting_history_repository

logger = logging.getLogger(__name__)


class ZoneSettingHistoryService:
    def check_coordinator(self, current_user: User):
        if current_user is None or not current_user.is_active:
            logger.warning("setting history access refused: inactive or unknown user")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account is not active.")

        if current_user.role != UserRole.PATROL_COORDINATOR:
            logger.warning(f"setting history refused: user {current_user.user_id} is not the coordinator")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the patrol coordinator can view setting history.",
            )

    def list_history(self, db: Session, current_user: User, zone_id=None, changed_by=None, limit=50, offset=0):
        self.check_coordinator(current_user)

        if zone_id is not None and db.query(Zone).filter(Zone.zone_id == zone_id).first() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone was not found.")

        query = db.query(ZoneSettingHistory)

        if zone_id is not None:
            query = query.filter(ZoneSettingHistory.zone_id == zone_id)
        if changed_by is not None:
            query = query.filter(ZoneSettingHistory.changed_by == changed_by)

        return query.order_by(ZoneSettingHistory.changed_at.desc()).limit(limit).offset(offset).all()

    def get_history(self, db: Session, current_user: User, history_id: uuid.UUID):
        self.check_coordinator(current_user)
        history = zone_setting_history_repository.get(db, history_id)

        if history is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setting history entry was not found.")

        return history


zone_setting_history_service = ZoneSettingHistoryService()