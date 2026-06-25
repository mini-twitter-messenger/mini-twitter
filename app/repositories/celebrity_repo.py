import json
import logging
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

CELEBRITY_KEY_PREFIX = "cel:"
CELEBRITY_MAX_TWEETS = 1000


def _tweet_to_json(tweet_data: dict) -> str:
    """Serialize a tweet dict to JSON string for sorted set member."""
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
    if isinstance(json_str, bytes):
        json_str = json_str.decode("utf-8")
    return json.loads(json_str)


class CelebrityRepository:
    """Repository for the celebrity Redis instance.
    
    Uses ONLY the dedicated celebrity Redis client. Never connects to
    the main Redis instance. Manages cel:{celebrity_id} sorted sets.
    """

    @staticmethod
    async def add_tweet(
        celebrity_redis: aioredis.Redis,
        celebrity_id: uuid.UUID,
        tweet_data: dict,
        created_at_epoch: float,
    ) -> None:
        """Add a tweet to the celebrity's sorted set on the celebrity Redis.
        
        Uses ZADD with created_at epoch as score, then trims to keep
        only the latest CELEBRITY_MAX_TWEETS entries.
        """
        key = f"{CELEBRITY_KEY_PREFIX}{celebrity_id}"
        tweet_json = _tweet_to_json(tweet_data)
        await celebrity_redis.zadd(key, {tweet_json: created_at_epoch})
        # Trim: keep only the latest 1000. Remove everything except top 1000.
        await celebrity_redis.zremrangebyrank(key, 0, -CELEBRITY_MAX_TWEETS - 1)
        logger.debug(
            "Added tweet to celebrity store for celebrity %s", celebrity_id
        )

    @staticmethod
    async def get_recent_tweets(
        celebrity_redis: aioredis.Redis,
        celebrity_id: uuid.UUID,
        count: int = 20,
    ) -> list[dict]:
        """Fetch the most recent tweets from a celebrity's sorted set.
        
        Uses ZREVRANGE to get the top `count` tweets by score (created_at epoch)
        from the dedicated celebrity Redis instance.
        """
        key = f"{CELEBRITY_KEY_PREFIX}{celebrity_id}"
        raw_tweets = await celebrity_redis.zrevrange(key, 0, count - 1)
        if not raw_tweets:
            return []
        return [_json_to_tweet(t) for t in raw_tweets]

    @staticmethod
    async def get_tweet_count(
        celebrity_redis: aioredis.Redis,
        celebrity_id: uuid.UUID,
    ) -> int:
        """Get the number of tweets in a celebrity's sorted set."""
        key = f"{CELEBRITY_KEY_PREFIX}{celebrity_id}"
        return await celebrity_redis.zcard(key)
