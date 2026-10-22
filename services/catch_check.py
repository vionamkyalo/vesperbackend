from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.catch_check import CatchCheck
from models.inspection import Inspection, InspectionType
from models.user import User, UserRole
from repositories.catch_check import catch_check_repository
from schemas.catch_check import CatchCheckCreate


class CatchCheckService:
    @staticmethod
    def _check_active_user(user: User) -> None:
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive users cannot access catch checks",
            )

    @staticmethod
    def _get_role_value(user: User) -> str:
        role = user.role
        return role.value if isinstance(role, UserRole) else str(role)

    def _check_officer(self, user: User) -> None:
        if self._get_role_value(user) != UserRole.PATROL_OFFICER.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only patrol officers can create catch checks",
            )

    @staticmethod
    def _check_future_time(checked_at: datetime) -> None:
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="checked_at must include a timezone",
            )

        now = datetime.now(timezone.utc)
        if checked_at.astimezone(timezone.utc) > now + timedelta(minutes=10):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="checked_at cannot be more than 10 minutes in the future",
            )

    @staticmethod
    def _calculate_catch_per_rig_night(
        catch_weight_kg: Decimal,
        rig_nights: int,
    ) -> Decimal:
        if rig_nights < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="rig_nights must be at least 1",
            )

        return (catch_weight_kg / Decimal(rig_nights)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    def get_inspection(
        self,
        db_session: Session,
        inspection_id: UUID,
    ) -> Inspection | None:
        return (
            db_session.query(Inspection)
            .filter(Inspection.inspection_id == inspection_id)
            .first()
        )

    def create_catch_check(
        self,
        db_session: Session,
        user: User,
        payload: CatchCheckCreate,
    ) -> CatchCheck:
        self._check_active_user(user)
        self._check_officer(user)
        self._check_future_time(payload.checked_at)

        # Repeated requests with the same catch ID are idempotent.
        existing = catch_check_repository.get(db_session, payload.catch_id)

        if existing is not None:
            if existing.inspection_id != payload.inspection_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="catch_id is already associated with another inspection",
                )

            existing_inspection = self.get_inspection(
                db_session,
                existing.inspection_id,
            )

            if (
                existing_inspection is None
                or existing_inspection.officer_id != user.user_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Catch check not found",
                )

            return existing

        inspection = self.get_inspection(
            db_session,
            payload.inspection_id,
        )

        if inspection is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inspection not found",
            )

        if inspection.officer_id != user.user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inspection not found",
            )

        if inspection.inspection_type != InspectionType.LANDING_SITE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Catch checks can only be created for landing-site inspections",
            )

        catch_per_rig_night = self._calculate_catch_per_rig_night(
            payload.catch_weight_kg,
            payload.rig_nights,
        )

        catch_check = CatchCheck(
            catch_id=payload.catch_id,
            inspection_id=payload.inspection_id,
            rig_identifier=payload.rig_identifier,
            rig_nights=payload.rig_nights,
            type_of_fish=payload.type_of_fish,
            catch_weight_kg=payload.catch_weight_kg,
            catch_per_rig_night=catch_per_rig_night,
            notes=payload.notes,
            checked_at=payload.checked_at,
        )

        try:
            return catch_check_repository.create(db_session, catch_check)
        except IntegrityError:
            # Another request saved the same catch_id first (offline retry race).
            db_session.rollback()
            existing = catch_check_repository.get(db_session, payload.catch_id)
            if existing is not None and existing.inspection_id == payload.inspection_id:
                return existing
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="catch_id is already in use",
            )

    def get_catch_check(
        self,
        db_session: Session,
        user: User,
        catch_id: UUID,
    ) -> CatchCheck:
        self._check_active_user(user)

        catch_check = catch_check_repository.get(db_session, catch_id)

        if catch_check is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Catch check not found",
            )

        if self._get_role_value(user) == UserRole.PATROL_COORDINATOR.value:
            return catch_check

        inspection = self.get_inspection(
            db_session,
            catch_check.inspection_id,
        )

        if inspection is None or inspection.officer_id != user.user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Catch check not found",
            )

        return catch_check

    def list_catch_checks(
        self,
        db_session: Session,
        user: User,
        inspection_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CatchCheck]:
        self._check_active_user(user)

        is_coordinator = self._get_role_value(user) == UserRole.PATROL_COORDINATOR.value

        return catch_check_repository.get_all(
            db_session,
            inspection_id=inspection_id,
            officer_id=None if is_coordinator else user.user_id,
            limit=limit,
            offset=offset,
        )


catch_check_service = CatchCheckService()
