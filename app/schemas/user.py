import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Request schema for user registration."""
    username: str = Field(..., min_length=1, max_length=50)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    """Request schema for user login."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Response schema for successful login."""
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Response schema for user data (registration response)."""
    id: uuid.UUID
    username: str
    email: str
    follower_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class UserProfileResponse(BaseModel):
    """Response schema for public user profile."""
    id: uuid.UUID
    username: str
    email: str
    follower_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class FollowResponse(BaseModel):
    """Response schema for follow/unfollow operations."""
    detail: str


class PaginatedUsersResponse(BaseModel):
    """Paginated response for user lists (followers, following)."""
    users: list[UserProfileResponse]
    total: int
    limit: int
    offset: int
