import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from models.user import User, UserRole

PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$dGVzdHNhbHQ$dGVzdGhhc2g"


class TestUser:
    def test_create_user_happy_path(self, db_session):
        user = User(
            first_name="Rudo",
            last_name="Chikwanha",
            phone_number="+263771999999",
            email="rudo.c@example.org",
            password_hash=PASSWORD_HASH,
            role=UserRole.PATROL_COORDINATOR,
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.user_id is not None
        assert isinstance(user.user_id, uuid.UUID)
        assert user.first_name == "Rudo"
        assert user.last_name == "Chikwanha"
        assert user.phone_number == "+263771999999"
        assert user.email == "rudo.c@example.org"
        assert user.password_hash == PASSWORD_HASH
        assert user.role == UserRole.PATROL_COORDINATOR
        assert user.is_active is True
        assert user.created_at is not None
        assert user.updated_at is not None

    def test_user_default_fields(self, db_session):
        user = User(
            first_name="Tendai",
            last_name="Moyo",
            phone_number="+263771999998",
            email="tendai.m@example.org",
            password_hash=PASSWORD_HASH,
            role=UserRole.PATROL_OFFICER,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.is_active is True
        assert user.created_at is not None
        assert user.updated_at is not None
        assert user.created_at.tzinfo is not None

    @pytest.mark.parametrize(
        "role",
        [
            UserRole.PATROL_COORDINATOR,
            UserRole.PATROL_OFFICER,
        ],
    )
    def test_user_role_values(self, db_session, role):
        user = User(
            first_name="Test",
            last_name="User",
            phone_number="+263770000123",
            email="role.test@example.org",
            password_hash=PASSWORD_HASH,
            role=role,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.role == role

    def test_user_missing_required_fields(self, db_session):
        user = User()
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_user_missing_email(self, db_session):
        user = User(
            first_name="Test",
            last_name="User",
            phone_number="+263770000124",
            password_hash=PASSWORD_HASH,
            role=UserRole.PATROL_OFFICER,
        )
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_user_missing_phone_number(self, db_session):
        user = User(
            first_name="Test",
            last_name="User",
            email="no.phone@example.org",
            password_hash=PASSWORD_HASH,
            role=UserRole.PATROL_OFFICER,
        )
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_user_missing_password_hash(self, db_session):
        user = User(
            first_name="Test",
            last_name="User",
            phone_number="+263770000125",
            email="no.password@example.org",
            role=UserRole.PATROL_OFFICER,
        )
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_user_missing_role(self, db_session):
        user = User(
            first_name="Test",
            last_name="User",
            phone_number="+263770000126",
            email="no.role@example.org",
            password_hash=PASSWORD_HASH,
        )
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_user_unique_email(self, db_session, sample_officer):
        user = User(
            first_name="Other",
            last_name="Officer",
            phone_number="+263770000999",
            email=sample_officer.email,
            password_hash=PASSWORD_HASH,
            role=UserRole.PATROL_OFFICER,
        )
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_user_unique_phone_number(self, db_session, sample_officer):
        user = User(
            first_name="Other",
            last_name="Officer",
            phone_number=sample_officer.phone_number,
            email="other.officer@example.org",
            password_hash=PASSWORD_HASH,
            role=UserRole.PATROL_OFFICER,
        )
        db_session.add(user)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_user_inspections_relationship(
        self, db_session, sample_officer, sample_inspection
    ):
        db_session.refresh(sample_officer)

        assert sample_inspection.officer.user_id == sample_officer.user_id
        assert sample_inspection in sample_officer.inspections

    def test_user_assignments_relationship(
        self, db_session, sample_officer, sample_assignment
    ):
        db_session.refresh(sample_officer)

        assert sample_assignment.officer.user_id == sample_officer.user_id
        assert sample_assignment in sample_officer.assignments

    def test_user_locations_relationship(
        self, db_session, sample_officer, sample_location
    ):
        db_session.refresh(sample_officer)

        assert sample_location.officer.user_id == sample_officer.user_id
        assert sample_location in sample_officer.locations
