import json
import logging
import uuid
from pathlib import Path

from fastapi import HTTPException, status
from shapely.geometry import shape
from sqlalchemy.orm import Session

from database import utcnow
from models.user import User, UserRole
from models.zone import Zone
from models.zone_setting_history import ZoneSettingHistory
from repositories.zone import zone_repository
from schemas.zone import ZoneSettings, ZoneUpdate

logger = logging.getLogger(__name__)

REQUIRED_UPDATE_FIELDS = ["name", "basin", "zone_type", "is_active"]
OPTIONAL_UPDATE_FIELDS = ["boat_cap", "closure_start", "closure_end"]

BASINS_FILE = Path(__file__).resolve().parent.parent / "seeds" / "kariba_basins.json"


def load_basins():
    with open(BASINS_FILE, encoding="utf-8") as basins_file:
        return json.load(basins_file)["basins"]


class ZoneService:
    def check_active(self, current_user: User):
        if current_user is None or not current_user.is_active:
            logger.warning("zone access refused: inactive or unknown user")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not active.",
            )

    def check_coordinator(self, current_user: User):
        self.check_active(current_user)

        if current_user.role != UserRole.PATROL_COORDINATOR:
            logger.warning(
                f"zone action refused: user {current_user.user_id} is not the coordinator"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the patrol coordinator can do this.",
            )

    def is_closed_on(self, zone: Zone, day):
        if zone.closure_start is None:
            return False

        end = zone.closure_end or zone.closure_start
        return zone.closure_start <= day <= end

    def check_closure_dates(self, zone: Zone):
        if zone.closure_end is not None and zone.closure_start is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="closure_end needs closure_start.",
            )

        if zone.closure_start is not None and zone.closure_end is not None:
            if zone.closure_end < zone.closure_start:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="closure_end must be on or after closure_start.",
                )

    def clear_rule_confirmation(self, zone: Zone):
        zone.rules_confirmed_at = None
        zone.rules_confirmed_by = None

    def record_settings(self, db: Session, zone: Zone, current_user: User):
        history = ZoneSettingHistory(
            zone_id=zone.zone_id,
            radiance_threshold=zone.radiance_threshold,
            cluster_radius_m=zone.cluster_radius_m,
            min_cluster_points=zone.min_cluster_points,
            confidence_threshold=zone.confidence_threshold,
            changed_by=current_user.user_id,
        )
        db.add(history)

    def basin_shape(self, basin):
        for item in load_basins():
            if item["name"] == basin:
                return shape(item["boundary"])

        names = ", ".join(item["name"] for item in load_basins())
        logger.warning(f"zone refused: unknown basin {basin}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown basin. Choose one of: {names}.",
        )

    def check_boundary(self, db: Session, basin, boundary, zone_id=None):
        zone = shape(boundary)

        if not zone.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The zone boundary crosses itself.",
            )

        if not zone.within(self.basin_shape(basin)):
            logger.warning(f"zone refused: boundary is outside the {basin} basin")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The zone must be inside the {basin} basin.",
            )

        for other in db.query(Zone).all():
            if other.zone_id == zone_id:
                continue
            if zone.intersection(shape(other.boundary)).area > 0:
                logger.warning(f"zone refused: boundary overlaps zone {other.zone_id}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"The zone overlaps {other.name}.",
                )

    def list_basins(self, current_user: User):
        self.check_active(current_user)
        return load_basins()

    def check_name_free(self, db: Session, name, zone_id=None):
        existing = db.query(Zone).filter(Zone.name == name).first()

        if existing is not None and existing.zone_id != zone_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A zone with this name already exists.",
            )

    def get_zone(self, db: Session, current_user: User, zone_id: uuid.UUID):
        self.check_active(current_user)
        zone = zone_repository.get(db, zone_id)

        if zone is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Zone was not found."
            )

        return zone

    def list_zones(self, db: Session, current_user: User, active_only=False):
        self.check_active(current_user)

        query = db.query(Zone)

        if active_only:
            query = query.filter(Zone.is_active.is_(True))

        return query.order_by(Zone.name).all()

    def update_zone(
        self, db: Session, current_user: User, zone_id: uuid.UUID, data: ZoneUpdate
    ):
        self.check_coordinator(current_user)
        zone = self.get_zone(db, current_user, zone_id)
        changes = data.model_dump(exclude_unset=True)

        if changes.get("name") is not None:
            self.check_name_free(db, changes["name"], zone.zone_id)

        if changes.get("basin") is not None or changes.get("boundary") is not None:
            boundary = (
                data.boundary.model_dump()
                if changes.get("boundary") is not None
                else zone.boundary
            )
            self.check_boundary(
                db, changes.get("basin") or zone.basin, boundary, zone.zone_id
            )

        for field in REQUIRED_UPDATE_FIELDS:
            if field not in changes:
                continue
            if changes[field] is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{field} cannot be empty.",
                )
            setattr(zone, field, changes[field])

        for field in OPTIONAL_UPDATE_FIELDS:
            if field in changes:
                setattr(zone, field, changes[field])

        self.check_closure_dates(zone)

        if changes.get("boundary") is not None:
            zone.boundary = data.boundary.model_dump()
            self.clear_rule_confirmation(zone)

        zone.updated_by = current_user.user_id
        zone = zone_repository.update(db, zone)

        logger.info(
            f"zone {zone.zone_id} updated by {current_user.user_id}: {sorted(changes)}"
        )
        return zone

    def update_settings(
        self, db: Session, current_user: User, zone_id: uuid.UUID, data: ZoneSettings
    ):
        self.check_coordinator(current_user)
        zone = self.get_zone(db, current_user, zone_id)

        zone.radiance_threshold = data.radiance_threshold
        zone.cluster_radius_m = data.cluster_radius_m
        zone.min_cluster_points = data.min_cluster_points
        zone.confidence_threshold = data.confidence_threshold
        zone.updated_by = current_user.user_id
        self.clear_rule_confirmation(zone)

        self.record_settings(db, zone, current_user)
        zone = zone_repository.update(db, zone)

        logger.info(
            f"zone {zone.zone_id} detection settings changed by {current_user.user_id}"
        )
        return zone

    def confirm_rules(self, db: Session, current_user: User, zone_id: uuid.UUID):
        self.check_coordinator(current_user)
        zone = self.get_zone(db, current_user, zone_id)

        zone.rules_confirmed_by = current_user.user_id
        zone.rules_confirmed_at = utcnow()
        zone = zone_repository.update(db, zone)

        logger.info(f"zone {zone.zone_id} rules confirmed by {current_user.user_id}")
        return zone


zone_service = ZoneService()
