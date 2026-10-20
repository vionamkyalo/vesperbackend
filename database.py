import os
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.types import TypeDecorator

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def utcnow():
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


GeoJSON = JSON().with_variant(JSONB(), "postgresql")


def enum_type(enum_class, name):
    return Enum(
        enum_class,
        name=name,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


def init_db():
    """Create all tables. Models are imported here, when the function runs,
    so SQLAlchemy knows about every table (and to avoid a circular import)."""
    import models.alert  # noqa: F401
    import models.alert_assignment  # noqa: F401
    import models.catch_check  # noqa: F401
    import models.inspection  # noqa: F401
    import models.officer_location  # noqa: F401
    import models.user  # noqa: F401
    import models.violation_report  # noqa: F401
    import models.zone  # noqa: F401
    import models.zone_baseline  # noqa: F401
    import models.zone_light_reading  # noqa: F401
    import models.zone_setting_history  # noqa: F401

    Base.metadata.create_all(bind=engine)
