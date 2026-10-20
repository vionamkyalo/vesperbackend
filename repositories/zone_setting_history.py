from sqlalchemy.orm import Session

from models.zone_setting_history import ZoneSettingHistory


class ZoneSettingHistoryRepository:
    def create(self, db: Session, history: ZoneSettingHistory):
        db.add(history)
        db.commit()
        db.refresh(history)
        return history

    def get(self, db: Session, history_id):
        return db.query(ZoneSettingHistory).filter(ZoneSettingHistory.history_id == history_id).first()

    def get_all(self, db: Session):
        return db.query(ZoneSettingHistory).all()


zone_setting_history_repository = ZoneSettingHistoryRepository()