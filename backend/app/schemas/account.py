import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# Only the shape is checked: nothing is sent to the address yet (no password reset).
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_CHARS = 8
# Argon2 takes any length; the cap keeps hashing cheap to ask for.
MAX_PASSWORD_CHARS = 128


class LoginRequest(BaseModel):
    email: str = Field(max_length=254, examples=["ana@example.com"])
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_CHARS)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, email: str) -> str:
        email = email.strip().lower()
        if not EMAIL_PATTERN.match(email):
            raise ValueError("enter a valid email address")
        return email


class SignupRequest(LoginRequest):
    password: str = Field(min_length=MIN_PASSWORD_CHARS, max_length=MAX_PASSWORD_CHARS)
    display_name: str = Field(min_length=1, max_length=50, examples=["Ana"])

    @field_validator("display_name")
    @classmethod
    def _strip_name(cls, name: str) -> str:
        if not name.strip():
            raise ValueError("enter a name")
        return name.strip()


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    created_at: datetime
