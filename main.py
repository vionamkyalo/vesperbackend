from fastapi import FastAPI


from core.config import get_settings

from core.security import apply_security, register_error_handlers

from database import init_db
from routers.auth import router as auth_router
from routers.user import router as user_router
from routers.zone import router as zone_router
from routers.zone_setting_history import router as zone_setting_history_router
from routers.catch_check import router as catch_check_router
from routers.inspection import router as inspection_router
from routers.violation_report import router as violation_report_router
from routers.alert import router as alert_router
from routers.zone_baseline import router as zone_baseline_router
from routers.detection import router as detection_router
from routers.alert_assignment import router as alert_assignment_router
from routers.zone_light_reading import router as zone_light_reading_router

settings = get_settings()

app = FastAPI(title="Vesper", version="0.1.0")
apply_security(app, settings)
register_error_handlers(app)


init_db()

app.include_router(user_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(zone_router, prefix="/api")
app.include_router(alert_router, prefix="/api/alerts")
app.include_router(inspection_router, prefix="/api")
app.include_router(zone_baseline_router, prefix="/api")
app.include_router(detection_router, prefix="/api")
app.include_router(catch_check_router, prefix="/api")
app.include_router(violation_report_router, prefix="/api/violation-reports")
app.include_router(zone_setting_history_router, prefix="/api")
app.include_router(alert_assignment_router, prefix="/api")
app.include_router(zone_light_reading_router, prefix="/api/zone-light-readings")


@app.get("/health")
def health_check():
    return {"status": "ok"}
