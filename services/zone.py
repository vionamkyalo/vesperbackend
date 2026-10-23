import json
import logging
import os
import uuid
from urllib.request import urlopen

from dotenv import load_dotenv
from fastapi import HTTPException, UploadFile, status
from pydantic import ValidationError
from shapely.geometry import shape
from sqlalchemy.orm import Session

from database import utcnow
from models.user import User, UserRole
from models.zone import Zone
from models.zone_setting_history import ZoneSettingHistory
from repositories.zone import zone_repository
from schemas.zone import BasinSource, ZoneSettings, ZoneSource, ZoneUpdate

load_dotenv()

logger = logging.getLogger(__name__)

REQUIRED_UPDATE_FIELDS = ["name", "basin", "zone_type", "is_active"]
OPTIONAL_UPDATE_FIELDS = ["boat_cap", "closure_start", "closure_end"]

SOURCE_TIMEOUT_SECONDS = 15
MAX_ZONE_FILE_BYTES = 1_000_000
JSON_CONTENT_TYPES = {"application/json", "text/json"}
MAX_POLYGON_POSITIONS = 2000


def read_source(variable):
    location = os.environ.get(variable)

    if not location:
        logger.error(f"{variable} is not set")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{variable} is not set. Point it at the file or URL with the data.",
        )

    try:
        if location.startswith(("http://", "https://")):
            with urlopen(location, timeout=SOURCE_TIMEOUT_SECONDS) as response:
                return json.load(response)

        with open(location, encoding="utf-8") as source_file:
            return json.load(source_file)
    except (OSError, ValueError) as error:
        logger.error(f"could not read {variable} from {location}: {error}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not read the data in {variable}.",
        )


def load_source(variable, schema):
    try:
        return schema.model_validate(read_source(variable))
    except ValidationError as error:
        logger.error(f"{variable} is not in the expected format: {error}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"The data in {variable} is not in the expected format.",
        )


def polygon_problem(boundary):
    total = 0
    for ring in boundary["coordinates"]:
        if len(ring) < 4:
            return "Each ring of the boundary needs at least 4 positions."
        if ring[0] != ring[-1]:
            return "Each ring of the boundary must end where it starts."
        for position in ring:
            if len(position) != 2:
                return "Boundary positions must be [longitude, latitude]."
            longitude, latitude = position
            if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
                return "A boundary position is outside valid longitude or latitude."
        total += len(ring)

    if total > MAX_POLYGON_POSITIONS:
        return f"The boundary has more than {MAX_POLYGON_POSITIONS} positions."
    return None


def load_basins():
    basins = [
        basin.model_dump() for basin in load_source("BASINS_SOURCE", BasinSource).basins
    ]
    for basin in basins:
        problem = polygon_problem(basin["boundary"])
        if problem is not None:
            logger.error(f"BASINS_SOURCE basin {basin['name']} is invalid: {problem}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The data in BASINS_SOURCE is not in the expected format.",
            )
    return basins


def load_zones():
    return load_source("ZONES_SOURCE", ZoneSource)


def check_json_upload(filename, content_type):
    media_type = (content_type or "").split(";")[0].strip().lower()
    if (
        not (filename or "").lower().endswith(".json")
        or media_type not in JSON_CONTENT_TYPES
    ):
        logger.warning(
            f"zone import refused: upload {filename} with type {content_type} is not JSON"
        )
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload the zones as a .json file.",
        )


def read_zone_upload(upload: UploadFile):
    check_json_upload(upload.filename, upload.content_type)
    return parse_zone_file(upload.file.read(MAX_ZONE_FILE_BYTES + 1))


def parse_zone_file(content):
    if len(content) > MAX_ZONE_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The zones file is too large.",
        )

    try:
        data = json.loads(content)
    except ValueError:
        logger.warning("zone import refused: uploaded file is not JSON")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is not valid JSON.",
        )

    try:
        return ZoneSource.model_validate(data)
    except ValidationError as error:
        logger.warning(
            f"zone import refused: uploaded file has the wrong format: {error}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is not in the expected zones format.",
        )


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

    def basin_shape(self, basin, basins=None):
        basins = basins or load_basins()

        for item in basins:
            if item["name"] == basin:
                return shape(item["boundary"])

        names = ", ".join(item["name"] for item in basins)
        logger.warning(f"zone refused: unknown basin {basin}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown basin. Choose one of: {names}.",
        )

    def check_boundary(self, db: Session, basin, boundary, zone_id=None, basins=None):
        problem = polygon_problem(boundary)
        if problem is not None:
            logger.warning(f"zone refused: {problem}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem)

        zone = shape(boundary)

        if not zone.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The zone boundary crosses itself.",
            )

        if not zone.within(self.basin_shape(basin, basins)):
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

    def check_import_overlaps(self, items):
        shapes = [(item.name, shape(item.boundary.model_dump())) for item in items]

        for index, (name, boundary) in enumerate(shapes):
            for other_name, other in shapes[index + 1 :]:
                if boundary.intersection(other).area > 0:
                    logger.warning(f"zone import refused: {name} overlaps {other_name}")
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"{name} overlaps {other_name} in ZONES_SOURCE.",
                    )

    def import_zones(
        self, db: Session, current_user: User, upload: UploadFile | None = None
    ):
        self.check_coordinator(current_user)
        data = read_zone_upload(upload) if upload is not None else load_zones()
        basins = load_basins()
        existing = {name for (name,) in db.query(Zone.name).all()}
        new_items = [item for item in data.zones if item.name not in existing]

        for item in new_items:
            try:
                self.check_boundary(
                    db, item.basin, item.boundary.model_dump(), basins=basins
                )
            except HTTPException as error:
                raise HTTPException(
                    status_code=error.status_code,
                    detail=f"{item.name}: {error.detail}",
                )
        self.check_import_overlaps(new_items)

        defaults = data.defaults
        created = []
        for item in new_items:
            zone = Zone(
                name=item.name,
                basin=item.basin,
                zone_type=item.zone_type or defaults.zone_type,
                boundary=item.boundary.model_dump(),
                radiance_threshold=defaults.radiance_threshold,
                cluster_radius_m=defaults.cluster_radius_m,
                min_cluster_points=defaults.min_cluster_points,
                confidence_threshold=defaults.confidence_threshold,
                is_active=False,
                updated_by=current_user.user_id,
            )
            created.append(zone_repository.create(db, zone))

        logger.info(
            f"{len(created)} zone(s) imported by {current_user.user_id}, "
            f"{len(data.zones) - len(created)} already saved"
        )
        return created

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
