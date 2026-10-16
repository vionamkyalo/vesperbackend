import uuid

from sqlalchemy import Column, ForeignKey, Integer, Numeric, Uuid
from sqlalchemy.orm import relationship

from database import Base, UTCDateTime, utcnow


class ZoneSettingHistory(Base):
    __tablename__ = "zone_setting_history"

    history_id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    zone_id = Column(ForeignKey("zone.zone_id"), nullable=False)
    radiance_threshold = Column(Numeric(10, 4), nullable=False)
    cluster_radius_m = Column(Numeric(8, 2), nullable=False)
    min_cluster_points = Column(Integer, nullable=False)
    confidence_threshold = Column(Numeric(5, 4), nullable=False)
    changed_by = Column(ForeignKey("users.user_id"), nullable=False)
    changed_at = Column(UTCDateTime(), nullable=False, default=utcnow)

    zone = relationship("Zone", back_populates="setting_history")
    changer = relationship("User", foreign_keys=[changed_by])
