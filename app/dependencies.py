import logging
import uuid
from typing import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_write_session, get_read_session
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

# Redis clients — module-level singletons
_main_redis: aioredis.Redis | None = None
_celebrity_redis: aioredis.Redis | None = None


async def init_redis() -> None:
    """Initialize both Redis clients. Called during app startup."""
    global _main_redis, _celebrity_redis
    _main_redis = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
    _celebrity_redis = aioredis.from_url(
        settings.CELEBRITY_REDIS_URL,
        decode_responses=True,
    )
    logger.info("Redis clients initialized (main: %s, celebrity: %s)",
                settings.REDIS_URL, settings.CELEBRITY_REDIS_URL)


async def close_redis() -> None:
    """Close both Redis clients. Called during app shutdown."""
    global _main_redis, _celebrity_redis
    if _main_redis:
        await _main_redis.close()
        _main_redis = None
    if _celebrity_redis:
        await _celebrity_redis.close()
        _celebrity_redis = None
    logger.info("Redis clients closed.")


async def get_write_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency: yield a write (primary) database session."""
    async for session in get_write_session():
        yield session


async def get_read_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency: yield a read (replica, round-robin) database session."""
    async for session in get_read_session():
        yield session


async def get_redis() -> aioredis.Redis:
    """Dependency: return the MAIN Redis client.
    
    Used for tl:home:{user_id}, tl:user:{user_id}, rate:{user_id}:{ep}.
    Never used for celebrity tweet store.
    """
    if _main_redis is None:
        raise HTTPException(
            status_code=503,
            detail={"detail": "Redis not available", "code": "REDIS_UNAVAILABLE"},
        )
    return _main_redis


async def get_celebrity_redis() -> aioredis.Redis:
    """Dependency: return the CELEBRITY Redis client.
    
    Used ONLY for cel:{celebrity_id} sorted sets.
    This is a SEPARATE Redis container from the main Redis.
    Never used for regular timelines, sessions, or rate limiting.
    """
    if _celebrity_redis is None:
        raise HTTPException(
            status_code=503,
            detail={"detail": "Celebrity Redis not available", "code": "CELEBRITY_REDIS_UNAVAILABLE"},
        )
    return _celebrity_redis


async def get_current_user(
    authorization: str = Header(None),
) -> dict:
    """Dependency: validate JWT from Authorization header.
    
    Returns payload dict with {sub: user_id, username: str, exp: timestamp}.
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={"detail": "Authorization header missing", "code": "UNAUTHORIZED"},
        )

    # Expect "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail={"detail": "Invalid authorization format", "code": "UNAUTHORIZED"},
        )

    token = parts[1]
    payload = AuthService.verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=401,
            detail={"detail": "Invalid or expired token", "code": "UNAUTHORIZED"},
        )

    return payload
