"""Pydantic schemas for user authentication and session management."""

from typing import Optional
from pydantic import BaseModel, Field, field_validator
import re

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")


class SignupRequest(BaseModel):
    """User registration payload."""
    email: str = Field(..., description="Valid email address")
    username: str = Field(..., min_length=2, max_length=50, description="Display name / username")
    password: str = Field(..., min_length=6, max_length=100, description="Account password (min 6 chars)")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email format.")
        return clean


class LoginRequest(BaseModel):
    """User login payload."""
    email: str = Field(..., description="Registered email address")
    password: str = Field(..., min_length=1, description="Account password")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email format.")
        return clean


class UserResponse(BaseModel):
    """Sanitized user public profile response."""
    id: int = Field(..., description="User ID")
    email: str = Field(..., description="User email")
    username: str = Field(..., description="Username / display name")
    created_at: Optional[str] = Field(None, description="Account creation timestamp")
    last_login: Optional[str] = Field(None, description="Last login timestamp")


class AuthResponse(BaseModel):
    """Authentication success payload with bearer token."""
    token: str = Field(..., description="Signed access token")
    user: UserResponse = Field(..., description="Authenticated user profile")
    message: str = Field("Authentication successful", description="Status message")
