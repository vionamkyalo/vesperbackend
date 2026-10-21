from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    JWT_SECRET: str = Field(min_length=32)
    JWT_ALGORITHM: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=60, gt=0)
    location_retention_days: int = Field(default=90, gt=0)
    max_officer_speed_kmh: float = Field(default=120.0, gt=0)
    location_clock_skew_minutes: int = Field(default=5, ge=0)
    default_arrival_radius_m: float = Field(default=500.0, gt=0)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:

    return Settings()
