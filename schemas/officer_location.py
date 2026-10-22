import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)


def _rounded_to(places: int):

    step = Decimal(1).scaleb(-places)

    def _round(value: Decimal) -> Decimal:
        return value.quantize(step, rounding=ROUND_HALF_UP)

    return _round


_AS_JSON_NUMBER = PlainSerializer(float, return_type=float, when_used="json")

Latitude = Annotated[
    Decimal,
    Field(ge=Decimal("-90"), le=Decimal("90"), allow_inf_nan=False),
    AfterValidator(_rounded_to(6)),
    _AS_JSON_NUMBER,
]

Longitude = Annotated[
    Decimal,
    Field(ge=Decimal("-180"), le=Decimal("180"), allow_inf_nan=False),
    AfterValidator(_rounded_to(6)),
    _AS_JSON_NUMBER,
]

AccuracyMetres = Annotated[
    Decimal,
    Field(ge=Decimal("0"), le=Decimal("999999.99"), allow_inf_nan=False),
    AfterValidator(_rounded_to(2)),
    _AS_JSON_NUMBER,
]


DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500


class OfficerLocationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: uuid.UUID
    alert_id: uuid.UUID | None = None
    latitude: Latitude
    longitude: Longitude
    accuracy_m: AccuracyMetres | None = None
    recorded_at: AwareDatetime

    @field_validator("recorded_at")
    @classmethod
    def to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


class LocationListQuery(BaseModel):
    officer_id: uuid.UUID | None = None
    alert_id: uuid.UUID | None = None
    recorded_from: AwareDatetime | None = None
    recorded_to: AwareDatetime | None = None
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)

    @model_validator(mode="after")
    def check_time_range(self) -> "LocationListQuery":
        if self.recorded_from and self.recorded_to:
            if self.recorded_from > self.recorded_to:
                raise ValueError("recorded_from must be on or before recorded_to")
        return self


class OfficerLocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    location_id: uuid.UUID
    officer_id: uuid.UUID
    alert_id: uuid.UUID | None
    latitude: Latitude
    longitude: Longitude
    accuracy_m: AccuracyMetres | None
    recorded_at: datetime
    synced_at: datetime
    jump_flagged: bool = False
    speed_from_previous_kmh: float | None = None


class OfficerLocationPage(BaseModel):
    items: list[OfficerLocationRead]
    total: int
    skip: int
    limit: int


class ArrivalCheckRead(BaseModel):
    alert_id: uuid.UUID
    officer_id: uuid.UUID | None
    arrived: bool
    arrival_radius_m: float
    closest_distance_m: float | None
    closest_location_id: uuid.UUID | None
    first_arrival_at: datetime | None
    positions_checked: int
    positions_ignored_as_jumps: int


class LocationPurgeResult(BaseModel):
    deleted_count: int
    cutoff: datetime
