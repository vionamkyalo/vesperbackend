from fastapi import FastAPI

from database import init_db
from models import (  # noqa: F401
    violation_report,
)
from routers.violation_report import router as violation_report_router

app = FastAPI(title="Vesper", version="0.1.0")

init_db()

app.include_router(
    violation_report_router,
    prefix="/violation-reports",
)


@app.get("/health")
def health_check():
    return {"status": "ok"}
