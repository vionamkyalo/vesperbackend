import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, List, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)

from models.zone import ZoneType

DecimalNumber = Annotated[
    Decimal, PlainSerializer(float, return_type=float, when_used="json")
]

MAX_POLYGON_POSITIONS = 2000


class GeoJSONPolygon(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["Polygon"]
    coordinates: List[List[List[float]]] = Field(min_length=1, max_length=20)

    @field_validator("coordinates")
    @classmethod
    def check_rings(cls, rings):
        total = 0
        for ring in rings:
            if len(ring) < 4:
                raise ValueError("Each ring needs at least 4 positions")
            if ring[0] != ring[-1]:
                raise ValueError(
                    "Each ring must be closed (first and last positions equal)"
                )
            for position in ring:
                if len(position) != 2:
                    raise ValueError("Positions must be [longitude, latitude]")
                longitude, latitude = position
                if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
                    raise ValueError(
                        "Position is outside valid longitude/latitude ranges"
                    )
            total += len(ring)

        if total > MAX_POLYGON_POSITIONS:
            raise ValueError(f"Polygon has more than {MAX_POLYGON_POSITIONS} positions")
        return rings


class ZoneSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    radiance_threshold: Decimal = Field(ge=0, max_digits=10, decimal_places=4)
    cluster_radius_m: Decimal = Field(gt=0, le=50000, max_digits=8, decimal_places=2)
    min_cluster_points: int = Field(ge=1, le=1000)
    confidence_threshold: Decimal = Field(ge=0, le=1, max_digits=5, decimal_places=4)


class ZoneCreate(ZoneSettings):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    basin: str = Field(min_length=1, max_length=50)
    zone_type: ZoneType
    boundary: GeoJSONPolygon
    boat_cap: int | None = Field(default=None, ge=0)
    closure_start: date | None = None
    closure_end: date | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def check_closure(self):
        if self.closure_end is not None and self.closure_start is None:
            raise ValueError("closure_end needs closure_start")
        if (
            self.closure_start is not None
            and self.closure_end is not None
            and self.closure_end < self.closure_start
        ):
            raise ValueError("closure_end must be on or after closure_start")
        return self


class ZoneUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    basin: str | None = Field(default=None, min_length=1, max_length=50)
    zone_type: ZoneType | None = None
    boundary: GeoJSONPolygon | None = None
    boat_cap: int | None = Field(default=None, ge=0)
    closure_start: date | None = None
    closure_end: date | None = None
    is_active: bool | None = None


class ZoneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    zone_id: uuid.UUID
    name: str
    basin: str
    zone_type: ZoneType
    boundary: dict
    boat_cap: int | None
    closure_start: date | None
    closure_end: date | None
    radiance_threshold: DecimalNumber
    cluster_radius_m: DecimalNumber
    min_cluster_points: int
    confidence_threshold: DecimalNumber
    is_active: bool
    updated_by: uuid.UUID | None
    rules_confirmed_by: uuid.UUID | None
    rules_confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime
