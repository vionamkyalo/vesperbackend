from sqlalchemy.orm import Session

from models.alert import Alert


class AlertRepository:
    def get(self, db: Session, alert_id):
        return db.query(Alert).filter(Alert.alert_id == alert_id).first()


alert_repository = AlertRepository()
