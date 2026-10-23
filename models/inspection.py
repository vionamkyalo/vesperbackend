import enum
import uuid

from sqlalchemy import Column, ForeignKey, Integer, Numeric, Text, Uuid
from sqlalchemy.orm import relationship

from database import Base, UTCDateTime, enum_type, utcnow


class InspectionType(str, enum.Enum):
    SITE = "site"
    LANDING_SITE = "landing_site"
    ZONE = "zone"


class InspectionOutcome(str, enum.Enum):
    ACTIVITY_CONSISTENT = "activity_consistent"
    NO_ACTIVITY = "no_activity"
    NO_FISHING_LIGHT = "no_fishing_light"
    UNABLE_TO_VERIFY = "unable_to_verify"


class Inspection(Base):
    __tablename__ = "inspection"

    inspection_id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    alert_id = Column(ForeignKey("alert.alert_id"), nullable=True, index=True)
    officer_id = Column(ForeignKey("users.user_id"), nullable=False, index=True)
    zone_id = Column(ForeignKey("zone.zone_id"), nullable=False, index=True)

    inspection_type = Column(
        enum_type(InspectionType, "inspection_type"), nullable=False
    )
    outcome = Column(enum_type(InspectionOutcome, "inspection_outcome"), nullable=False)
    rigs_observed = Column(Integer, nullable=False)
    latitude = Column(Numeric(9, 6), nullable=False)
    longitude = Column(Numeric(9, 6), nullable=False)
    notes = Column(Text, nullable=True)
    inspected_at = Column(UTCDateTime(), nullable=False)
    synced_at = Column(UTCDateTime(), nullable=False, default=utcnow)

    alert = relationship("Alert", back_populates="inspections")
    officer = relationship("User", back_populates="inspections")
    zone = relationship("Zone", back_populates="inspections")
    violation_reports = relationship("ViolationReport", back_populates="inspection")
    catch_checks = relationship("CatchCheck", back_populates="inspection")
