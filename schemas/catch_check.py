from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class CatchCheckCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    catch_id: UUID
    inspection_id: UUID
    rig_identifier: str = Field(min_length=1, max_length=50)
    rig_nights: int = Field(ge=1)
    type_of_fish: Optional[str] = Field(default=None, max_length=100)
    catch_weight_kg: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    notes: Optional[str] = Field(default=None, max_length=2000)
    checked_at: datetime

    @field_validator("checked_at")
    @classmethod
    def validate_checked_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("checked_at must include a timezone")
        return value.astimezone(timezone.utc)

    @field_validator("type_of_fish", "notes")
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            return None
        return value


class CatchCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    catch_id: UUID
    inspection_id: UUID
    rig_identifier: str
    rig_nights: int
    type_of_fish: Optional[str]
    catch_weight_kg: Decimal
    catch_per_rig_night: Decimal
    notes: Optional[str]
    checked_at: datetime
    synced_at: datetime

    @field_serializer(
        "catch_weight_kg",
        "catch_per_rig_night",
        when_used="json",
    )
    def serialize_decimal_as_number(self, value: Decimal) -> float:
        return float(value)
