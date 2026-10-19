import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.violation_report import ReviewStatus, ViolationType


class ViolationReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    violation_id: uuid.UUID
    inspection_id: uuid.UUID
    violation_type: ViolationType
    rig_identifier: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=4000)
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def require_timezone(cls, value):
        if value.tzinfo is None:
            raise ValueError(
                "recorded_at must include a time zone, for example 2026-10-15T21:30:00Z"
            )
        return value.astimezone(timezone.utc)


class ViolationReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    violation_id: uuid.UUID
    inspection_id: uuid.UUID
    violation_type: ViolationType
    rig_identifier: str
    description: str
    review_status: ReviewStatus
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    recorded_at: datetime
    synced_at: datetime
