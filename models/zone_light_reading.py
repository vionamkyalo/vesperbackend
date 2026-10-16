import enum
import uuid

from sqlalchemy import (
    Column,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import relationship

from database import Base, UTCDateTime, enum_type, utcnow


class IngestionStatus(str, enum.Enum):
    PENDING = "pending"
    RECEIVED = "received"
    INGESTION_ERROR = "ingestion_error"


class ZoneLightReading(Base):
    __tablename__ = "zone_light_reading"

    __table_args__ = (
        UniqueConstraint("zone_id", "observation_date", name="uq_reading_zone_date"),
    )

    reading_id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    zone_id = Column(ForeignKey("zone.zone_id"), nullable=False)
    observation_date = Column(Date, nullable=False)
    ingestion_status = Column(
        enum_type(IngestionStatus, "ingestion_status"),
        nullable=False,
        default=IngestionStatus.PENDING,
    )
    light_index = Column(Numeric(12, 4), nullable=True)
    valid_pixel_count = Column(Integer, nullable=True)
    hotspot_pixel_count = Column(Integer, nullable=True)
    cluster_count = Column(Integer, nullable=True)
    created_at = Column(UTCDateTime(), nullable=False, default=utcnow)

    zone = relationship("Zone", back_populates="readings")
    alerts = relationship("Alert", back_populates="reading")
