from fastapi import FastAPI
from routers.alert import router as alert_router

app = FastAPI(title="Vesper", version="0.1.0")

app.include_router(alert_router, prefix="/vesper/alerts")


@app.get("/health")
def health() -> dict[str, str]:

    return {"status": "ok"}
