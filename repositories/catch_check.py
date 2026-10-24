from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session
from models.inspection import Inspection
from models.catch_check import CatchCheck


class CatchCheckRepository:
    def create(
        self,
        db_session: Session,
        catch_check: CatchCheck,
    ) -> CatchCheck:
        db_session.add(catch_check)
        db_session.commit()
        db_session.refresh(catch_check)
        return catch_check

    def get(
        self,
        db_session: Session,
        catch_id: UUID,
    ) -> Optional[CatchCheck]:
        return (
            db_session.query(CatchCheck).filter(CatchCheck.catch_id == catch_id).first()
        )

    def get_all(
        self,
        db_session: Session,
        inspection_id: Optional[UUID] = None,
        officer_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CatchCheck]:
        query = db_session.query(CatchCheck)

        if inspection_id is not None:
            query = query.filter(CatchCheck.inspection_id == inspection_id)

        if officer_id is not None:
            query = query.join(CatchCheck.inspection).filter(
                Inspection.officer_id == officer_id
            )

        return (
            query.order_by(CatchCheck.checked_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )


catch_check_repository = CatchCheckRepository()
