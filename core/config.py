import json
import logging
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Vesper API"
    environment: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api"

    database_url: str = "sqlite:///./vesper.db"
    create_tables_on_startup: bool = False

    jwt_secret_key: str = Field(
        min_length=32,
        repr=False,
        validation_alias="JWT_SECRET",
    )
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "vesper-api"
    jwt_audience: str = "vesper-clients"
    access_token_ttl_minutes: int = Field(default=30, ge=1, le=60)
    refresh_token_ttl_days: int = Field(default=7, ge=1, le=30)

    CORS_ORIGINS: str | list[str] = "http://localhost:3000,http://127.0.0.1:3000"
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    max_request_bytes: int = 1_000_000
    api_rate_limit_per_minute: int = 120
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15

    assignment_report_timeout_minutes: int = 30
    sync_max_batch: int = 200
    sync_max_clock_skew_minutes: int = 10

    location_retention_days: int = Field(default=90, gt=0)
    max_officer_speed_kmh: float = Field(default=120.0, gt=0)
    location_clock_skew_minutes: int = Field(default=5, ge=0)
    default_arrival_radius_m: float = Field(default=500.0, gt=0)

    baseline_lookback_nights: int = 90
    baseline_min_nights: int = 5
    moon_dark_max_illumination: float = 0.25
    moon_partial_max_illumination: float = 0.75

    seed_coordinator_first_name: str = ""
    seed_coordinator_last_name: str = ""
    seed_coordinator_email: str = ""
    seed_coordinator_phone: str = ""
    seed_coordinator_password: SecretStr = SecretStr("")

    satellite_provider: Literal["static", "earth_engine"] = "static"
    earth_engine_project: str = ""
    earth_engine_service_account: str = ""
    earth_engine_key_path: str = ""
    viirs_collection: str = "NASA/VIIRS/002/VNP46A2"
    viirs_radiance_band: str = "DNB_BRDF_Corrected_NTL"
    viirs_quality_band: str = "Mandatory_Quality_Flag"
    viirs_radiance_scale: float = 1.0
    viirs_pixel_scale_m: int = 500
    earthdata_token: SecretStr = SecretStr("")
    laads_base_url: str = "https://ladsweb.modaps.eosdis.nasa.gov/archive/allData"
    laads_archive_set: str = "5200"
    viirs_daily_product: str = "VNP46A1"
    viirs_tile: str = "h20v10"
    kariba_bbox: list[float] = [26.5, -18.6, 29.5, -16.3]
    min_clear_fraction: float = 0.3

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    email_from: str = ""
    frontend_url: str = "http://localhost:3000"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def seed_coordinator_configured(self) -> bool:
        return bool(self.seed_coordinator_email)

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @model_validator(mode="after")
    def check_settings(self) -> "Settings":
        if self.moon_dark_max_illumination >= self.moon_partial_max_illumination:
            raise ValueError(
                "moon_dark_max_illumination must be lower than moon_partial_max_illumination"
            )

        if self.seed_coordinator_email:
            missing = [
                name
                for name in ("first_name", "last_name", "phone")
                if not getattr(self, f"seed_coordinator_{name}")
            ]
            if missing:
                raise ValueError("Seed coordinator is missing: " + ", ".join(missing))

        if self.is_production:
            if "*" in self.cors_allowed_origins:
                raise ValueError("Wildcard CORS origins are not allowed in production")
            if self.database_url.startswith("sqlite"):
                raise ValueError("SQLite is not allowed in production")
            if self.create_tables_on_startup:
                raise ValueError(
                    "Use migrations in production, not create_tables_on_startup"
                )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


SENSITIVE_KEYS = [
    "password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "secret",
]


def redact(data: dict) -> dict:
    return {
        key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else value
        for key, value in data.items()
    }


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            entry.update(redact(extra))
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if any(isinstance(handler.formatter, JsonFormatter) for handler in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)
