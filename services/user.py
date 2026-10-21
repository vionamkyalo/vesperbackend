import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from core.security import (
    AuthenticationError,
    RESET_TOKEN,
    ValidationFailedError,
    create_reset_token,
    decode_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from models.user import User, UserRole
from repositories.user import user_repository
from schemas.user import (
    ForgotPasswordResponse,
    PasswordChange,
    ResetPasswordResponse,
    UserCreate,
    UserRead,
    UserUpdate,
)
from services.email import send_officer_credentials, send_password_reset_email

logger = logging.getLogger(__name__)

REQUIRED_UPDATE_FIELDS = (
    "first_name",
    "last_name",
    "phone_number",
    "is_active",
)


class UserService:
    def check_active(self, current_user: User) -> None:
        if current_user is None or not current_user.is_active:
            logger.warning("Access refused: inactive or unknown user")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not active.",
            )

    def is_coordinator(self, current_user: User) -> bool:
        return (
            current_user is not None
            and current_user.role == UserRole.PATROL_COORDINATOR
        )

    def check_coordinator(self, current_user: User) -> None:
        self.check_active(current_user)
        if not self.is_coordinator(current_user):
            logger.warning(
                "User action refused: user %s is not the coordinator",
                current_user.user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the patrol coordinator can do this.",
            )

    def full_name(self, user: User) -> str:
        return f"{user.first_name} {user.last_name}"

    def to_read(self, user: User) -> UserRead:
        return UserRead(
            user_id=user.user_id,
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=self.full_name(user),
            phone_number=user.phone_number,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    def check_password_strength(self, password: str) -> None:
        try:
            validate_password_strength(password)
        except ValidationFailedError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error.message,
            ) from error

    def check_email_and_phone_free(
        self,
        db: Session,
        email: str | None = None,
        phone_number: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> None:
        if email is not None:
            existing = user_repository.get_by_email(db, email)
            if existing is not None and existing.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A user with this email already exists.",
                )

        if phone_number is not None:
            existing = user_repository.get_by_phone(db, phone_number)
            if existing is not None and existing.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A user with this phone number already exists.",
                )

    def _commit(self, db: Session) -> None:
        try:
            db.commit()
        except IntegrityError as error:
            db.rollback()
            logger.warning("Database integrity constraint conflict")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "The operation conflicts with an existing record "
                    "or a database constraint."
                ),
            ) from error
        except SQLAlchemyError as error:
            db.rollback()
            logger.exception("Database operation failed")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The database operation could not be completed.",
            ) from error

    def seed_coordinator(self, db: Session, settings) -> User | None:
        if not settings.seed_coordinator_configured:
            return None

        if user_repository.count_by_role(db, UserRole.PATROL_COORDINATOR) > 0:
            return None

        password = settings.seed_coordinator_password.get_secret_value()
        if not password:
            raise RuntimeError(
                "SEED_COORDINATOR_PASSWORD is needed to create the coordinator"
            )

        try:
            validate_password_strength(password)
        except ValidationFailedError as error:
            raise RuntimeError(
                "The configured coordinator password does not meet "
                "the password policy."
            ) from error

        email = settings.seed_coordinator_email.strip().lower()
        phone_number = settings.seed_coordinator_phone

        if user_repository.get_by_email(db, email) is not None:
            raise RuntimeError("SEED_COORDINATOR_EMAIL already belongs to another user")

        if user_repository.get_by_phone(db, phone_number) is not None:
            raise RuntimeError("SEED_COORDINATOR_PHONE already belongs to another user")

        user = User(
            first_name=settings.seed_coordinator_first_name,
            last_name=settings.seed_coordinator_last_name,
            phone_number=phone_number,
            email=email,
            password_hash=hash_password(password),
            role=UserRole.PATROL_COORDINATOR,
            is_active=True,
        )

        try:
            user_repository.create(db, user)
            db.commit()
            db.refresh(user)
        except IntegrityError as error:
            db.rollback()
            logger.exception("Coordinator creation encountered a conflict")
            raise RuntimeError(
                "Coordinator creation failed because of a database conflict."
            ) from error
        except SQLAlchemyError as error:
            db.rollback()
            logger.exception("Coordinator creation failed")
            raise RuntimeError(
                "Coordinator creation failed because of a database error."
            ) from error

        logger.info("Patrol coordinator %s seeded", user.user_id)
        return user

    def create_user(
        self,
        db: Session,
        current_user: User,
        data: UserCreate,
    ) -> UserRead:
        self.check_coordinator(current_user)
        self.check_password_strength(data.password)

        email = str(data.email).strip().lower()
        self.check_email_and_phone_free(
            db,
            email=email,
            phone_number=data.phone_number,
        )

        user = User(
            first_name=data.first_name,
            last_name=data.last_name,
            phone_number=data.phone_number,
            email=email,
            password_hash=hash_password(data.password),
            role=data.role,
            is_active=True,
        )

        try:
            user_repository.create(db, user)
            db.commit()
            db.refresh(user)
        except IntegrityError as error:
            db.rollback()
            logger.warning("User creation encountered a constraint conflict")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("A user with this email or phone number already exists."),
            ) from error
        except SQLAlchemyError as error:
            db.rollback()
            logger.exception("User creation failed")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The user could not be created.",
            ) from error

        logger.info(
            "User %s with role %s created by %s",
            user.user_id,
            user.role.value,
            current_user.user_id,
        )

        try:
            send_officer_credentials(
                recipient=user.email,
                first_name=user.first_name,
                password=data.password,
            )
        except Exception as error:
            logger.exception(
                "Officer account created, but credential email failed for user %s",
                user.user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "The account was created, but the email could not be sent. "
                    "Check the email configuration before retrying."
                ),
            ) from error

        return self.to_read(user)

    def get_user_record(
        self,
        db: Session,
        current_user: User,
        user_id: uuid.UUID,
    ) -> User:
        self.check_active(current_user)

        if not self.is_coordinator(current_user) and current_user.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User was not found.",
            )

        user = user_repository.get(db, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User was not found.",
            )

        return user

    def get_user(
        self,
        db: Session,
        current_user: User,
        user_id: uuid.UUID,
    ) -> UserRead:
        user = self.get_user_record(db, current_user, user_id)
        return self.to_read(user)

    def get_me(self, current_user: User) -> UserRead:
        self.check_active(current_user)
        return self.to_read(current_user)

    def list_users(
        self,
        db: Session,
        current_user: User,
        role: UserRole | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UserRead]:
        self.check_coordinator(current_user)

        users = user_repository.list_users(
            db,
            role=role,
            is_active=is_active,
            limit=limit,
            offset=offset,
        )
        return [self.to_read(user) for user in users]

    def update_user(
        self,
        db: Session,
        current_user: User,
        user_id: uuid.UUID,
        data: UserUpdate,
    ) -> UserRead:
        user = self.get_user_record(db, current_user, user_id)
        changes = data.model_dump(exclude_unset=True)

        if not changes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one field must be provided.",
            )

        for field in REQUIRED_UPDATE_FIELDS:
            if field in changes and changes[field] is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{field} cannot be empty.",
                )

        if "is_active" in changes:
            if not self.is_coordinator(current_user):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Only the patrol coordinator can activate "
                        "or deactivate accounts."
                    ),
                )

            if user.user_id == current_user.user_id and changes["is_active"] is False:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=("The coordinator cannot deactivate their own account."),
                )

        if changes.get("phone_number") is not None:
            self.check_email_and_phone_free(
                db,
                phone_number=changes["phone_number"],
                user_id=user.user_id,
            )

        for field in REQUIRED_UPDATE_FIELDS:
            if field in changes:
                setattr(user, field, changes[field])

        self._commit(db)

        try:
            db.refresh(user)
        except SQLAlchemyError as error:
            db.rollback()
            logger.exception("Failed to refresh updated user")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The updated user could not be retrieved.",
            ) from error

        logger.info(
            "User %s updated by %s: %s",
            user.user_id,
            current_user.user_id,
            sorted(changes),
        )
        return self.to_read(user)

    def change_password(
        self,
        db: Session,
        current_user: User,
        data: PasswordChange,
    ) -> None:
        self.check_active(current_user)

        if not verify_password(
            data.current_password,
            current_user.password_hash,
        ):
            logger.warning(
                "Password change refused for %s: wrong current password",
                current_user.user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is not correct.",
            )

        if data.new_password == data.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=("New password must be different from the current one."),
            )

        self.check_password_strength(data.new_password)
        current_user.password_hash = hash_password(data.new_password)
        self._commit(db)
        logger.info("Password changed for %s", current_user.user_id)

    def forgot_password(self, db: Session, email: str) -> ForgotPasswordResponse:
        user = user_repository.get_by_email(db, email)

        if user is not None and user.is_active:
            token = create_reset_token(user.user_id)

            try:
                send_password_reset_email(
                    recipient=user.email,
                    first_name=user.first_name,
                    reset_token=token,
                )
            except Exception as error:
                logger.exception(
                    "Password reset email failed for user %s", user.user_id
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        "The reset token was created, but the email could not be "
                        "sent. Check the email configuration before retrying."
                    ),
                ) from error

        return ForgotPasswordResponse()

    def reset_password(
        self, db: Session, token: str, new_password: str
    ) -> ResetPasswordResponse:
        self.check_password_strength(new_password)

        try:
            payload = decode_token(token, RESET_TOKEN)
            user_id = uuid.UUID(payload["sub"])
        except AuthenticationError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token.",
            )

        user = user_repository.get(db, user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token.",
            )

        user.password_hash = hash_password(new_password)
        self._commit(db)

        logger.info("Password reset for %s", user.user_id)
        return ResetPasswordResponse()

    def deactivate_user(
        self,
        db: Session,
        current_user: User,
        user_id: uuid.UUID,
    ) -> UserRead:
        self.check_coordinator(current_user)

        user = user_repository.get(db, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User was not found.",
            )

        if user.user_id == current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("The coordinator cannot deactivate their own account."),
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This account is already deactivated.",
            )

        user.is_active = False
        self._commit(db)

        try:
            db.refresh(user)
        except SQLAlchemyError as error:
            db.rollback()
            logger.exception("Failed to refresh deactivated user")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The deactivated user could not be retrieved.",
            ) from error

        logger.info(
            "User %s deactivated by %s",
            user.user_id,
            current_user.user_id,
        )
        return self.to_read(user)


user_service = UserService()
