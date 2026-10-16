import enum

from sqlalchemy import Column, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import relationship

from database import Base, UTCDateTime, enum_type, utcnow


class ViolationType(str, enum.Enum):
    UNREGISTERED_RIG = "unregistered_rig"
    MISSING_PERMIT = "missing_permit"
    FISHING_IN_CLOSED_AREA = "fishing_in_closed_area"
    FISHING_DURING_CLOSURE = "fishing_during_closure"
    RIG_CAP_EXCEEDED = "rig_cap_exceeded"
    UNAUTHORIZED_GEAR = "unauthorized_gear"


class ReviewStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    REVIEWED = "reviewed"


class ViolationReport(Base):
    __tablename__ = "violation_report"

    violation_id = Column(Uuid, primary_key=True)
    inspection_id = Column(
        ForeignKey("inspection.inspection_id"), nullable=False, index=True
    )
    violation_type = Column(enum_type(ViolationType, "violation_type"), nullable=False)
    rig_identifier = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    review_status = Column(
        enum_type(ReviewStatus, "review_status"),
        nullable=False,
        default=ReviewStatus.SUBMITTED,
    )
    reviewed_by = Column(ForeignKey("users.user_id"), nullable=True)
    reviewed_at = Column(UTCDateTime(), nullable=True)
    recorded_at = Column(UTCDateTime(), nullable=False)
    synced_at = Column(UTCDateTime(), nullable=False, default=utcnow)

    inspection = relationship("Inspection", back_populates="violation_reports")
    reviewer = relationship("User", foreign_keys=[reviewed_by])
