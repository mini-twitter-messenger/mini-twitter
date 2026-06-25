import logging
import uuid
from typing import Optional

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.tweet import Tweet
from app.models.follower import Follower
from app.models.user import User

logger = logging.getLogger(__name__)


class TweetRepository:
    """Repository for tweet data access."""

    @staticmethod
    async def create_tweet(
        session: AsyncSession,
        user_id: uuid.UUID,
        content: str,
    ) -> Tweet:
        """Insert a new tweet."""
        tweet = Tweet(user_id=user_id, content=content)
        session.add(tweet)
        await session.flush()
        await session.refresh(tweet)
        logger.info("Created tweet %s by user %s", tweet.id, user_id)
        return tweet

    @staticmethod
    async def get_by_id(
        session: AsyncSession, tweet_id: uuid.UUID
    ) -> Optional[Tweet]:
        """Fetch a tweet by its UUID."""
        result = await session.execute(
            select(Tweet).where(Tweet.id == tweet_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_tweet(
        session: AsyncSession, tweet_id: uuid.UUID
    ) -> bool:
        """Delete a tweet by its UUID. Returns True if deleted."""
        result = await session.execute(
            delete(Tweet).where(Tweet.id == tweet_id)
        )
        deleted = result.rowcount > 0
        if deleted:
            logger.info("Deleted tweet %s", tweet_id)
        return deleted

    @staticmethod
    async def get_tweets_by_user(
        session: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Tweet]:
        """Fetch tweets by a user, ordered by created_at DESC."""
        result = await session.execute(
            select(Tweet)
            .options(joinedload(Tweet.author))
            .where(Tweet.user_id == user_id)
            .order_by(Tweet.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.unique().scalars().all())

    @staticmethod
    async def get_home_timeline_from_db(
        session: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Tweet]:
        """Fetch home timeline tweets from DB (fallback when cache misses).
        
        Gets tweets from all users that user_id follows PLUS the user's
        own tweets, ordered by created_at DESC.
        """
        # Get IDs of users this user follows
        from app.models.follower import Follower as FollowerModel
        following_subq = (
            select(FollowerModel.followee_id)
            .where(FollowerModel.follower_id == user_id)
        ).scalar_subquery()

        result = await session.execute(
            select(Tweet)
            .options(joinedload(Tweet.author))
            .where(
                (Tweet.user_id == user_id) | (Tweet.user_id.in_(following_subq))
            )
            .order_by(Tweet.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.unique().scalars().all())

    @staticmethod
    async def get_recent_tweets_by_user(
        session: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 20,
    ) -> list[Tweet]:
        """Fetch the most recent tweets by a user (used for backfill on follow)."""
        result = await session.execute(
            select(Tweet)
            .options(joinedload(Tweet.author))
            .where(Tweet.user_id == user_id)
            .order_by(Tweet.created_at.desc())
            .limit(limit)
        )
        return list(result.unique().scalars().all())
