import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

HOME_TIMELINE_PREFIX = "tl:home:"
USER_TIMELINE_PREFIX = "tl:user:"
TIMELINE_MAX_LENGTH = 1000
TIMELINE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days


def _tweet_to_json(tweet_data: dict) -> str:
    """Serialize a tweet dict to JSON string."""
    serializable = {}
    for key, value in tweet_data.items():
        if isinstance(value, uuid.UUID):
            serializable[key] = str(value)
        elif isinstance(value, datetime):
            serializable[key] = value.isoformat()
        else:
            serializable[key] = value
    return json.dumps(serializable)


def _json_to_tweet(json_str: str) -> dict:
    """Deserialize a JSON string to a tweet dict."""
    return json.loads(json_str)


class TimelineRepository:
    """Repository for main Redis timeline operations.
    
    Uses ONLY the main Redis client. Never connects to the celebrity Redis.
    """

    @staticmethod
    async def push_to_home_timeline(
        redis_client: aioredis.Redis,
        user_id: uuid.UUID,
        tweet_data: dict,
    ) -> None:
        """Push a tweet to a user's home timeline cache."""
        key = f"{HOME_TIMELINE_PREFIX}{user_id}"
        tweet_json = _tweet_to_json(tweet_data)
        await redis_client.lpush(key, tweet_json)
        await redis_client.ltrim(key, 0, TIMELINE_MAX_LENGTH - 1)
        await redis_client.expire(key, TIMELINE_TTL_SECONDS)
        logger.debug("Pushed tweet to home timeline for user %s", user_id)

    @staticmethod
    async def push_to_user_timeline(
        redis_client: aioredis.Redis,
        user_id: uuid.UUID,
        tweet_data: dict,
    ) -> None:
        """Push a tweet to a user's own timeline cache."""
        key = f"{USER_TIMELINE_PREFIX}{user_id}"
        tweet_json = _tweet_to_json(tweet_data)
        await redis_client.lpush(key, tweet_json)
        await redis_client.ltrim(key, 0, TIMELINE_MAX_LENGTH - 1)
        await redis_client.expire(key, TIMELINE_TTL_SECONDS)
        logger.debug("Pushed tweet to user timeline for user %s", user_id)

    @staticmethod
    async def get_home_timeline(
        redis_client: aioredis.Redis,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> Optional[list[dict]]:
        """Fetch home timeline from cache. Returns None on cache miss."""
        key = f"{HOME_TIMELINE_PREFIX}{user_id}"
        exists = await redis_client.exists(key)
        if not exists:
            return None
        raw_tweets = await redis_client.lrange(key, offset, offset + limit - 1)
        if not raw_tweets:
            return []
        return [_json_to_tweet(t) for t in raw_tweets]

    @staticmethod
    async def get_user_timeline(
        redis_client: aioredis.Redis,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> Optional[list[dict]]:
        """Fetch user timeline from cache. Returns None on cache miss."""
        key = f"{USER_TIMELINE_PREFIX}{user_id}"
        exists = await redis_client.exists(key)
        if not exists:
            return None
        raw_tweets = await redis_client.lrange(key, offset, offset + limit - 1)
        if not raw_tweets:
            return []
        return [_json_to_tweet(t) for t in raw_tweets]

    @staticmethod
    async def populate_home_timeline(
        redis_client: aioredis.Redis,
        user_id: uuid.UUID,
        tweets: list[dict],
    ) -> None:
        """Populate a user's home timeline cache from a list of tweet dicts."""
        key = f"{HOME_TIMELINE_PREFIX}{user_id}"
        if not tweets:
            return
        pipeline = redis_client.pipeline()
        await pipeline.delete(key)
        for tweet in tweets:
            tweet_json = _tweet_to_json(tweet)
            await pipeline.rpush(key, tweet_json)
        await pipeline.ltrim(key, 0, TIMELINE_MAX_LENGTH - 1)
        await pipeline.expire(key, TIMELINE_TTL_SECONDS)
        await pipeline.execute()
        logger.debug(
            "Populated home timeline cache for user %s with %d tweets",
            user_id,
            len(tweets),
        )

    @staticmethod
    async def populate_user_timeline(
        redis_client: aioredis.Redis,
        user_id: uuid.UUID,
        tweets: list[dict],
    ) -> None:
        """Populate a user's own timeline cache."""
        key = f"{USER_TIMELINE_PREFIX}{user_id}"
        if not tweets:
            return
        pipeline = redis_client.pipeline()
        await pipeline.delete(key)
        for tweet in tweets:
            tweet_json = _tweet_to_json(tweet)
            await pipeline.rpush(key, tweet_json)
        await pipeline.ltrim(key, 0, TIMELINE_MAX_LENGTH - 1)
        await pipeline.expire(key, TIMELINE_TTL_SECONDS)
        await pipeline.execute()

    @staticmethod
    async def invalidate_home_timeline(
        redis_client: aioredis.Redis,
        user_id: uuid.UUID,
    ) -> None:
        """Delete a user's home timeline cache (e.g., on unfollow)."""
        key = f"{HOME_TIMELINE_PREFIX}{user_id}"
        await redis_client.delete(key)
        logger.debug("Invalidated home timeline cache for user %s", user_id)

    @staticmethod
    async def invalidate_user_timeline(
        redis_client: aioredis.Redis,
        user_id: uuid.UUID,
    ) -> None:
        """Delete a user's own timeline cache."""
        key = f"{USER_TIMELINE_PREFIX}{user_id}"
        await redis_client.delete(key)
