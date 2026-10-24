from sqlalchemy.orm import Session

from models.alert_assignment import AlertAssignment


class AlertAssignmentRepository:
    def create(self, db: Session, assignment: AlertAssignment):
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
        return assignment

    def get(self, db: Session, assignment_id):
        return (
            db.query(AlertAssignment)
            .filter(AlertAssignment.assignment_id == assignment_id)
            .first()
        )

    def get_all(self, db: Session):
        return db.query(AlertAssignment).all()

    def update(self, db: Session, assignment: AlertAssignment):
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
        return assignment

    def exists_for_officer(self, db: Session, alert_id, officer_id) -> bool:
        return (
            db.query(AlertAssignment)
            .filter(
                AlertAssignment.alert_id == alert_id,
                AlertAssignment.officer_id == officer_id,
            )
            .first()
            is not None
        )

    def get_active_for_officer(self, db: Session, alert_id, officer_id):
        return (
            db.query(AlertAssignment)
            .filter(
                AlertAssignment.alert_id == alert_id,
                AlertAssignment.officer_id == officer_id,
                AlertAssignment.ended_at.is_(None),
            )
            .first()
        )


alert_assignment_repository = AlertAssignmentRepository()
