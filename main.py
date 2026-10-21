from fastapi import FastAPI

from routers import zone
from database import init_db
from routers.violation_report import router as violation_report_router

app = FastAPI(title="Vesper", version="0.1.0")
app.include_router(zone.router, prefix="/vesper")

init_db()

app.include_router(violation_report_router, prefix="/vesper/violation-reports")


@app.get("/health")
def health_check():
    return {"status": "ok"}
