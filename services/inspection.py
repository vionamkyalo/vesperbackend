import logging
import uuid
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from database import utcnow
from models.alert import Alert
from models.alert_assignment import AlertAssignment, AssignmentStatus
from models.inspection import Inspection
from models.user import User, UserRole
from repositories.inspection import inspection_repository
from repositories.zone import zone_repository
from schemas.inspection import InspectionCreate

logger = logging.getLogger(__name__)

MAX_CLOCK_SKEW = timedelta(minutes=10)


class InspectionService:
    def check_active(self, current_user: User):
        if current_user is None or not current_user.is_active:
            logger.warning("inspection access refused: inactive or unknown user")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not active.",
            )

    def is_coordinator(self, current_user: User):
        return current_user.role == UserRole.PATROL_COORDINATOR

    def officer_was_assigned(self, db: Session, alert_id, officer_id):
        assignment = (
            db.query(AlertAssignment)
            .filter(
                AlertAssignment.alert_id == alert_id,
                AlertAssignment.officer_id == officer_id,
            )
            .first()
        )
        return assignment is not None

    def check_alert(self, db: Session, current_user: User, data: InspectionCreate):
        alert = db.query(Alert).filter(Alert.alert_id == data.alert_id).first()

        assigned = False
        if alert is not None:
            if alert.officer_id == current_user.user_id:
                assigned = True
            elif self.officer_was_assigned(db, alert.alert_id, current_user.user_id):
                assigned = True

        if not assigned:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert was not found or is not assigned to you.",
            )

        if alert.zone_id != data.zone_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Inspection zone does not match the alert zone.",
            )

        return alert

    def mark_alert_reported(self, db: Session, current_user: User, alert):

        now = utcnow()
        alert.assignment_status = AssignmentStatus.REPORTED
        alert.reported_at = now

        assignment = (
            db.query(AlertAssignment)
            .filter(
                AlertAssignment.alert_id == alert.alert_id,
                AlertAssignment.officer_id == current_user.user_id,
                AlertAssignment.ended_at.is_(None),
            )
            .first()
        )
        if assignment is not None:
            assignment.status = AssignmentStatus.REPORTED
            assignment.reported_at = now

    def create_inspection(
        self, db: Session, current_user: User, data: InspectionCreate
    ):
        self.check_active(current_user)

        if self.is_coordinator(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only patrol officers record inspections.",
            )

        if data.inspected_at > utcnow() + MAX_CLOCK_SKEW:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="inspected_at cannot be in the future.",
            )

        if zone_repository.get(db, data.zone_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Zone was not found."
            )

        alert = None
        if data.alert_id is not None:
            alert = self.check_alert(db, current_user, data)

        inspection = Inspection(
            alert_id=data.alert_id,
            officer_id=current_user.user_id,
            zone_id=data.zone_id,
            inspection_type=data.inspection_type,
            outcome=data.outcome,
            rigs_observed=data.rigs_observed,
            latitude=data.latitude,
            longitude=data.longitude,
            notes=data.notes,
            inspected_at=data.inspected_at,
        )

        if alert is not None:
            self.mark_alert_reported(db, current_user, alert)

        inspection = inspection_repository.create(db, inspection)

        logger.info(
            "inspection %s recorded by %s",
            inspection.inspection_id,
            current_user.user_id,
        )
        return inspection

    def get_inspection(self, db: Session, current_user: User, inspection_id: uuid.UUID):
        self.check_active(current_user)
        inspection = inspection_repository.get(db, inspection_id)

        if inspection is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inspection was not found.",
            )

        if (
            not self.is_coordinator(current_user)
            and inspection.officer_id != current_user.user_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inspection was not found.",
            )

        return inspection

    def list_inspections(
        self,
        db: Session,
        current_user: User,
        alert_id=None,
        zone_id=None,
        officer_id=None,
        limit=50,
        offset=0,
    ):
        self.check_active(current_user)

        if not self.is_coordinator(current_user):
            officer_id = current_user.user_id

        return inspection_repository.search(
            db,
            officer_id=officer_id,
            alert_id=alert_id,
            zone_id=zone_id,
            limit=limit,
            offset=offset,
        )


inspection_service = InspectionService()
