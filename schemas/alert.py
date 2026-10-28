import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    computed_field,
    field_validator,
    model_validator,
)

from models.alert import AlertStatus, VerificationResult
from models.alert_assignment import AssignmentStatus


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

Confidence = Annotated[
    Decimal,
    Field(ge=Decimal("0"), le=Decimal("1"), allow_inf_nan=False),
    AfterValidator(_rounded_to(4)),
    _AS_JSON_NUMBER,
]

INT32_MAX = 2_147_483_647
HIGH_PRIORITY_MIN = Decimal("0.75")
MEDIUM_PRIORITY_MIN = Decimal("0.50")
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100

NEUTRAL_ALERT_SUMMARY = (
    "Unusually high fishing-light activity was detected in this zone. "
    "It needs a field check."
)


def priority_for(confidence: Decimal) -> Literal["high", "medium", "low"]:
    if confidence >= HIGH_PRIORITY_MIN:
        return "high"
    if confidence >= MEDIUM_PRIORITY_MIN:
        return "medium"
    return "low"


class AlertCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone_id: uuid.UUID
    reading_id: uuid.UUID
    cluster_label: int = Field(ge=0, le=INT32_MAX)
    point_count: int = Field(gt=0, le=INT32_MAX)
    confidence: Confidence
    centroid_latitude: Latitude
    centroid_longitude: Longitude


class AlertStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: AlertStatus


class AlertVerificationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verification_result: VerificationResult

    @field_validator("verification_result")
    @classmethod
    def must_be_a_final_result(cls, value: VerificationResult) -> VerificationResult:
        if value == VerificationResult.PENDING:
            raise ValueError(
                "verification_result must be activity_confirmed or no_activity"
            )
        return value


class AlertListQuery(BaseModel):
    zone_id: uuid.UUID | None = None
    status: AlertStatus | None = None
    verification_result: VerificationResult | None = None
    officer_id: uuid.UUID | None = None
    min_confidence: Confidence | None = None
    created_from: AwareDatetime | None = None
    created_to: AwareDatetime | None = None
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)

    @model_validator(mode="after")
    def check_date_range(self) -> "AlertListQuery":
        if self.created_from and self.created_to:
            if self.created_from > self.created_to:
                raise ValueError("created_from must be on or before created_to")
        return self


class MyAlertsQuery(BaseModel):
    status: AlertStatus | None = None
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alert_id: uuid.UUID
    zone_id: uuid.UUID
    reading_id: uuid.UUID
    cluster_label: int
    point_count: int
    confidence: Confidence
    centroid_latitude: Latitude
    centroid_longitude: Longitude
    status: AlertStatus
    verification_result: VerificationResult
    verified_at: datetime | None
    officer_id: uuid.UUID | None
    assigned_by: uuid.UUID | None
    assignment_status: AssignmentStatus | None
    assigned_at: datetime | None
    reported_at: datetime | None
    created_at: datetime

    @computed_field
    @property
    def priority(self) -> Literal["high", "medium", "low"]:
        return priority_for(self.confidence)

    @computed_field
    @property
    def summary(self) -> str:
        return NEUTRAL_ALERT_SUMMARY


class AlertPage(BaseModel):
    items: list[AlertRead]
    total: int
    skip: int
    limit: int
