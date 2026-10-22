from sqlalchemy.orm import Session

from models.user import User


class UserRepository:
    def create(self, db: Session, user: User) -> User:
        db.add(user)
        db.flush()
        return user

    def get(self, db: Session, user_id) -> User | None:
        return db.query(User).filter(User.user_id == user_id).first()

    def get_by_email(self, db: Session, email: str) -> User | None:
        normalized_email = email.strip().lower()
        return db.query(User).filter(User.email == normalized_email).first()

    def get_by_phone(self, db: Session, phone_number: str) -> User | None:
        return db.query(User).filter(User.phone_number == phone_number).first()

    def list_users(
        self,
        db: Session,
        role=None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        query = db.query(User)

        if role is not None:
            query = query.filter(User.role == role)

        if is_active is not None:
            query = query.filter(User.is_active.is_(is_active))

        return (
            query.order_by(User.last_name, User.first_name)
            .limit(limit)
            .offset(offset)
            .all()
        )

    def count_by_role(self, db: Session, role) -> int:
        return db.query(User).filter(User.role == role).count()


user_repository = UserRepository()
