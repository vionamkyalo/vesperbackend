import uuid
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

from models.user import UserRole


PHONE_PATTERN = r"^\+[1-9]\d{7,14}$"


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone_number: str = Field(pattern=PHONE_PATTERN)
    email: EmailStr = Field(max_length=100)
    password: str = Field(min_length=12, max_length=128)
    role: UserRole = UserRole.PATROL_OFFICER

    @field_validator("email")
    @classmethod
    def lower_email(cls, value):
        return value.lower()


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone_number: str | None = Field(default=None, pattern=PHONE_PATTERN)
    is_active: bool | None = None


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class UserRead(BaseModel):
    user_id: uuid.UUID
    first_name: str
    last_name: str
    full_name: str
    phone_number: str
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def lower_email(cls, value):
        return value.lower()


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr

    @field_validator("email")
    @classmethod
    def lower_email(cls, value):
        return value.lower()


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def lower_email(cls, value):
        return value.lower()


class ForgotPasswordResponse(BaseModel):
    message: str = (
        "If an account exists for that email, a password reset code has been sent."
    )


class ResetPasswordResponse(BaseModel):
    message: str = "Password has been reset successfully."


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
