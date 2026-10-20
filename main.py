from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.security import apply_security
from database import Base, engine


from routers.user import router as user_router
from routers.auth import router as auth_router


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.create_tables_on_startup:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Vesper",
    version="0.1.0",
    lifespan=lifespan,
)

apply_security(app, settings)

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
