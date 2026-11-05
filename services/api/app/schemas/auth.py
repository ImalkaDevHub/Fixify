import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128

# A short deny-list of the most common passwords that satisfy the length rule.
_COMMON_PASSWORDS = frozenset(
    {
        "1234567890",
        "12345678910",
        "123456789a",
        "password123",
        "password12",
        "password1234",
        "qwertyuiop",
        "1q2w3e4r5t",
        "iloveyou123",
        "admin12345",
        "letmein123",
        "welcome123",
        "abcdefghij",
        "0987654321",
        "1111111111",
        "aaaaaaaaaa",
    }
)


def _validate_password(value: str) -> str:
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Use at least {PASSWORD_MIN_LENGTH} characters.")
    if len(value) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Use at most {PASSWORD_MAX_LENGTH} characters.")
    if not value.strip():
        raise ValueError("The password cannot be only spaces.")
    if value.lower() in _COMMON_PASSWORDS:
        raise ValueError("This password is too common. Choose another one.")
    return value


def _clean_name(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise ValueError("Enter a name.")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Control characters are not allowed.")
    return value


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=320)
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)
    display_name: str = Field(min_length=1, max_length=100)

    _password = field_validator("password")(_validate_password)
    _name = field_validator("display_name")(_clean_name)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=16, max_length=200)


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=320)


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=16, max_length=200)
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)

    _password = field_validator("password")(_validate_password)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
    new_password: str = Field(max_length=PASSWORD_MAX_LENGTH)

    _password = field_validator("new_password")(_validate_password)


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=100)

    _name = field_validator("display_name")(_clean_name)


class DeleteAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    email_verified: bool
    created_at: datetime
    last_login_at: datetime | None


class SessionRead(BaseModel):
    id: uuid.UUID
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    current: bool


class MessageResponse(BaseModel):
    message: str
