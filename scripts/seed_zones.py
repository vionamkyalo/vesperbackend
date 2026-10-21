import argparse
import importlib
import json
import logging
from decimal import Decimal
from pathlib import Path

from database import SessionLocal
from models.zone import Zone, ZoneType

for model in [
    "alert",
    "alert_assignment",
    "catch_check",
    "inspection",
    "officer_location",
    "user",
    "violation_report",
    "zone_baseline",
    "zone_light_reading",
    "zone_setting_history",
]:
    try:
        importlib.import_module(f"models.{model}")
    except ModuleNotFoundError:
        pass

logger = logging.getLogger(__name__)

SEED_FILE = Path(__file__).resolve().parent.parent / "seeds" / "kariba_zones.json"


def load_seed(path=SEED_FILE):
    with open(path, encoding="utf-8") as seed_file:
        return json.load(seed_file)


def seed_zones(db, seed=None):
    seed = seed or load_seed()
    defaults = seed["defaults"]
    existing = {name for (name,) in db.query(Zone.name).all()}
    created = []

    for item in seed["zones"]:
        if item["name"] in existing:
            continue

        zone = Zone(
            name=item["name"],
            basin=item["basin"],
            zone_type=ZoneType(item.get("zone_type", defaults["zone_type"])),
            boundary=item["boundary"],
            radiance_threshold=Decimal(defaults["radiance_threshold"]),
            cluster_radius_m=Decimal(defaults["cluster_radius_m"]),
            min_cluster_points=defaults["min_cluster_points"],
            confidence_threshold=Decimal(defaults["confidence_threshold"]),
            is_active=False,
        )
        db.add(zone)
        created.append(zone)

    db.commit()
    return created


def update_boundaries(db, seed=None):
    seed = seed or load_seed()
    zones = {zone.name: zone for zone in db.query(Zone).all()}
    updated = []

    for item in seed["zones"]:
        zone = zones.get(item["name"])
        if zone is None or zone.boundary == item["boundary"]:
            continue

        zone.boundary = item["boundary"]
        zone.basin = item["basin"]
        zone.rules_confirmed_at = None
        zone.rules_confirmed_by = None
        updated.append(zone)

    db.commit()
    return updated


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Load the mapped zones into the database."
    )
    parser.add_argument("path", nargs="?", default=str(SEED_FILE))
    parser.add_argument(
        "--update",
        action="store_true",
        help="Also replace the boundaries of zones already saved",
    )
    args = parser.parse_args()

    path = Path(args.path)
    seed = load_seed(path)
    db = SessionLocal()
    try:
        created = seed_zones(db, seed)
        logger.info(f"Seeded {len(created)} zone(s) from {path.name}")
        for zone in created:
            logger.info(f"  {zone.name} ({zone.basin})")

        if args.update:
            updated = update_boundaries(db, seed)
            logger.info(f"Updated the boundary of {len(updated)} zone(s)")
            for zone in updated:
                logger.info(f"  {zone.name} ({zone.basin})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
