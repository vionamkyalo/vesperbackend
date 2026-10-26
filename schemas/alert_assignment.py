import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from models.alert_assignment import AssignmentStatus


class AlertAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_id: uuid.UUID
    officer_id: uuid.UUID


class AlertAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assignment_id: uuid.UUID
    alert_id: uuid.UUID
    officer_id: uuid.UUID
    assigned_by: uuid.UUID
    status: AssignmentStatus
    assigned_at: datetime
    acknowledged_at: datetime | None
    reported_at: datetime | None
    ended_at: datetime | None
