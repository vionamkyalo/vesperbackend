import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from models.zone_baseline import MoonBand, ZoneBaseline


class TestZoneBaseline:
    def test_create_zone_baseline_happy_path(self, db_session, sample_zone):
        baseline = ZoneBaseline(
            zone_id=sample_zone.zone_id,
            moon_band=MoonBand.DARK,
            expected_light_index=Decimal("123.4567"),
            nights_used=8,
        )
        db_session.add(baseline)
        db_session.commit()
        db_session.refresh(baseline)

        assert baseline.baseline_id is not None
        assert isinstance(baseline.baseline_id, uuid.UUID)
        assert baseline.zone_id == sample_zone.zone_id
        assert baseline.moon_band == MoonBand.DARK
        assert baseline.expected_light_index == Decimal("123.4567")
        assert baseline.nights_used == 8
        assert baseline.calculated_at is not None

    @pytest.mark.parametrize(
        "moon_band",
        [
            MoonBand.DARK,
            MoonBand.PARTIAL,
            MoonBand.BRIGHT,
        ],
    )
    def test_zone_baseline_moon_band_values(self, db_session, sample_zone, moon_band):
        baseline = ZoneBaseline(
            zone_id=sample_zone.zone_id,
            moon_band=moon_band,
            expected_light_index=Decimal("50.0000"),
            nights_used=5,
        )
        db_session.add(baseline)
        db_session.commit()
        db_session.refresh(baseline)

        assert baseline.moon_band == moon_band

    def test_zone_baseline_missing_required_fields(self, db_session):
        baseline = ZoneBaseline()
        db_session.add(baseline)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_baseline_missing_zone_id(self, db_session):
        baseline = ZoneBaseline(
            moon_band=MoonBand.DARK,
            expected_light_index=Decimal("50.0000"),
            nights_used=5,
        )
        db_session.add(baseline)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_baseline_missing_moon_band(self, db_session, sample_zone):
        baseline = ZoneBaseline(
            zone_id=sample_zone.zone_id,
            expected_light_index=Decimal("50.0000"),
            nights_used=5,
        )
        db_session.add(baseline)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_baseline_unknown_zone(self, db_session):
        baseline = ZoneBaseline(
            zone_id=uuid.uuid4(),
            moon_band=MoonBand.DARK,
            expected_light_index=Decimal("50.0000"),
            nights_used=5,
        )
        db_session.add(baseline)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_baseline_unique_zone_and_moon_band(self, db_session, sample_zone):
        baseline1 = ZoneBaseline(
            zone_id=sample_zone.zone_id,
            moon_band=MoonBand.BRIGHT,
            expected_light_index=Decimal("50.0000"),
            nights_used=5,
        )
        db_session.add(baseline1)
        db_session.commit()

        baseline2 = ZoneBaseline(
            zone_id=sample_zone.zone_id,
            moon_band=MoonBand.BRIGHT,
            expected_light_index=Decimal("60.0000"),
            nights_used=6,
        )
        db_session.add(baseline2)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_zone_baseline_zone_relationship(
        self, db_session, sample_zone, sample_baseline
    ):
        db_session.refresh(sample_zone)

        assert sample_baseline.zone.zone_id == sample_zone.zone_id
        assert sample_baseline in sample_zone.baselines
