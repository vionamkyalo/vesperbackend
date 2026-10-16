from sqlalchemy import Column, ForeignKey, Numeric, Uuid
from sqlalchemy.orm import relationship

from database import Base, UTCDateTime, utcnow


class OfficerLocation(Base):
    __tablename__ = "officer_location"

    location_id = Column(Uuid, primary_key=True)
    officer_id = Column(ForeignKey("users.user_id"), nullable=False, index=True)
    alert_id = Column(ForeignKey("alert.alert_id"), nullable=True)
    latitude = Column(Numeric(9, 6), nullable=False)
    longitude = Column(Numeric(9, 6), nullable=False)
    accuracy_m = Column(Numeric(8, 2), nullable=True)
    recorded_at = Column(UTCDateTime(), nullable=False)
    synced_at = Column(UTCDateTime(), nullable=False, default=utcnow)

    officer = relationship("User", back_populates="locations")
    alert = relationship("Alert")
