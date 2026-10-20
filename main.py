from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import Settings


from routers.user import router as user_router
from routers.auth import router as auth_router


app = FastAPI(
    title="Vesper",
    version="0.1.0",
)

settings = Settings()
app.include_router(user_router)
app.include_router(auth_router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    """Let deployment verification confirm that the API is responding."""
    return {"status": "ok"}


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
