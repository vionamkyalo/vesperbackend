import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, List

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from models.zone_baseline import MoonBand

DecimalNumber = Annotated[
    Decimal, PlainSerializer(float, return_type=float, when_used="json")
]


class ZoneBaselineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    baseline_id: uuid.UUID
    zone_id: uuid.UUID
    moon_band: MoonBand
    expected_light_index: DecimalNumber
    nights_used: int
    calculated_at: datetime
    spread: DecimalNumber


class ZoneBaselineFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone_id: uuid.UUID | None = None
    moon_band: MoonBand | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ZoneBaselineRecalculate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone_id: uuid.UUID | None = None
    lookback_days: int = Field(default=90, ge=7, le=365)
    min_nights: int = Field(default=5, ge=1, le=60)


class ZoneBaselineSkipped(BaseModel):
    zone_id: uuid.UUID
    moon_band: MoonBand
    nights_found: int


class ZoneBaselineRecalculateResult(BaseModel):
    updated: List[ZoneBaselineRead]
    skipped: List[ZoneBaselineSkipped]
