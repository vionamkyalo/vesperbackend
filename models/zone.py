import enum
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, Numeric, String, Uuid
from sqlalchemy.orm import relationship

from database import Base, GeoJSON, UTCDateTime, enum_type, utcnow


class ZoneType(str, enum.Enum):
    FISHING_ZONE = "fishing_zone"
    RESTRICTED_AREA = "restricted_area"


class Zone(Base):
    __tablename__ = "zone"

    zone_id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    basin = Column(String(50), nullable=False)
    zone_type = Column(enum_type(ZoneType, "zone_type"), nullable=False)
    boundary = Column(GeoJSON, nullable=False)
    boat_cap = Column(Integer, nullable=True)
    closure_start = Column(Date, nullable=True)
    closure_end = Column(Date, nullable=True)

    radiance_threshold = Column(Numeric(10, 4), nullable=False)
    cluster_radius_m = Column(Numeric(8, 2), nullable=False)
    min_cluster_points = Column(Integer, nullable=False, default=3)
    confidence_threshold = Column(Numeric(5, 4), nullable=False, default=Decimal("0.5"))
    is_active = Column(Boolean, nullable=False, default=True)

    updated_by = Column(ForeignKey("users.user_id"), nullable=True)
    rules_confirmed_by = Column(ForeignKey("users.user_id"), nullable=True)
    rules_confirmed_at = Column(UTCDateTime(), nullable=True)
    created_at = Column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at = Column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow)

    readings = relationship("ZoneLightReading", back_populates="zone")
    baselines = relationship("ZoneBaseline", back_populates="zone")
    setting_history = relationship("ZoneSettingHistory", back_populates="zone")
    alerts = relationship("Alert", back_populates="zone")
    inspections = relationship("Inspection", back_populates="zone")
