import enum
import uuid

from sqlalchemy import Column, ForeignKey, Integer, Numeric, UniqueConstraint, Uuid
from sqlalchemy.orm import relationship

from database import Base, UTCDateTime, enum_type, utcnow
from models.alert_assignment import AssignmentStatus


class AlertStatus(str, enum.Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    DISMISSED = "dismissed"
    CLOSED = "closed"


class VerificationResult(str, enum.Enum):
    PENDING = "pending"
    ACTIVITY_CONFIRMED = "activity_confirmed"
    NO_ACTIVITY = "no_activity"


class Alert(Base):
    __tablename__ = "alert"

    __table_args__ = (
        UniqueConstraint(
            "reading_id", "cluster_label", name="uq_alert_reading_cluster"
        ),
    )

    alert_id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    zone_id = Column(ForeignKey("zone.zone_id"), nullable=False, index=True)
    reading_id = Column(ForeignKey("zone_light_reading.reading_id"), nullable=False)

    cluster_label = Column(Integer, nullable=False)
    point_count = Column(Integer, nullable=False)
    confidence = Column(Numeric(5, 4), nullable=False)
    centroid_latitude = Column(Numeric(9, 6), nullable=False)
    centroid_longitude = Column(Numeric(9, 6), nullable=False)

    status = Column(
        enum_type(AlertStatus, "alert_status"), nullable=False, default=AlertStatus.NEW
    )
    verification_result = Column(
        enum_type(VerificationResult, "verification_result"),
        nullable=False,
        default=VerificationResult.PENDING,
    )
    verified_at = Column(UTCDateTime(), nullable=True)

    officer_id = Column(ForeignKey("users.user_id"), nullable=True, index=True)
    assigned_by = Column(ForeignKey("users.user_id"), nullable=True)
    assignment_status = Column(
        enum_type(AssignmentStatus, "assignment_status"), nullable=True
    )
    assigned_at = Column(UTCDateTime(), nullable=True)
    reported_at = Column(UTCDateTime(), nullable=True)
    created_at = Column(UTCDateTime(), nullable=False, default=utcnow)

    zone = relationship("Zone", back_populates="alerts")
    reading = relationship("ZoneLightReading", back_populates="alerts")
    officer = relationship("User", foreign_keys=[officer_id])
    assigner = relationship("User", foreign_keys=[assigned_by])
    assignments = relationship(
        "AlertAssignment",
        back_populates="alert",
        order_by="AlertAssignment.assigned_at",
    )
    inspections = relationship("Inspection", back_populates="alert")
