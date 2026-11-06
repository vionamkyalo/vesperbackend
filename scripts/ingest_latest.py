"""Ingest every recent night NASA has published, run detection on it, and
refresh the zone baselines.

Heroku Scheduler runs this once a day:

    python -m scripts.ingest_latest

Each run looks back LOOKBACK_DAYS and fetches any night that has no readings
yet (NASA publishes 1-3 days late, so nights it has not published are tried
again on the next run). When new nights were saved, the baselines are
recalculated from the same window so "normal" for each zone stays current.

For a one-off longer backfill, pass the number of days:

    python -m scripts.ingest_latest 90
"""

import logging
import sys
import urllib.error
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

import main  # noqa: F401  (loads every model so relationships resolve)
from database import SessionLocal, utcnow
from models.user import User, UserRole
from models.zone_baseline import MoonBand
from models.zone_light_reading import ZoneLightReading
from schemas.zone_baseline import ZoneBaselineRecalculate
from services.ingestion import ingestion_service
from services.zone_baseline import moon_band_for, zone_baseline_service

LOOKBACK_DAYS = 30
BASELINE_MIN_NIGHTS = 3

logger = logging.getLogger("ingest_latest")


def nights_to_fetch(db: Session, today: date, lookback: int = LOOKBACK_DAYS):
    """Nights in the lookback window that have no readings yet, oldest first."""
    first = today - timedelta(days=lookback)
    done = {
        night
        for (night,) in db.query(ZoneLightReading.observation_date)
        .filter(ZoneLightReading.observation_date >= first)
        .distinct()
    }
    nights = [today - timedelta(days=days) for days in range(lookback, 0, -1)]
    return [night for night in nights if night not in done]


def acting_coordinator(db: Session):
    return (
        db.query(User)
        .filter(
            User.role == UserRole.PATROL_COORDINATOR,
            User.is_active.is_(True),
        )
        .order_by(User.created_at)
        .first()
    )


def refresh_baselines(db: Session, coordinator: User, lookback: int):
    try:
        result = zone_baseline_service.recalculate(
            db,
            coordinator,
            ZoneBaselineRecalculate(
                lookback_days=max(lookback, 7), min_nights=BASELINE_MIN_NIGHTS
            ),
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Baseline recalculation failed")
        return
    logger.info(
        f"Baselines refreshed: {len(result.updated)} updated, "
        f"{len(result.skipped)} skipped (not enough nights yet)"
    )


def run(db: Session, today: date, lookback: int = LOOKBACK_DAYS) -> dict:
    coordinator = acting_coordinator(db)
    if coordinator is None:
        logger.error("No active coordinator to run ingestion as; nothing done.")
        return {}

    results = {}
    saved_new_night = False
    for night in nights_to_fetch(db, today, lookback):
        if moon_band_for(night) == MoonBand.BRIGHT:
            results[night] = "skipped (moon too bright)"
            logger.info(f"{night}: {results[night]}")
            continue
        try:
            result = ingestion_service.run_for_night(db, coordinator, night)
        except (urllib.error.HTTPError, HTTPException) as error:
            db.rollback()
            code = getattr(error, "status_code", None) or getattr(error, "code", None)
            if code == 404:
                results[night] = "not published yet"
            else:
                results[night] = f"failed ({code})"
                logger.warning(f"{night}: failed with {code}: {error}")
        except Exception:
            db.rollback()
            results[night] = "failed"
            logger.exception(f"{night}: ingestion failed")
        else:
            if result.skipped:
                results[night] = "skipped (too cloudy)"
            else:
                results[night] = f"{len(result.detection.alerts)} alerts"
                saved_new_night = True
        logger.info(f"{night}: {results[night]}")

    if not results:
        logger.info("Every night in the lookback window is already ingested.")
    if saved_new_night:
        refresh_baselines(db, coordinator, lookback)
    return results


def cli():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    days = int(sys.argv[1]) if len(sys.argv) > 1 else LOOKBACK_DAYS
    db = SessionLocal()
    try:
        run(db, utcnow().date(), days)
    finally:
        db.close()


if __name__ == "__main__":
    cli()
