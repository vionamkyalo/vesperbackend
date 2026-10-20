from sqlalchemy.orm import Session
from models.inspection import Inspection
from models.user import User
from models.violation_report import ViolationReport


class ViolationReportRepository:
    def create(self, db: Session, report: ViolationReport):
        db.add(report)
        db.commit()
        db.refresh(report)
        return report

    def get(self, db: Session, violation_id):
        return (
            db.query(ViolationReport)
            .filter(ViolationReport.violation_id == violation_id)
            .first()
        )

    def get_inspection(self, db: Session, inspection_id):
        return (
            db.query(Inspection)
            .filter(Inspection.inspection_id == inspection_id)
            .first()
        )

    def get_user_by_id(self, db: Session, user_id):
        return db.query(User).filter(User.user_id == user_id).first()

    def list_reports(
        self,
        db: Session,
        review_status=None,
        officer_id=None,
        inspection_id=None,
        limit=50,
        offset=0,
    ):
        query = db.query(ViolationReport)

        if review_status is not None:
            query = query.filter(ViolationReport.review_status == review_status)
        if officer_id is not None:
            query = query.join(Inspection).filter(Inspection.officer_id == officer_id)
        if inspection_id is not None:
            query = query.filter(ViolationReport.inspection_id == inspection_id)

        return (
            query.order_by(ViolationReport.recorded_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )


violation_report_repository = ViolationReportRepository()
