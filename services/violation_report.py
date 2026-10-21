import logging
import uuid
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from database import utcnow
from models.user import User, UserRole
from models.violation_report import ReviewStatus, ViolationReport
from repositories.violation_report import violation_report_repository
from schemas.violation_report import ViolationReportCreate


logger = logging.getLogger(__name__)

MAX_CLOCK_SKEW = timedelta(minutes=10)


class ViolationReportService:
    def check_active(self, current_user: User):
        if current_user is None or not current_user.is_active:
            logger.warning("violation report access refused: inactive or unknown user")
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
                "violation report action refused: user %s is not the coordinator",
                current_user.user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the patrol coordinator can do this.",
            )

    def create_report(
        self,
        db: Session,
        current_user: User,
        data: ViolationReportCreate,
    ):
        self.check_active(current_user)

        if self.is_coordinator(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only patrol officers record violation reports.",
            )

        if data.recorded_at > utcnow() + MAX_CLOCK_SKEW:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="recorded_at cannot be in the future.",
            )

        inspection = violation_report_repository.get_inspection(
            db,
            data.inspection_id,
        )

        if inspection is None:
            logger.warning(
                "create_report refused: inspection %s does not exist",
                data.inspection_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inspection was not found.",
            )

        if inspection.officer_id != current_user.user_id:
            logger.warning(
                "create_report refused: inspection %s belongs to officer %s, "
                "but the request was made by user %s",
                data.inspection_id,
                inspection.officer_id,
                current_user.user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inspection was not found.",
            )

        report = ViolationReport(
            violation_id=uuid.uuid4(),
            inspection_id=data.inspection_id,
            violation_type=data.violation_type,
            rig_identifier=data.rig_identifier,
            description=data.description,
            recorded_at=data.recorded_at,
        )

        report = violation_report_repository.create(db, report)

        logger.info(
            "violation report %s recorded by %s",
            report.violation_id,
            current_user.user_id,
        )

        return report

    def get_report(
        self,
        db: Session,
        current_user: User,
        violation_id: uuid.UUID,
    ):
        self.check_active(current_user)

        report = violation_report_repository.get(db, violation_id)

        if report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Violation report was not found.",
            )

        if (
            not self.is_coordinator(current_user)
            and report.inspection.officer_id != current_user.user_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Violation report was not found.",
            )

        return report

    def list_reports(
        self,
        db: Session,
        current_user: User,
        review_status=None,
        inspection_id=None,
        limit=50,
        offset=0,
    ):
        self.check_active(current_user)

        officer_id = None

        if not self.is_coordinator(current_user):
            officer_id = current_user.user_id

        return violation_report_repository.list_reports(
            db,
            review_status,
            officer_id,
            inspection_id,
            limit,
            offset,
        )

    def review_report(
        self,
        db: Session,
        current_user: User,
        violation_id: uuid.UUID,
    ):
        self.check_coordinator(current_user)

        report = self.get_report(db, current_user, violation_id)

        if report.review_status != ReviewStatus.SUBMITTED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This report has already been reviewed.",
            )

        report.review_status = ReviewStatus.REVIEWED
        report.reviewed_by = current_user.user_id
        report.reviewed_at = utcnow()

        db.commit()
        db.refresh(report)

        logger.info(
            "violation report %s reviewed by %s",
            report.violation_id,
            current_user.user_id,
        )

        return report

    def delete_report(
        self,
        db: Session,
        current_user: User,
        violation_id: uuid.UUID,
    ):
        self.check_coordinator(current_user)

        report = self.get_report(
            db,
            current_user,
            violation_id,
        )

        violation_report_repository.delete(db, report)

        logger.info(
            "violation report %s deleted by %s",
            violation_id,
            current_user.user_id,
        )


violation_report_service = ViolationReportService()
