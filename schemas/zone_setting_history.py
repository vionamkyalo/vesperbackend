import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

DecimalNumber = Annotated[
    Decimal, PlainSerializer(float, return_type=float, when_used="json")
]


class ZoneSettingHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    history_id: uuid.UUID
    zone_id: uuid.UUID
    radiance_threshold: DecimalNumber
    cluster_radius_m: DecimalNumber
    min_cluster_points: int
    confidence_threshold: DecimalNumber
    changed_by: uuid.UUID
    changed_at: datetime
