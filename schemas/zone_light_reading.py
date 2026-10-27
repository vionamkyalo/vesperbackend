import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.zone_light_reading import IngestionStatus


class ZoneLightReadingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone_id: uuid.UUID
    observation_date: date


class ZoneLightReadingResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    light_index: Decimal = Field(ge=0, max_digits=12, decimal_places=4)
    valid_pixel_count: int = Field(ge=0)
    hotspot_pixel_count: int = Field(ge=0)
    cluster_count: int = Field(ge=0)

    @model_validator(mode="after")
    def check_counts(self):
        if self.hotspot_pixel_count > self.valid_pixel_count:
            raise ValueError(
                "hotspot_pixel_count cannot be greater than valid_pixel_count."
            )
        if self.cluster_count > self.hotspot_pixel_count:
            raise ValueError(
                "cluster_count cannot be greater than hotspot_pixel_count."
            )
        return self


class ZoneLightReadingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reading_id: uuid.UUID
    zone_id: uuid.UUID
    observation_date: date
    ingestion_status: IngestionStatus
    light_index: Decimal | None
    valid_pixel_count: int | None
    hotspot_pixel_count: int | None
    cluster_count: int | None
    created_at: datetime
