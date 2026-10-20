import enum
import uuid

from sqlalchemy import Boolean, Column, String, Uuid

from database import Base, UTCDateTime, enum_type, utcnow


class UserRole(str, enum.Enum):
    PATROL_COORDINATOR = "patrol_coordinator"
    PATROL_OFFICER = "patrol_officer"


class User(Base):
    __tablename__ = "users"

    user_id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone_number = Column(String(20), nullable=False, unique=True)
    email = Column(String(100), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(enum_type(UserRole, "user_role"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at = Column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow)

    # alert_assignments = relationship("AlertAssignment", back_populates="officer")
    # inspections = relationship("Inspection", back_populates="officer")
    # locations = relationship("OfficerLocation", back_populates="officer")
