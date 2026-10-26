import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator

from models.inspection import InspectionOutcome, InspectionType

DecimalNumber = Annotated[
    Decimal, PlainSerializer(float, return_type=float, when_used="json")
]


class InspectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    alert_id: uuid.UUID | None = None
    zone_id: uuid.UUID
    inspection_type: InspectionType
    outcome: InspectionOutcome
    rigs_observed: int = Field(ge=0, le=1000)
    latitude: Decimal = Field(ge=-90, le=90)
    longitude: Decimal = Field(ge=-180, le=180)
    notes: str | None = Field(default=None, max_length=2000)
    inspected_at: datetime

    @field_validator("latitude", "longitude")
    @classmethod
    def six_decimal_places(cls, value):
        return value.quantize(Decimal("0.000001"))

    @field_validator("inspected_at")
    @classmethod
    def require_timezone(cls, value):
        if value.tzinfo is None:
            raise ValueError(
                "inspected_at must include a time zone, for example 2026-10-15T21:30:00Z"
            )
        return value.astimezone(timezone.utc)


class InspectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    inspection_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    alert_id: uuid.UUID | None
    officer_id: uuid.UUID
    zone_id: uuid.UUID
    inspection_type: InspectionType
    outcome: InspectionOutcome
    rigs_observed: int
    latitude: DecimalNumber
    longitude: DecimalNumber
    notes: str | None
    inspected_at: datetime
    synced_at: datetime
