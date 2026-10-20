import uuid
from decimal import Decimal
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core import security
from database import get_db
from models.user import User, UserRole
from models.zone import Zone, ZoneType
from models.zone_setting_history import ZoneSettingHistory
from repositories.zone_setting_history import zone_setting_history_repository
from schemas.zone_setting_history import ZoneSettingHistoryRead
from services.zone_setting_history import zone_setting_history_service


class TestZoneSettingHistory:
    def test_create_zone_setting_history_happy_path(
        self, db_session, sample_zone, sample_coordinator
    ):
        history = ZoneSettingHistory(
            zone_id=sample_zone.zone_id,
            radiance_threshold=Decimal("15.0000"),
            cluster_radius_m=Decimal("800.00"),
            min_cluster_points=4,
            confidence_threshold=Decimal("0.6000"),
            changed_by=sample_coordinator.user_id,
        )
        db_session.add(history)
        db_session.commit()
        db_session.refresh(history)

        assert history.history_id is not None
        assert isinstance(history.history_id, uuid.UUID)
        assert history.zone_id == sample_zone.zone_id
        assert history.radiance_threshold == Decimal("15.0000")
        assert history.cluster_radius_m == Decimal("800.00")
        assert history.min_cluster_points == 4
        assert history.confidence_threshold == Decimal("0.6000")
        assert history.changed_by == sample_coordinator.user_id
        assert history.changed_at is not None

    def test_zone_setting_history_missing_required_fields(self, db_session):
        history = ZoneSettingHistory()
        db_session.add(history)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_setting_history_missing_zone_id(self, db_session, sample_coordinator):
        history = ZoneSettingHistory(
            radiance_threshold=Decimal("15"),
            cluster_radius_m=Decimal("800"),
            min_cluster_points=4,
            confidence_threshold=Decimal("0.6"),
            changed_by=sample_coordinator.user_id,
        )
        db_session.add(history)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_setting_history_missing_changed_by(self, db_session, sample_zone):
        history = ZoneSettingHistory(
            zone_id=sample_zone.zone_id,
            radiance_threshold=Decimal("15"),
            cluster_radius_m=Decimal("800"),
            min_cluster_points=4,
            confidence_threshold=Decimal("0.6"),
        )
        db_session.add(history)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_setting_history_missing_confidence_threshold(
        self, db_session, sample_zone, sample_coordinator
    ):
        history = ZoneSettingHistory(
            zone_id=sample_zone.zone_id,
            radiance_threshold=Decimal("15"),
            cluster_radius_m=Decimal("800"),
            min_cluster_points=4,
            changed_by=sample_coordinator.user_id,
        )
        db_session.add(history)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_setting_history_zone_relationship(
        self, db_session, sample_zone, sample_coordinator
    ):
        history = ZoneSettingHistory(
            zone_id=sample_zone.zone_id,
            radiance_threshold=Decimal("15"),
            cluster_radius_m=Decimal("800"),
            min_cluster_points=4,
            confidence_threshold=Decimal("0.6"),
            changed_by=sample_coordinator.user_id,
        )
        db_session.add(history)
        db_session.commit()
        db_session.refresh(sample_zone)

        assert history.zone.zone_id == sample_zone.zone_id
        assert history in sample_zone.setting_history

    def test_zone_setting_history_changer_relationship(
        self, db_session, sample_zone, sample_coordinator
    ):
        history = ZoneSettingHistory(
            zone_id=sample_zone.zone_id,
            radiance_threshold=Decimal("15"),
            cluster_radius_m=Decimal("800"),
            min_cluster_points=4,
            confidence_threshold=Decimal("0.6"),
            changed_by=sample_coordinator.user_id,
        )
        db_session.add(history)
        db_session.commit()
        db_session.refresh(history)

        assert history.changer.user_id == sample_coordinator.user_id


HISTORY_API = "/api/v1/zone-setting-history"


def make_history(db_session, zone, user, minutes_ago=0, **changes):
    values = {
        "zone_id": zone.zone_id,
        "radiance_threshold": Decimal("12.5000"),
        "cluster_radius_m": Decimal("1000.00"),
        "min_cluster_points": 3,
        "confidence_threshold": Decimal("0.4000"),
        "changed_by": user.user_id,
        "changed_at": datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        - timedelta(minutes=minutes_ago),
    }
    values.update(changes)
    history = ZoneSettingHistory(**values)
    db_session.add(history)
    db_session.commit()
    db_session.refresh(history)
    return history


def make_other_zone(db_session, name="History Other Zone"):
    zone = Zone(
        name=name,
        basin="Sanyati",
        zone_type=ZoneType.FISHING_ZONE,
        boundary={"type": "Polygon", "coordinates": []},
        radiance_threshold=Decimal("10"),
        cluster_radius_m=Decimal("500"),
    )
    db_session.add(zone)
    db_session.commit()
    return zone


def history_stand_in_role_check(*roles):
    def checker(
        x_test_user: str | None = Header(default=None), db: Session = Depends(get_db)
    ):
        if x_test_user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        user = db.get(User, uuid.UUID(x_test_user))
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        if user.role not in roles:
            raise HTTPException(
                status_code=403, detail="You do not have permission to do this."
            )
        return user

    return checker


HISTORY_REAL_SECURITY = hasattr(security, "create_access_token") and hasattr(
    security, "require_any_user"
)

if not HISTORY_REAL_SECURITY:
    security.require_coordinator = history_stand_in_role_check(
        UserRole.PATROL_COORDINATOR
    )
    security.require_officer = history_stand_in_role_check(UserRole.PATROL_OFFICER)
    security.require_any_user = history_stand_in_role_check(
        UserRole.PATROL_COORDINATOR, UserRole.PATROL_OFFICER
    )


def history_headers(user):
    if HISTORY_REAL_SECURITY:
        token = security.create_access_token(user.user_id, user.role.value)
        return {"Authorization": f"Bearer {token}"}
    return {"X-Test-User": str(user.user_id)}


@pytest.fixture
def history_client(db_session):
    from routers import zone_setting_history as history_router

    app = FastAPI()
    if HISTORY_REAL_SECURITY:
        security.register_error_handlers(app)
    app.include_router(history_router.router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


class TestZoneSettingHistoryRepository:
    def test_create_saves_all_fields(self, db_session, sample_zone, sample_coordinator):
        history = ZoneSettingHistory(
            zone_id=sample_zone.zone_id,
            radiance_threshold=Decimal("12.5000"),
            cluster_radius_m=Decimal("1000.00"),
            min_cluster_points=3,
            confidence_threshold=Decimal("0.4000"),
            changed_by=sample_coordinator.user_id,
        )

        saved = zone_setting_history_repository.create(db_session, history)
        db_session.expire_all()
        found = zone_setting_history_repository.get(db_session, saved.history_id)

        assert found.zone_id == sample_zone.zone_id
        assert found.radiance_threshold == Decimal("12.5000")
        assert found.cluster_radius_m == Decimal("1000.00")
        assert found.min_cluster_points == 3
        assert found.confidence_threshold == Decimal("0.4000")
        assert found.changed_by == sample_coordinator.user_id

    def test_create_fills_id_and_time(
        self, db_session, sample_zone, sample_coordinator
    ):
        history = ZoneSettingHistory(
            zone_id=sample_zone.zone_id,
            radiance_threshold=Decimal("1"),
            cluster_radius_m=Decimal("1"),
            min_cluster_points=1,
            confidence_threshold=Decimal("0"),
            changed_by=sample_coordinator.user_id,
        )

        saved = zone_setting_history_repository.create(db_session, history)

        assert isinstance(saved.history_id, uuid.UUID)
        assert saved.changed_at is not None

    def test_create_returns_same_object(
        self, db_session, sample_zone, sample_coordinator
    ):
        history = ZoneSettingHistory(
            zone_id=sample_zone.zone_id,
            radiance_threshold=Decimal("1"),
            cluster_radius_m=Decimal("1"),
            min_cluster_points=1,
            confidence_threshold=Decimal("0"),
            changed_by=sample_coordinator.user_id,
        )

        assert zone_setting_history_repository.create(db_session, history) is history

    def test_get_found(self, db_session, sample_zone, sample_coordinator):
        history = make_history(db_session, sample_zone, sample_coordinator)

        assert (
            zone_setting_history_repository.get(
                db_session, history.history_id
            ).history_id
            == history.history_id
        )

    def test_get_unknown_id(self, db_session):
        assert zone_setting_history_repository.get(db_session, uuid.uuid4()) is None

    def test_get_all_empty(self, db_session):
        assert zone_setting_history_repository.get_all(db_session) == []

    @pytest.mark.parametrize("count", [1, 3, 5])
    def test_get_all_counts(self, db_session, sample_zone, sample_coordinator, count):
        for minutes in range(count):
            make_history(
                db_session, sample_zone, sample_coordinator, minutes_ago=minutes
            )

        assert len(zone_setting_history_repository.get_all(db_session)) == count

    def test_get_all_every_zone(self, db_session, sample_zone, sample_coordinator):
        other_zone = make_other_zone(db_session)
        make_history(db_session, sample_zone, sample_coordinator)
        make_history(db_session, other_zone, sample_coordinator)

        zones = {
            history.zone_id
            for history in zone_setting_history_repository.get_all(db_session)
        }

        assert zones == {sample_zone.zone_id, other_zone.zone_id}

    @pytest.mark.parametrize(
        "field",
        [
            "zone_id",
            "radiance_threshold",
            "cluster_radius_m",
            "min_cluster_points",
            "confidence_threshold",
            "changed_by",
        ],
    )
    def test_create_required_field_missing(
        self, db_session, sample_zone, sample_coordinator, field
    ):
        values = {
            "zone_id": sample_zone.zone_id,
            "radiance_threshold": Decimal("1"),
            "cluster_radius_m": Decimal("1"),
            "min_cluster_points": 1,
            "confidence_threshold": Decimal("0"),
            "changed_by": sample_coordinator.user_id,
        }
        values[field] = None

        with pytest.raises(IntegrityError):
            zone_setting_history_repository.create(
                db_session, ZoneSettingHistory(**values)
            )

        db_session.rollback()

    @pytest.mark.parametrize("missing_link", ["zone_id", "changed_by"])
    def test_create_unknown_link_rejected(
        self, db_session, sample_zone, sample_coordinator, missing_link
    ):
        values = {
            "zone_id": sample_zone.zone_id,
            "radiance_threshold": Decimal("1"),
            "cluster_radius_m": Decimal("1"),
            "min_cluster_points": 1,
            "confidence_threshold": Decimal("0"),
            "changed_by": sample_coordinator.user_id,
        }
        values[missing_link] = uuid.uuid4()

        with pytest.raises(IntegrityError):
            zone_setting_history_repository.create(
                db_session, ZoneSettingHistory(**values)
            )

        db_session.rollback()

    def test_create_duplicate_id_rejected(
        self, db_session, sample_zone, sample_coordinator
    ):
        first = make_history(db_session, sample_zone, sample_coordinator)
        db_session.expunge_all()
        copy = ZoneSettingHistory(
            history_id=first.history_id,
            zone_id=sample_zone.zone_id,
            radiance_threshold=Decimal("1"),
            cluster_radius_m=Decimal("1"),
            min_cluster_points=1,
            confidence_threshold=Decimal("0"),
            changed_by=sample_coordinator.user_id,
        )

        with pytest.raises(IntegrityError):
            zone_setting_history_repository.create(db_session, copy)

        db_session.rollback()

    @pytest.mark.parametrize(
        "field, value",
        [
            ("radiance_threshold", Decimal("999999.9999")),
            ("radiance_threshold", Decimal("0.0000")),
            ("cluster_radius_m", Decimal("50000.00")),
            ("confidence_threshold", Decimal("1.0000")),
            ("confidence_threshold", Decimal("0.0001")),
        ],
    )
    def test_create_keeps_decimal_values(
        self, db_session, sample_zone, sample_coordinator, field, value
    ):
        history = make_history(
            db_session, sample_zone, sample_coordinator, **{field: value}
        )
        db_session.expire_all()

        assert (
            getattr(
                zone_setting_history_repository.get(db_session, history.history_id),
                field,
            )
            == value
        )

    def test_repository_has_no_update(self):
        assert not hasattr(zone_setting_history_repository, "update")


class TestZoneSettingHistorySchema:
    def test_read_from_model(self, db_session, sample_zone, sample_coordinator):
        history = make_history(db_session, sample_zone, sample_coordinator)

        data = ZoneSettingHistoryRead.model_validate(history)

        assert data.history_id == history.history_id
        assert data.zone_id == sample_zone.zone_id
        assert data.changed_by == sample_coordinator.user_id
        assert data.min_cluster_points == 3

    def test_read_exact_fields(self, db_session, sample_zone, sample_coordinator):
        history = make_history(db_session, sample_zone, sample_coordinator)

        data = ZoneSettingHistoryRead.model_validate(history).model_dump(mode="json")

        assert set(data) == {
            "history_id",
            "zone_id",
            "radiance_threshold",
            "cluster_radius_m",
            "min_cluster_points",
            "confidence_threshold",
            "changed_by",
            "changed_at",
        }

    @pytest.mark.parametrize(
        "field, expected",
        [
            ("radiance_threshold", 12.5),
            ("cluster_radius_m", 1000.0),
            ("confidence_threshold", 0.4),
        ],
    )
    def test_read_decimals_sent_as_numbers(
        self, db_session, sample_zone, sample_coordinator, field, expected
    ):
        history = make_history(db_session, sample_zone, sample_coordinator)

        data = ZoneSettingHistoryRead.model_validate(history).model_dump(mode="json")

        assert isinstance(data[field], float)
        assert data[field] == expected

    def test_read_ids_sent_as_text(self, db_session, sample_zone, sample_coordinator):
        history = make_history(db_session, sample_zone, sample_coordinator)

        data = ZoneSettingHistoryRead.model_validate(history).model_dump(mode="json")

        assert data["history_id"] == str(history.history_id)
        assert data["zone_id"] == str(sample_zone.zone_id)

    def test_read_from_dict(self):
        data = ZoneSettingHistoryRead(
            history_id=uuid.uuid4(),
            zone_id=uuid.uuid4(),
            radiance_threshold="20.0000",
            cluster_radius_m="800.00",
            min_cluster_points=4,
            confidence_threshold="0.6000",
            changed_by=uuid.uuid4(),
            changed_at="2026-10-10T12:00:00Z",
        )

        assert data.radiance_threshold == Decimal("20.0000")
        assert data.changed_at.tzinfo is not None

    @pytest.mark.parametrize(
        "field",
        [
            "history_id",
            "zone_id",
            "radiance_threshold",
            "cluster_radius_m",
            "min_cluster_points",
            "confidence_threshold",
            "changed_by",
            "changed_at",
        ],
    )
    def test_read_missing_field_rejected(self, field):
        values = {
            "history_id": uuid.uuid4(),
            "zone_id": uuid.uuid4(),
            "radiance_threshold": "20.0000",
            "cluster_radius_m": "800.00",
            "min_cluster_points": 4,
            "confidence_threshold": "0.6000",
            "changed_by": uuid.uuid4(),
            "changed_at": "2026-10-10T12:00:00Z",
        }
        del values[field]

        with pytest.raises(ValidationError):
            ZoneSettingHistoryRead(**values)

    @pytest.mark.parametrize(
        "field, value",
        [
            ("history_id", "not-a-uuid"),
            ("radiance_threshold", "high"),
            ("min_cluster_points", "three"),
            ("min_cluster_points", 2.5),
            ("changed_at", "yesterday"),
        ],
    )
    def test_read_bad_values_rejected(self, field, value):
        values = {
            "history_id": uuid.uuid4(),
            "zone_id": uuid.uuid4(),
            "radiance_threshold": "20.0000",
            "cluster_radius_m": "800.00",
            "min_cluster_points": 4,
            "confidence_threshold": "0.6000",
            "changed_by": uuid.uuid4(),
            "changed_at": "2026-10-10T12:00:00Z",
        }
        values[field] = value

        with pytest.raises(ValidationError):
            ZoneSettingHistoryRead(**values)


class TestZoneSettingHistoryService:
    def test_list_all_as_coordinator(self, db_session, sample_zone, sample_coordinator):
        make_history(db_session, sample_zone, sample_coordinator)
        make_history(db_session, sample_zone, sample_coordinator, minutes_ago=5)

        assert (
            len(
                zone_setting_history_service.list_history(
                    db_session, sample_coordinator
                )
            )
            == 2
        )

    def test_list_empty(self, db_session, sample_coordinator):
        assert (
            zone_setting_history_service.list_history(db_session, sample_coordinator)
            == []
        )

    def test_list_newest_first(self, db_session, sample_zone, sample_coordinator):
        old = make_history(db_session, sample_zone, sample_coordinator, minutes_ago=60)
        new = make_history(db_session, sample_zone, sample_coordinator, minutes_ago=1)

        results = zone_setting_history_service.list_history(
            db_session, sample_coordinator
        )

        assert [history.history_id for history in results] == [
            new.history_id,
            old.history_id,
        ]

    def test_list_filter_by_zone(self, db_session, sample_zone, sample_coordinator):
        other_zone = make_other_zone(db_session)
        mine = make_history(db_session, sample_zone, sample_coordinator)
        make_history(db_session, other_zone, sample_coordinator)

        results = zone_setting_history_service.list_history(
            db_session, sample_coordinator, zone_id=sample_zone.zone_id
        )

        assert [history.history_id for history in results] == [mine.history_id]

    def test_list_zone_without_history(
        self, db_session, sample_zone, sample_coordinator
    ):
        other_zone = make_other_zone(db_session)
        make_history(db_session, sample_zone, sample_coordinator)

        assert (
            zone_setting_history_service.list_history(
                db_session, sample_coordinator, zone_id=other_zone.zone_id
            )
            == []
        )

    def test_list_unknown_zone(self, db_session, sample_coordinator):
        with pytest.raises(HTTPException) as error:
            zone_setting_history_service.list_history(
                db_session, sample_coordinator, zone_id=uuid.uuid4()
            )

        assert error.value.status_code == 404

    def test_list_filter_by_changed_by(
        self, db_session, sample_zone, sample_coordinator, sample_officer
    ):
        mine = make_history(db_session, sample_zone, sample_coordinator)
        make_history(db_session, sample_zone, sample_officer)

        results = zone_setting_history_service.list_history(
            db_session, sample_coordinator, changed_by=sample_coordinator.user_id
        )

        assert [history.history_id for history in results] == [mine.history_id]

    def test_list_filter_by_unknown_person(
        self, db_session, sample_zone, sample_coordinator
    ):
        make_history(db_session, sample_zone, sample_coordinator)

        assert (
            zone_setting_history_service.list_history(
                db_session, sample_coordinator, changed_by=uuid.uuid4()
            )
            == []
        )

    def test_list_zone_and_person_together(
        self, db_session, sample_zone, sample_coordinator, sample_officer
    ):
        other_zone = make_other_zone(db_session)
        wanted = make_history(db_session, sample_zone, sample_coordinator)
        make_history(db_session, sample_zone, sample_officer)
        make_history(db_session, other_zone, sample_coordinator)

        results = zone_setting_history_service.list_history(
            db_session,
            sample_coordinator,
            zone_id=sample_zone.zone_id,
            changed_by=sample_coordinator.user_id,
        )

        assert [history.history_id for history in results] == [wanted.history_id]

    @pytest.mark.parametrize(
        "limit, offset, expected",
        [(1, 0, 1), (2, 0, 2), (50, 0, 3), (2, 2, 1), (10, 3, 0)],
    )
    def test_list_paging(
        self, db_session, sample_zone, sample_coordinator, limit, offset, expected
    ):
        for minutes in range(3):
            make_history(
                db_session, sample_zone, sample_coordinator, minutes_ago=minutes
            )

        results = zone_setting_history_service.list_history(
            db_session, sample_coordinator, limit=limit, offset=offset
        )

        assert len(results) == expected

    def test_list_officer_refused(self, db_session, sample_officer):
        with pytest.raises(HTTPException) as error:
            zone_setting_history_service.list_history(db_session, sample_officer)

        assert error.value.status_code == 403

    def test_list_inactive_coordinator_refused(self, db_session, sample_coordinator):
        sample_coordinator.is_active = False

        with pytest.raises(HTTPException) as error:
            zone_setting_history_service.list_history(db_session, sample_coordinator)

        assert error.value.status_code == 403

    def test_list_without_user_refused(self, db_session):
        with pytest.raises(HTTPException) as error:
            zone_setting_history_service.list_history(db_session, None)

        assert error.value.status_code == 403

    def test_get_found(self, db_session, sample_zone, sample_coordinator):
        history = make_history(db_session, sample_zone, sample_coordinator)

        result = zone_setting_history_service.get_history(
            db_session, sample_coordinator, history.history_id
        )

        assert result.history_id == history.history_id

    def test_get_not_found(self, db_session, sample_coordinator):
        with pytest.raises(HTTPException) as error:
            zone_setting_history_service.get_history(
                db_session, sample_coordinator, uuid.uuid4()
            )

        assert error.value.status_code == 404

    def test_get_officer_refused(
        self, db_session, sample_zone, sample_coordinator, sample_officer
    ):
        history = make_history(db_session, sample_zone, sample_coordinator)

        with pytest.raises(HTTPException) as error:
            zone_setting_history_service.get_history(
                db_session, sample_officer, history.history_id
            )

        assert error.value.status_code == 403

    def test_get_inactive_coordinator_refused(
        self, db_session, sample_zone, sample_coordinator
    ):
        history = make_history(db_session, sample_zone, sample_coordinator)
        sample_coordinator.is_active = False

        with pytest.raises(HTTPException) as error:
            zone_setting_history_service.get_history(
                db_session, sample_coordinator, history.history_id
            )

        assert error.value.status_code == 403

    def test_get_without_user_refused(self, db_session):
        with pytest.raises(HTTPException) as error:
            zone_setting_history_service.get_history(db_session, None, uuid.uuid4())

        assert error.value.status_code == 403

    def test_officer_refused_before_not_found(self, db_session, sample_officer):
        # An officer must not learn whether an ID exists
        with pytest.raises(HTTPException) as error:
            zone_setting_history_service.get_history(
                db_session, sample_officer, uuid.uuid4()
            )

        assert error.value.status_code == 403


class TestZoneSettingHistoryRouter:
    def test_list_as_coordinator(
        self, history_client, db_session, sample_zone, sample_coordinator
    ):
        history = make_history(db_session, sample_zone, sample_coordinator)

        response = history_client.get(
            HISTORY_API, headers=history_headers(sample_coordinator)
        )

        assert response.status_code == 200
        assert [item["history_id"] for item in response.json()] == [
            str(history.history_id)
        ]

    def test_list_empty(self, history_client, sample_coordinator):
        response = history_client.get(
            HISTORY_API, headers=history_headers(sample_coordinator)
        )

        assert response.status_code == 200
        assert response.json() == []

    def test_list_response_fields(
        self, history_client, db_session, sample_zone, sample_coordinator
    ):
        make_history(db_session, sample_zone, sample_coordinator)

        item = history_client.get(
            HISTORY_API, headers=history_headers(sample_coordinator)
        ).json()[0]

        assert item["radiance_threshold"] == 12.5
        assert item["cluster_radius_m"] == 1000.0
        assert item["min_cluster_points"] == 3
        assert item["confidence_threshold"] == 0.4
        assert item["changed_by"] == str(sample_coordinator.user_id)

    def test_list_filter_by_zone(
        self, history_client, db_session, sample_zone, sample_coordinator
    ):
        other_zone = make_other_zone(db_session)
        make_history(db_session, sample_zone, sample_coordinator)
        make_history(db_session, other_zone, sample_coordinator)

        response = history_client.get(
            HISTORY_API,
            params={"zone_id": str(other_zone.zone_id)},
            headers=history_headers(sample_coordinator),
        )

        assert [item["zone_id"] for item in response.json()] == [
            str(other_zone.zone_id)
        ]

    def test_list_filter_by_changed_by(
        self,
        history_client,
        db_session,
        sample_zone,
        sample_coordinator,
        sample_officer,
    ):
        make_history(db_session, sample_zone, sample_coordinator)
        make_history(db_session, sample_zone, sample_officer)

        response = history_client.get(
            HISTORY_API,
            params={"changed_by": str(sample_officer.user_id)},
            headers=history_headers(sample_coordinator),
        )

        assert [item["changed_by"] for item in response.json()] == [
            str(sample_officer.user_id)
        ]

    def test_list_unknown_zone(self, history_client, sample_coordinator):
        response = history_client.get(
            HISTORY_API,
            params={"zone_id": str(uuid.uuid4())},
            headers=history_headers(sample_coordinator),
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "params, expected",
        [
            ({"limit": 1}, 1),
            ({"limit": 200}, 2),
            ({"offset": 1}, 1),
            ({"offset": 2}, 0),
        ],
    )
    def test_list_paging(
        self,
        history_client,
        db_session,
        sample_zone,
        sample_coordinator,
        params,
        expected,
    ):
        make_history(db_session, sample_zone, sample_coordinator)
        make_history(db_session, sample_zone, sample_coordinator, minutes_ago=5)

        response = history_client.get(
            HISTORY_API, params=params, headers=history_headers(sample_coordinator)
        )

        assert response.status_code == 200
        assert len(response.json()) == expected

    @pytest.mark.parametrize(
        "params",
        [
            {"limit": 0},
            {"limit": 201},
            {"offset": -1},
            {"limit": "ten"},
            {"zone_id": "zone-1"},
            {"changed_by": "rudo"},
        ],
    )
    def test_list_bad_query(self, history_client, sample_coordinator, params):
        response = history_client.get(
            HISTORY_API, params=params, headers=history_headers(sample_coordinator)
        )

        assert response.status_code == 422

    def test_list_officer_forbidden(self, history_client, sample_officer):
        assert (
            history_client.get(
                HISTORY_API, headers=history_headers(sample_officer)
            ).status_code
            == 403
        )

    def test_list_requires_login(self, history_client):
        assert history_client.get(HISTORY_API).status_code == 401

    def test_list_inactive_coordinator(
        self, history_client, db_session, sample_coordinator
    ):
        headers = history_headers(sample_coordinator)
        sample_coordinator.is_active = False
        db_session.commit()

        assert history_client.get(HISTORY_API, headers=headers).status_code == 401

    def test_get_one(self, history_client, db_session, sample_zone, sample_coordinator):
        history = make_history(db_session, sample_zone, sample_coordinator)

        response = history_client.get(
            f"{HISTORY_API}/{history.history_id}",
            headers=history_headers(sample_coordinator),
        )

        assert response.status_code == 200
        assert response.json()["history_id"] == str(history.history_id)
        assert response.json()["zone_id"] == str(sample_zone.zone_id)

    def test_get_not_found(self, history_client, sample_coordinator):
        response = history_client.get(
            f"{HISTORY_API}/{uuid.uuid4()}", headers=history_headers(sample_coordinator)
        )

        assert response.status_code == 404

    def test_get_bad_id(self, history_client, sample_coordinator):
        response = history_client.get(
            f"{HISTORY_API}/not-a-uuid", headers=history_headers(sample_coordinator)
        )

        assert response.status_code == 422

    def test_get_officer_forbidden(
        self,
        history_client,
        db_session,
        sample_zone,
        sample_coordinator,
        sample_officer,
    ):
        history = make_history(db_session, sample_zone, sample_coordinator)

        response = history_client.get(
            f"{HISTORY_API}/{history.history_id}",
            headers=history_headers(sample_officer),
        )

        assert response.status_code == 403

    def test_get_requires_login(
        self, history_client, db_session, sample_zone, sample_coordinator
    ):
        history = make_history(db_session, sample_zone, sample_coordinator)

        assert (
            history_client.get(f"{HISTORY_API}/{history.history_id}").status_code == 401
        )

    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_list_cannot_be_changed(self, history_client, sample_coordinator, method):
        response = getattr(history_client, method)(
            HISTORY_API, headers=history_headers(sample_coordinator)
        )

        assert response.status_code == 405

    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_entry_cannot_be_changed(
        self, history_client, db_session, sample_zone, sample_coordinator, method
    ):
        history = make_history(db_session, sample_zone, sample_coordinator)

        response = getattr(history_client, method)(
            f"{HISTORY_API}/{history.history_id}",
            headers=history_headers(sample_coordinator),
        )

        assert response.status_code == 405
