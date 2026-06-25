import logging
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_read_db,
    get_redis,
    get_celebrity_redis,
    get_current_user,
)
from app.middleware.rate_limit import limiter, get_rate_limit_string
from app.schemas.timeline import TimelineResponse
from app.services.timeline_service import TimelineService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/timeline", tags=["timeline"])


@router.get("/home", response_model=TimelineResponse)
@limiter.limit(get_rate_limit_string())
async def home_timeline(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    redis_client: aioredis.Redis = Depends(get_redis),
    celebrity_redis_client: aioredis.Redis = Depends(get_celebrity_redis),
    read_db: AsyncSession = Depends(get_read_db),
    current_user: dict = Depends(get_current_user),
):
    """Get home timeline (regular fan-out + celebrity merge)."""
    user_id = uuid.UUID(current_user["sub"])
    return await TimelineService.get_home_timeline(
        redis_client, celebrity_redis_client, read_db, user_id, limit, offset
    )


@router.get("/user/{user_id}", response_model=TimelineResponse)
@limiter.limit(get_rate_limit_string())
async def user_timeline(
    request: Request,
    user_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    redis_client: aioredis.Redis = Depends(get_redis),
    read_db: AsyncSession = Depends(get_read_db),
):
    """Get a user's tweet timeline (paginated)."""
    return await TimelineService.get_user_timeline(
        redis_client, read_db, user_id, limit, offset
    )
