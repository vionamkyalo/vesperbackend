from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from models import ( 
    alert_assignment,
)
from routers.alert_assignment import router as alert_assignment_router

app = FastAPI(title="Vesper", version="0.1.0")

init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    alert_assignment_router,
    prefix="/alert-assignments",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}