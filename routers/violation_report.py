import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.security import (
    require_any_user,
    require_coordinator,
    require_officer,
)
from database import get_db
from models.user import User
from models.violation_report import ReviewStatus, ViolationReport
from schemas.violation_report import (
    ViolationReportCreate,
    ViolationReportRead,
)
from services.violation_report import violation_report_service


router = APIRouter(tags=["violation reports"])


@router.post(
    "",
    response_model=ViolationReportRead,
    status_code=status.HTTP_201_CREATED,
)
def create_report(
    body: ViolationReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
):
    return violation_report_service.create_report(
        db,
        current_user,
        body,
    )


@router.get(
    "",
    response_model=List[ViolationReportRead],
)
def list_reports(
    review_status: ReviewStatus | None = None,
    inspection_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_user),
):
    return violation_report_service.list_reports(
        db,
        current_user,
        review_status,
        inspection_id,
        limit,
        offset,
    )


@router.get(
    "/{violation_id}",
    response_model=ViolationReportRead,
)
def get_report(
    violation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_user),
):
    return violation_report_service.get_report(
        db,
        current_user,
        violation_id,
    )


@router.post(
    "/{violation_id}/review",
    response_model=ViolationReportRead,
)
def review_report(
    violation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return violation_report_service.review_report(
        db,
        current_user,
        violation_id,
    )


@router.delete(
    "/{violation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_report(
    violation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    report = (
        db.query(ViolationReport)
        .filter(ViolationReport.violation_id == violation_id)
        .first()
    )

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Violation report with ID {violation_id} not found.",
        )

    db.delete(report)
    db.commit()
    return None
