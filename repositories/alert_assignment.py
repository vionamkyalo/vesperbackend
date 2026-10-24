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

    def get_active_for_alert(self, db: Session, alert_id):
        return (
            db.query(AlertAssignment)
            .filter(
                AlertAssignment.alert_id == alert_id,
                AlertAssignment.ended_at.is_(None),
            )
            .first()
        )

    def search(
        self,
        db: Session,
        *,
        alert_id=None,
        officer_id=None,
        assignment_status=None,
        active_only=False,
        limit=50,
        offset=0,
    ):
        query = db.query(AlertAssignment)
        if alert_id is not None:
            query = query.filter(AlertAssignment.alert_id == alert_id)
        if officer_id is not None:
            query = query.filter(AlertAssignment.officer_id == officer_id)
        if assignment_status is not None:
            query = query.filter(AlertAssignment.status == assignment_status)
        if active_only:
            query = query.filter(AlertAssignment.ended_at.is_(None))
        return (
            query.order_by(AlertAssignment.assigned_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )


alert_assignment_repository = AlertAssignmentRepository()
