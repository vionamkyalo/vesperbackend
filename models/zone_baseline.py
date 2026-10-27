import enum
import uuid

from sqlalchemy import Column, ForeignKey, Integer, Numeric, UniqueConstraint, Uuid
from sqlalchemy.orm import relationship

from database import Base, UTCDateTime, enum_type, utcnow


class MoonBand(str, enum.Enum):
    DARK = "dark"
    PARTIAL = "partial"
    BRIGHT = "bright"


class ZoneBaseline(Base):
    __tablename__ = "zone_baseline"

    __table_args__ = (
        UniqueConstraint("zone_id", "moon_band", name="uq_zone_baseline_zone_band"),
    )

    baseline_id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    zone_id = Column(ForeignKey("zone.zone_id"), nullable=False)
    moon_band = Column(enum_type(MoonBand, "moon_band"), nullable=False)
    expected_light_index = Column(Numeric(12, 4), nullable=False)
    nights_used = Column(Integer, nullable=False)
    calculated_at = Column(UTCDateTime(), nullable=False, default=utcnow)
    spread = Column(Numeric(12, 4), nullable=False, default=1)

    zone = relationship("Zone", back_populates="baselines")
