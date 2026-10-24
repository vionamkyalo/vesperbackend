from sqlalchemy import Column, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import relationship

from database import Base, UTCDateTime, utcnow


class CatchCheck(Base):
    __tablename__ = "catch_check"

    catch_id = Column(Uuid, primary_key=True)
    inspection_id = Column(
        ForeignKey("inspection.inspection_id"), nullable=False, index=True
    )
    rig_identifier = Column(String(50), nullable=False)
    rig_nights = Column(Integer, nullable=False)
    type_of_fish = Column(String(100), nullable=True)
    catch_weight_kg = Column(Numeric(10, 2), nullable=False)
    catch_per_rig_night = Column(Numeric(10, 2), nullable=False)
    notes = Column(Text, nullable=True)
    checked_at = Column(UTCDateTime(), nullable=False)
    synced_at = Column(UTCDateTime(), nullable=False, default=utcnow)

    inspection = relationship("Inspection", back_populates="catch_checks")
