import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from database import utcnow
from models.alert import Alert, AlertStatus
from models.alert_assignment import AlertAssignment, AssignmentStatus
from models.user import User, UserRole
from repositories.alert_assignment import alert_assignment_repository
from repositories.user import user_repository
from schemas.alert_assignment import AlertAssignmentCreate

logger = logging.getLogger(__name__)

ASSIGNABLE_ALERT_STATUSES = [AlertStatus.NEW, AlertStatus.IN_PROGRESS]


class AlertAssignmentService:
    def check_active(self, current_user: User):
        if current_user is None or not current_user.is_active:
            logger.warning("assignment access refused: inactive or unknown user")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not active.",
            )

    def is_coordinator(self, current_user: User):
        return current_user.role == UserRole.PATROL_COORDINATOR

    def check_coordinator(self, current_user: User):
        self.check_active(current_user)

        if not self.is_coordinator(current_user):
            logger.warning(
                "assignment action refused: user %s is not the coordinator",
                current_user.user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the patrol coordinator can do this.",
            )

    def check_officer(self, current_user: User):
        self.check_active(current_user)

        if current_user.role != UserRole.PATROL_OFFICER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only patrol officers can do this.",
            )

    def get_active_assignment(self, db: Session, alert_id):
        return alert_assignment_repository.get_active_for_alert(db, alert_id)

    def check_open(self, assignment):
        if assignment.ended_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This assignment has already ended.",
            )

    def assign_alert(
        self, db: Session, current_user: User, data: AlertAssignmentCreate
    ):
        self.check_coordinator(current_user)

        alert = db.query(Alert).filter(Alert.alert_id == data.alert_id).first()
        if alert is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Alert was not found."
            )

        if alert.status not in ASSIGNABLE_ALERT_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A {alert.status.value} alert cannot be assigned.",
            )

        officer = user_repository.get(db, data.officer_id)
        if officer is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Officer was not found."
            )

        if officer.role != UserRole.PATROL_OFFICER or not officer.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Alerts can only be assigned to active patrol officers.",
            )

        now = utcnow()
        current = self.get_active_assignment(db, alert.alert_id)

        if current is not None:
            if current.officer_id == officer.user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This alert is already assigned to this officer.",
                )
            current.status = AssignmentStatus.REASSIGNED
            current.ended_at = now

        assignment = AlertAssignment(
            alert_id=alert.alert_id,
            officer_id=officer.user_id,
            assigned_by=current_user.user_id,
            status=AssignmentStatus.ASSIGNED,
            assigned_at=now,
        )

        alert.officer_id = officer.user_id
        alert.assigned_by = current_user.user_id
        alert.assignment_status = AssignmentStatus.ASSIGNED
        alert.assigned_at = now
        alert.reported_at = None
        if alert.status == AlertStatus.NEW:
            alert.status = AlertStatus.IN_PROGRESS

        assignment = alert_assignment_repository.create(db, assignment)

        logger.info(
            "alert %s assigned to %s by %s",
            alert.alert_id,
            officer.user_id,
            current_user.user_id,
        )
        return assignment

    def get_assignment(self, db: Session, current_user: User, assignment_id: uuid.UUID):
        self.check_active(current_user)
        assignment = alert_assignment_repository.get(db, assignment_id)

        if assignment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment was not found.",
            )

        if (
            not self.is_coordinator(current_user)
            and assignment.officer_id != current_user.user_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment was not found.",
            )

        return assignment

    def list_assignments(
        self,
        db: Session,
        current_user: User,
        alert_id=None,
        officer_id=None,
        assignment_status=None,
        active_only=False,
        limit=50,
        offset=0,
    ):
        self.check_active(current_user)

        if not self.is_coordinator(current_user):
            officer_id = current_user.user_id

        return alert_assignment_repository.search(
            db,
            alert_id=alert_id,
            officer_id=officer_id,
            assignment_status=assignment_status,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )

    def acknowledge(self, db: Session, current_user: User, assignment_id: uuid.UUID):
        self.check_officer(current_user)
        assignment = self.get_assignment(db, current_user, assignment_id)
        self.check_open(assignment)

        if assignment.status != AssignmentStatus.ASSIGNED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A {assignment.status.value} assignment cannot be acknowledged.",
            )

        now = utcnow()
        assignment.status = AssignmentStatus.ACKNOWLEDGED
        assignment.acknowledged_at = now
        assignment.alert.assignment_status = AssignmentStatus.ACKNOWLEDGED

        assignment = alert_assignment_repository.update(db, assignment)

        logger.info(
            "assignment %s acknowledged by %s",
            assignment.assignment_id,
            current_user.user_id,
        )
        return assignment

    def mark_failed(self, db: Session, current_user: User, assignment_id: uuid.UUID):
        self.check_coordinator(current_user)
        assignment = self.get_assignment(db, current_user, assignment_id)
        self.check_open(assignment)

        if assignment.status == AssignmentStatus.REPORTED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The officer has already reported on this assignment.",
            )

        assignment.status = AssignmentStatus.FAILED
        assignment.ended_at = utcnow()

        alert = assignment.alert
        alert.officer_id = None
        alert.assignment_status = AssignmentStatus.FAILED

        assignment = alert_assignment_repository.update(db, assignment)

        logger.info(
            "assignment %s marked failed by %s",
            assignment.assignment_id,
            current_user.user_id,
        )
        return assignment

    def acknowledge_by_alert_id(self, db: Session, current_user: User, alert_id: uuid.UUID):
        self.check_officer(current_user)
        
        assignment = self.get_active_assignment(db, alert_id)
        if assignment is None or assignment.officer_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Active assignment for this alert was not found."
            )
            
        self.check_open(assignment)
        if assignment.status != AssignmentStatus.ASSIGNED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A {assignment.status.value} assignment cannot be acknowledged."
            )

        now = utcnow()
        assignment.status = AssignmentStatus.ACKNOWLEDGED
        assignment.acknowledged_at = now
        if assignment.alert:
            assignment.alert.assignment_status = AssignmentStatus.ACKNOWLEDGED

        assignment = alert_assignment_repository.update(db, assignment)

        logger.info(
            "assignment %s acknowledged via alert_id %s by %s",
            assignment.assignment_id,
            alert_id,
            current_user.user_id,
        )
        return assignment


alert_assignment_service = AlertAssignmentService()
