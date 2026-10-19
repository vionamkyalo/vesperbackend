import os

from fastapi import FastAPI

from database import init_db


from routers.alert import router as alert_router
from routers.inspection import router as inspection_router
from routers.users import router as users_router
from routers.violation_report import router as violation_report_router

app = FastAPI(title="Vesper", version="0.1.0")

init_db()

app.include_router(
    violation_report_router,
    prefix="/violation-reports",
)

app.include_router(
    inspection_router,
    prefix="/inspections",
)

app.include_router(
    alert_router,
    prefix="/alerts",
)

if (
    os.getenv("FASTAPI_ENV") in ("dev", "development")
    or os.getenv("VESPER_DEV_TOOLS") == "1"
):
    app.include_router(
        users_router,
        prefix="/dev",
    )


@app.get("/health")
def health_check():
    return {"status": "ok"}
