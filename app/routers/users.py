import logging
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_write_db, get_read_db, get_current_user
from app.middleware.rate_limit import limiter, get_rate_limit_string
from app.schemas.user import (
    RegisterRequest,
    LoginRequest,
    LoginResponse,
    UserResponse,
    UserProfileResponse,
    FollowResponse,
    PaginatedUsersResponse,
)
from app.services.user_service import UserService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


@router.post("/register", response_model=UserResponse, status_code=201)
@limiter.limit(get_rate_limit_string())
async def register(
    request: Request,
    body: RegisterRequest,
    write_db: AsyncSession = Depends(get_write_db),
):
    """Register a new user."""
    return await UserService.register(write_db, body)


@router.get("/search", response_model=list[UserProfileResponse])
@limiter.limit(get_rate_limit_string())
async def search_users(
    request: Request,
    q: str = Query("", min_length=1, max_length=50),
    limit: int = Query(20, ge=1, le=100),
    read_db: AsyncSession = Depends(get_read_db),
):
    """Search users by username."""
    return await UserService.search_users(read_db, q, limit)


@router.post("/login", response_model=LoginResponse)
@limiter.limit(get_rate_limit_string())
async def login(
    request: Request,
    body: LoginRequest,
    write_db: AsyncSession = Depends(get_write_db),
):
    """Login and get JWT access token."""
    return await UserService.login(write_db, body.username, body.password)


@router.get("/{user_id}/profile", response_model=UserProfileResponse)
@limiter.limit(get_rate_limit_string())
async def get_profile(
    request: Request,
    user_id: uuid.UUID,
    read_db: AsyncSession = Depends(get_read_db),
):
    """Get a user's public profile."""
    return await UserService.get_profile(read_db, user_id)


@router.post("/{user_id}/follow", response_model=FollowResponse)
@limiter.limit(get_rate_limit_string())
async def follow_user(
    request: Request,
    user_id: uuid.UUID,
    write_db: AsyncSession = Depends(get_write_db),
    current_user: dict = Depends(get_current_user),
):
    """Follow a user."""
    follower_id = uuid.UUID(current_user["sub"])
    result = await UserService.follow(write_db, follower_id, user_id)
    return FollowResponse(detail=result["detail"])


@router.delete("/{user_id}/follow", response_model=FollowResponse)
@limiter.limit(get_rate_limit_string())
async def unfollow_user(
    request: Request,
    user_id: uuid.UUID,
    write_db: AsyncSession = Depends(get_write_db),
    current_user: dict = Depends(get_current_user),
):
    """Unfollow a user."""
    follower_id = uuid.UUID(current_user["sub"])
    result = await UserService.unfollow(write_db, follower_id, user_id)
    return FollowResponse(detail=result["detail"])


@router.get("/{user_id}/followers", response_model=PaginatedUsersResponse)
@limiter.limit(get_rate_limit_string())
async def get_followers(
    request: Request,
    user_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    read_db: AsyncSession = Depends(get_read_db),
):
    """List followers of a user (paginated)."""
    return await UserService.get_followers(read_db, user_id, limit, offset)


@router.get("/{user_id}/following", response_model=PaginatedUsersResponse)
@limiter.limit(get_rate_limit_string())
async def get_following(
    request: Request,
    user_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    read_db: AsyncSession = Depends(get_read_db),
):
    """List users that a user is following (paginated)."""
    return await UserService.get_following(read_db, user_id, limit, offset)
