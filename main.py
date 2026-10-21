from fastapi import FastAPI

app = FastAPI(title="Vesper", version="0.1.0")


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers.inspection_report import router as inspection_report_router

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
    inspection_report_router,
    prefix="/inspection-reports",
)
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

