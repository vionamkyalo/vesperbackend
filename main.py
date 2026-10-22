from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import Settings
from core.security import register_error_handlers

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
from routers.alert import router as alert_router

settings = Settings()

app = FastAPI(title="Vesper", version="0.1.0")

register_error_handlers(app)

init_db()

app.include_router(user_router)
app.include_router(auth_router, prefix="/api")
app.include_router(alert_router, prefix="/vesper/alerts")
app.include_router(violation_report_router, prefix="/violation-reports")


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():

    return {"status": "ok"}
