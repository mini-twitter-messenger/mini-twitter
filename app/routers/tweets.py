import logging
import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_write_db, get_read_db, get_current_user
from app.middleware.rate_limit import limiter, get_rate_limit_string
from app.schemas.tweet import TweetCreateRequest, TweetResponse
from app.services.tweet_service import TweetService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tweets", tags=["tweets"])


@router.post("/", response_model=TweetResponse, status_code=201)
@limiter.limit(get_rate_limit_string())
async def create_tweet(
    request: Request,
    body: TweetCreateRequest,
    write_db: AsyncSession = Depends(get_write_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new tweet (max 280 characters)."""
    user_id = uuid.UUID(current_user["sub"])
    return await TweetService.create_tweet(write_db, user_id, body.content)


@router.delete("/{tweet_id}", status_code=204)
@limiter.limit(get_rate_limit_string())
async def delete_tweet(
    request: Request,
    tweet_id: uuid.UUID,
    write_db: AsyncSession = Depends(get_write_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a tweet (owner only)."""
    user_id = uuid.UUID(current_user["sub"])
    await TweetService.delete_tweet(write_db, tweet_id, user_id)
    return Response(status_code=204)


@router.get("/{tweet_id}", response_model=TweetResponse)
@limiter.limit(get_rate_limit_string())
async def get_tweet(
    request: Request,
    tweet_id: uuid.UUID,
    read_db: AsyncSession = Depends(get_read_db),
):
    """Get a single tweet by ID."""
    return await TweetService.get_tweet(read_db, tweet_id)
