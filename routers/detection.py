from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from core.security import require_coordinator
from database import get_db
from models.user import User
from schemas.detection import DetectionResult, DetectionRun
from services.detection import detection_service

router = APIRouter(prefix="/detections", tags=["detections"])


@router.post(
    "/run", response_model=DetectionResult, status_code=status.HTTP_201_CREATED
)
def run_detection(
    body: DetectionRun,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return detection_service.run(db, current_user, body)
