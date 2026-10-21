from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import Settings
from database import init_db
from models import violation_report  # noqa: F401
from routers.auth import router as auth_router
from routers.user import router as user_router
from routers.violation_report import router as violation_report_router

settings = Settings()

app = FastAPI(title="Vesper", version="0.1.0")

init_db()

app.include_router(user_router)
app.include_router(auth_router, prefix="/api")
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