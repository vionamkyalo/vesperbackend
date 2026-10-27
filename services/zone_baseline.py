import logging
import math
import statistics
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from database import utcnow
from models.user import User, UserRole
from models.zone import Zone
from models.zone_baseline import MoonBand, ZoneBaseline
from repositories.zone import zone_repository
from repositories.zone_baseline import zone_baseline_repository
from schemas.zone_baseline import (
    ZoneBaselineFilter,
    ZoneBaselineRead,
    ZoneBaselineRecalculate,
    ZoneBaselineRecalculateResult,
    ZoneBaselineSkipped,
)

logger = logging.getLogger(__name__)

SYNODIC_MONTH_DAYS = 29.530588853
REFERENCE_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
OBSERVATION_HOUR_UTC = 22
DARK_MAX_ILLUMINATION = 0.25
BRIGHT_MIN_ILLUMINATION = 0.75
LIGHT_INDEX_PLACES = Decimal("0.0001")
MAD_SCALE = Decimal("1.4826")
MIN_SPREAD = Decimal("0.1000")


def moon_illumination(day):
    moment = datetime(
        day.year, day.month, day.day, OBSERVATION_HOUR_UTC, tzinfo=timezone.utc
    )
    age = ((moment - REFERENCE_NEW_MOON).total_seconds() / 86400) % (SYNODIC_MONTH_DAYS)
    return (1 - math.cos(2 * math.pi * age / SYNODIC_MONTH_DAYS)) / 2


def moon_band_for(day):
    illumination = moon_illumination(day)
    if illumination < DARK_MAX_ILLUMINATION:
        return MoonBand.DARK
    if illumination < BRIGHT_MIN_ILLUMINATION:
        return MoonBand.PARTIAL
    return MoonBand.BRIGHT


def spread_of(values, centre):
    deviations = [abs(value - centre) for value in values]
    mad = Decimal(statistics.median(deviations)) * MAD_SCALE
    return max(mad, MIN_SPREAD).quantize(LIGHT_INDEX_PLACES, rounding=ROUND_HALF_UP)


class ZoneBaselineService:
    def check_active(self, current_user: User):
        if current_user is None or not current_user.is_active:
            logger.warning("baseline access refused: inactive or unknown user")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not active.",
            )

    def check_coordinator(self, current_user: User):
        self.check_active(current_user)

        if current_user.role != UserRole.PATROL_COORDINATOR:
            logger.warning(
                f"baseline action refused: user {current_user.user_id} is not the coordinator"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the patrol coordinator can do this.",
            )

    def list_baselines(
        self, db: Session, current_user: User, filters: ZoneBaselineFilter
    ):
        self.check_coordinator(current_user)
        return zone_baseline_repository.list_baselines(
            db,
            zone_id=filters.zone_id,
            moon_band=filters.moon_band,
            limit=filters.limit,
            offset=filters.offset,
        )

    def get_baseline(self, db: Session, current_user: User, baseline_id: uuid.UUID):
        self.check_coordinator(current_user)
        baseline = zone_baseline_repository.get(db, baseline_id)

        if baseline is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Baseline was not found.",
            )

        return baseline

    def zones_to_recalculate(self, db: Session, zone_id):
        if zone_id is None:
            return db.query(Zone).order_by(Zone.name).all()

        zone = zone_repository.get(db, zone_id)
        if zone is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Zone was not found."
            )
        return [zone]

    def nights_by_band(self, readings):
        nights = {band: [] for band in MoonBand}
        for reading in readings:
            nights[moon_band_for(reading.observation_date)].append(
                Decimal(reading.light_index)
            )
        return nights

    def save_baseline(self, db: Session, zone_id, moon_band, values):
        median = Decimal(statistics.median(values))
        expected = median.quantize(LIGHT_INDEX_PLACES, rounding=ROUND_HALF_UP)
        spread = spread_of(values, median)
        baseline = zone_baseline_repository.get_by_zone_band(db, zone_id, moon_band)

        if baseline is None:
            return zone_baseline_repository.create(
                db,
                ZoneBaseline(
                    zone_id=zone_id,
                    moon_band=moon_band,
                    expected_light_index=expected,
                    spread=spread,
                    nights_used=len(values),
                    calculated_at=utcnow(),
                ),
            )

        baseline.expected_light_index = expected
        baseline.spread = spread
        baseline.nights_used = len(values)
        baseline.calculated_at = utcnow()
        return zone_baseline_repository.update(db, baseline)

    def recalculate(
        self, db: Session, current_user: User, data: ZoneBaselineRecalculate
    ):
        self.check_coordinator(current_user)

        until = utcnow().date()
        since = until - timedelta(days=data.lookback_days)
        updated, skipped = [], []

        for zone in self.zones_to_recalculate(db, data.zone_id):
            readings = zone_baseline_repository.list_received_readings(
                db, zone.zone_id, since, until
            )
            for moon_band, values in self.nights_by_band(readings).items():
                if len(values) < data.min_nights:
                    skipped.append(
                        ZoneBaselineSkipped(
                            zone_id=zone.zone_id,
                            moon_band=moon_band,
                            nights_found=len(values),
                        )
                    )
                    continue
                updated.append(self.save_baseline(db, zone.zone_id, moon_band, values))

        logger.info(
            f"baselines recalculated by {current_user.user_id}: "
            f"{len(updated)} updated, {len(skipped)} skipped, "
            f"{data.lookback_days} days back"
        )
        return ZoneBaselineRecalculateResult(
            updated=[ZoneBaselineRead.model_validate(item) for item in updated],
            skipped=skipped,
        )


zone_baseline_service = ZoneBaselineService()
