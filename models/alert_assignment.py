import enum
import uuid

from sqlalchemy import Column, ForeignKey, Uuid
from sqlalchemy.orm import relationship

from database import Base, UTCDateTime, enum_type, utcnow


class AssignmentStatus(str, enum.Enum):
    ASSIGNED = "assigned"
    ACKNOWLEDGED = "acknowledged"
    REPORTED = "reported"
    REASSIGNED = "reassigned"
    FAILED = "failed"


class AlertAssignment(Base):
    __tablename__ = "alert_assignment"

    assignment_id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    alert_id = Column(ForeignKey("alert.alert_id"), nullable=False, index=True)
    officer_id = Column(ForeignKey("users.user_id"), nullable=False, index=True)
    assigned_by = Column(ForeignKey("users.user_id"), nullable=False)
    status = Column(
        enum_type(AssignmentStatus, "assignment_status"),
        nullable=False,
        default=AssignmentStatus.ASSIGNED,
    )
    assigned_at = Column(UTCDateTime(), nullable=False, default=utcnow)
    acknowledged_at = Column(UTCDateTime(), nullable=True)
    reported_at = Column(UTCDateTime(), nullable=True)
    ended_at = Column(UTCDateTime(), nullable=True)

    alert = relationship("Alert", back_populates="assignments")
    officer = relationship(
        "User", back_populates="assignments", foreign_keys=[officer_id]
    )
    assigner = relationship("User", foreign_keys=[assigned_by])
