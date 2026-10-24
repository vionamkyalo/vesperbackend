from datetime import date
from typing import List

from pydantic import BaseModel, ConfigDict, Field

from models.zone_baseline import MoonBand


class DetectionPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radiance: float = Field(ge=0)
    near_shore: bool = False


class DetectionRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_date: date
    points: List[DetectionPoint] = Field(default_factory=list, max_length=100_000)


class DetectionAlert(BaseModel):
    alert_id: str
    zone_id: str
    cluster_label: int
    point_count: int
    score: float
    confidence: float


class DetectionResult(BaseModel):
    observation_date: date
    moon_band: MoonBand
    readings_saved: int
    alerts: List[DetectionAlert]
