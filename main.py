from fastapi import FastAPI

from core.config import get_settings
from core.security import apply_security
from database import init_db
from models.alert import Alert  # noqa: F401
from models.alert_assignment import AlertAssignment  # noqa: F401
from models.catch_check import CatchCheck  # noqa: F401
from models.inspection import Inspection  # noqa: F401
from models.officer_location import OfficerLocation  # noqa: F401
from models.user import User  # noqa: F401
from models.zone import Zone  # noqa: F401
from models.zone_baseline import ZoneBaseline  # noqa: F401
from models.zone_light_reading import ZoneLightReading  # noqa: F401
from models.zone_setting_history import ZoneSettingHistory  # noqa: F401
from routers.auth import router as auth_router
from routers.user import router as user_router
from routers.violation_report import router as violation_report_router
from routers.inspection import router as inspection_router

settings = get_settings()

app = FastAPI(title="Vesper", version="0.1.0")

init_db()

API_PREFIX = "/vesper"
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(user_router, prefix=API_PREFIX)
app.include_router(inspection_router, prefix=API_PREFIX)
app.include_router(violation_report_router, prefix=f"{API_PREFIX}/violation-reports")

apply_security(app, settings)


@app.get("/health")
def health_check():
    return {"status": "ok"}
