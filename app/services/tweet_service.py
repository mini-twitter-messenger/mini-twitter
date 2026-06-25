import logging
import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.kafka.producer import kafka_producer
from app.repositories.tweet_repo import TweetRepository
from app.schemas.tweet import TweetResponse

logger = logging.getLogger(__name__)


class TweetService:
    """Service layer for tweet operations."""

    @staticmethod
    async def create_tweet(
        write_db: AsyncSession,
        user_id: uuid.UUID,
        content: str,
    ) -> TweetResponse:
        """Create a new tweet."""
        if len(content) > 280:
            raise HTTPException(
                status_code=422,
                detail={"detail": "Tweet content exceeds 280 characters", "code": "TWEET_TOO_LONG"},
            )
        if len(content) == 0:
            raise HTTPException(
                status_code=422,
                detail={"detail": "Tweet content cannot be empty", "code": "TWEET_EMPTY"},
            )

        tweet = await TweetRepository.create_tweet(write_db, user_id, content)

        # Fetch the author username for the Kafka payload
        from app.repositories.user_repo import UserRepository
        author = await UserRepository.get_by_id(write_db, user_id)
        username = author.username if author else ""

        # Publish tweet.created event to Kafka
        await kafka_producer.send(
            topic="tweet.created",
            value={
                "tweet_id": str(tweet.id),
                "user_id": str(tweet.user_id),
                "content": tweet.content,
                "username": username,
                "created_at": tweet.created_at.isoformat(),
            },
        )
        logger.info("Tweet created: %s by user %s", tweet.id, user_id)
        return TweetResponse.model_validate(tweet)

    @staticmethod
    async def delete_tweet(
        write_db: AsyncSession,
        tweet_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Delete a tweet. Only the owner can delete."""
        tweet = await TweetRepository.get_by_id(write_db, tweet_id)
        if not tweet:
            raise HTTPException(
                status_code=404,
                detail={"detail": "Tweet not found", "code": "TWEET_NOT_FOUND"},
            )
        if tweet.user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail={"detail": "Not authorized to delete this tweet", "code": "FORBIDDEN"},
            )
        await TweetRepository.delete_tweet(write_db, tweet_id)
        logger.info("Tweet %s deleted by user %s", tweet_id, user_id)

    @staticmethod
    async def get_tweet(
        read_db: AsyncSession,
        tweet_id: uuid.UUID,
    ) -> TweetResponse:
        """Get a single tweet by ID."""
        tweet = await TweetRepository.get_by_id(read_db, tweet_id)
        if not tweet:
            raise HTTPException(
                status_code=404,
                detail={"detail": "Tweet not found", "code": "TWEET_NOT_FOUND"},
            )
        return TweetResponse.model_validate(tweet)
