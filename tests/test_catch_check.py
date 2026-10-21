import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from models.catch_check import CatchCheck


class TestCatchCheck:
    def test_create_catch_check_happy_path(self, db_session, landing_inspection):
        catch_id = uuid.uuid4()
        checked_at = datetime(2026, 10, 11, 6, 0, tzinfo=timezone.utc)
        check = CatchCheck(
            catch_id=catch_id,
            inspection_id=landing_inspection.inspection_id,
            rig_identifier="KR-3000",
            rig_nights=2,
            catch_weight_kg=Decimal("301.00"),
            checked_at=checked_at,
        )
        db_session.add(check)
        db_session.commit()
        db_session.refresh(check)

        assert check.catch_id == catch_id
        assert isinstance(check.catch_id, uuid.UUID)
        assert check.inspection_id == landing_inspection.inspection_id
        assert check.rig_identifier == "KR-3000"
        assert check.rig_nights == 2
        assert check.catch_weight_kg == Decimal("301.00")
        assert check.checked_at == checked_at
        assert check.synced_at is not None

    def test_catch_check_missing_required_fields(self, db_session):
        check = CatchCheck(catch_id=uuid.uuid4())
        db_session.add(check)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_catch_check_missing_inspection_id(self, db_session):
        check = CatchCheck(
            catch_id=uuid.uuid4(),
            rig_identifier="KR-3001",
            rig_nights=2,
            catch_weight_kg=Decimal("100.00"),
            checked_at=datetime(2026, 10, 11, 6, 0, tzinfo=timezone.utc),
        )
        db_session.add(check)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_catch_check_missing_catch_weight(self, db_session, landing_inspection):
        check = CatchCheck(
            catch_id=uuid.uuid4(),
            inspection_id=landing_inspection.inspection_id,
            rig_identifier="KR-3002",
            rig_nights=2,
            checked_at=datetime(2026, 10, 11, 6, 0, tzinfo=timezone.utc),
        )
        db_session.add(check)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_catch_check_inspection_relationship(
        self, db_session, landing_inspection, sample_catch_check
    ):
        db_session.refresh(landing_inspection)

        assert (
            sample_catch_check.inspection.inspection_id
            == landing_inspection.inspection_id
        )
        assert sample_catch_check in landing_inspection.catch_checks
