from fastapi import FastAPI

from routers import zone

app = FastAPI(title="Vesper", version="0.1.0")
app.include_router(zone.router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
