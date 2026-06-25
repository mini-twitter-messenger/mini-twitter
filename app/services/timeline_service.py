import logging
import uuid
from datetime import datetime
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.repositories.celebrity_repo import CelebrityRepository
from app.repositories.timeline_repo import TimelineRepository
from app.repositories.tweet_repo import TweetRepository
from app.repositories.user_repo import UserRepository
from app.schemas.timeline import TimelineTweet, TimelineResponse

logger = logging.getLogger(__name__)


def _tweet_model_to_dict(tweet) -> dict:
    """Convert a Tweet ORM model to a dict suitable for caching."""
    return {
        "id": str(tweet.id),
        "content": tweet.content,
        "user_id": str(tweet.user_id),
        "username": tweet.author.username if hasattr(tweet, 'author') and tweet.author else "",
        "created_at": tweet.created_at.isoformat(),
    }


def _dict_to_timeline_tweet(data: dict) -> TimelineTweet:
    """Convert a tweet dict to a TimelineTweet schema."""
    return TimelineTweet(
        id=data["id"],
        content=data["content"],
        user_id=data["user_id"],
        username=data.get("username", ""),
        created_at=data["created_at"],
    )


class TimelineService:
    """Service layer for timeline operations.
    
    Home timeline: fan-out on write (regular) + celebrity merge at read.
    User timeline: cache-first from main Redis, fallback to DB.
    """

    @staticmethod
    async def get_home_timeline(
        redis_client: aioredis.Redis,
        celebrity_redis_client: aioredis.Redis,
        read_db: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> TimelineResponse:
        """Get home timeline with celebrity merge.
        
        1. Fetch regular fanned-out tweets from tl:home:{user_id} on MAIN Redis
        2. Identify celebrity followees
        3. Fetch tweets from each celebrity's cel:{id} on CELEBRITY Redis
        4. Merge, sort by created_at DESC, deduplicate, paginate
        """
        # Step 1: Get regular tweets from main Redis cache
        regular_tweets = await TimelineRepository.get_home_timeline(
            redis_client, user_id, limit=1000, offset=0
        )

        if regular_tweets is None:
            # Cache miss — fetch from DB and populate cache
            db_tweets = await TweetRepository.get_home_timeline_from_db(
                read_db, user_id, limit=1000, offset=0
            )
            regular_tweets = [_tweet_model_to_dict(t) for t in db_tweets]
            if regular_tweets:
                await TimelineRepository.populate_home_timeline(
                    redis_client, user_id, regular_tweets
                )

        # Step 2: Identify celebrity followees
        celebrity_ids = await UserRepository.get_celebrity_followee_ids(
            read_db, user_id, settings.CELEBRITY_THRESHOLD
        )

        # Step 3: Fetch celebrity tweets from CELEBRITY Redis
        celebrity_tweets: list[dict] = []
        for celeb_id in celebrity_ids:
            celeb_tweets = await CelebrityRepository.get_recent_tweets(
                celebrity_redis_client, celeb_id, count=100
            )
            celebrity_tweets.extend(celeb_tweets)

        # Step 4: Merge regular + celebrity tweets
        all_tweets = regular_tweets + celebrity_tweets

        # Deduplicate by tweet ID
        seen_ids = set()
        unique_tweets = []
        for tweet in all_tweets:
            tweet_id = tweet.get("id") or tweet.get("tweet_id")
            if tweet_id and tweet_id not in seen_ids:
                seen_ids.add(tweet_id)
                unique_tweets.append(tweet)

        # Sort by created_at DESC
        def parse_created_at(t: dict) -> datetime:
            ca = t.get("created_at", "")
            if isinstance(ca, str):
                try:
                    return datetime.fromisoformat(ca)
                except (ValueError, TypeError):
                    return datetime.min
            return ca

        unique_tweets.sort(key=parse_created_at, reverse=True)

        # Paginate
        paginated = unique_tweets[offset: offset + limit]
        timeline_tweets = [_dict_to_timeline_tweet(t) for t in paginated]

        return TimelineResponse(
            tweets=timeline_tweets,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    async def get_user_timeline(
        redis_client: aioredis.Redis,
        read_db: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> TimelineResponse:
        """Get a user's own tweet timeline (cache-first)."""
        # Try cache first
        cached = await TimelineRepository.get_user_timeline(
            redis_client, user_id, limit, offset
        )

        if cached is not None:
            timeline_tweets = [_dict_to_timeline_tweet(t) for t in cached]
            return TimelineResponse(
                tweets=timeline_tweets, limit=limit, offset=offset
            )

        # Cache miss — fetch from DB
        db_tweets = await TweetRepository.get_tweets_by_user(
            read_db, user_id, limit, offset
        )
        tweet_dicts = [_tweet_model_to_dict(t) for t in db_tweets]

        # Populate cache
        if tweet_dicts:
            await TimelineRepository.populate_user_timeline(
                redis_client, user_id, tweet_dicts
            )

        timeline_tweets = [_dict_to_timeline_tweet(t) for t in tweet_dicts]
        return TimelineResponse(
            tweets=timeline_tweets, limit=limit, offset=offset
        )
