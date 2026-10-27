import shutil
import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from core.security import require_coordinator
from database import get_db
from models.user import User
from schemas.detection import DetectionResult, DetectionRun, IngestionResult, NasaRun
from services.detection import detection_service
from services.ingestion import ingestion_service

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


@router.post(
    "/nasa", response_model=IngestionResult, status_code=status.HTTP_201_CREATED
)
def run_from_nasa(
    body: NasaRun,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    return ingestion_service.run_for_night(db, current_user, body.observation_date)


@router.post(
    "/nasa/upload", response_model=IngestionResult, status_code=status.HTTP_201_CREATED
)
def run_from_upload(
    observation_date: date = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_coordinator),
):
    folder = Path(tempfile.mkdtemp())
    path = folder / "night.h5"
    try:
        with open(path, "wb") as out:
            shutil.copyfileobj(file.file, out)
        return ingestion_service.run_for_night(db, current_user, observation_date, path)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
