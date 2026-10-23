import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, List, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
)

from models.zone import ZoneType

DecimalNumber = Annotated[
    Decimal, PlainSerializer(float, return_type=float, when_used="json")
]


class GeoJSONPolygon(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["Polygon"]
    coordinates: List[List[List[float]]] = Field(min_length=1, max_length=20)


class BasinRead(BaseModel):
    name: str
    boundary: dict


class BasinSourceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=50)
    boundary: GeoJSONPolygon


class BasinSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basins: List[BasinSourceItem] = Field(min_length=1)


class ZoneSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    radiance_threshold: Decimal = Field(ge=0, max_digits=10, decimal_places=4)
    cluster_radius_m: Decimal = Field(gt=0, le=50000, max_digits=8, decimal_places=2)
    min_cluster_points: int = Field(ge=1, le=1000)
    confidence_threshold: Decimal = Field(ge=0, le=1, max_digits=5, decimal_places=4)


class ZoneSourceDefaults(ZoneSettings):
    zone_type: ZoneType


class ZoneSourceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    basin: str = Field(min_length=1, max_length=50)
    managed_by: str | None = Field(default=None, max_length=100)
    zone_type: ZoneType | None = None
    boundary: GeoJSONPolygon


class ZoneSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str | None = None
    defaults: ZoneSourceDefaults
    zones: List[ZoneSourceItem] = Field(min_length=1)


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
