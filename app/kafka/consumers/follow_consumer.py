import json
import logging
import uuid

from aiokafka import AIOKafkaConsumer

from app.config import settings
from app.db.session import _primary_engine
import app.dependencies as deps
from app.repositories.timeline_repo import TimelineRepository
from app.repositories.tweet_repo import TweetRepository
from app.repositories.user_repo import UserRepository

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


async def start_follow_consumer() -> None:
    """Consume follow.created and follow.deleted events.

    follow.created:
    - If followee is a regular user (follower_count <= threshold):
      backfill their recent tweets into follower's tl:home on MAIN Redis.
    - If followee is a celebrity: do nothing (merged at read time).

    follow.deleted:
    - DEL tl:home:{follower_id} — cache will rebuild on next read.
    """
    consumer = AIOKafkaConsumer(
        "follow.created",
        "follow.deleted",
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="follow_consumer_group",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        enable_auto_commit=True,
        auto_commit_interval_ms=1000,
    )
    await consumer.start()
    logger.info("Follow consumer started.")

    session_factory = async_sessionmaker(
        bind=_primary_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async for msg in consumer:
            try:
                payload = msg.value
                topic = msg.topic
                follower_id = uuid.UUID(payload["follower_id"])
                followee_id = uuid.UUID(payload["followee_id"])
                main_redis = deps._main_redis

                if topic == "follow.created":
                    # Get followee's follower count
                    async with session_factory() as session:
                        follower_count = await UserRepository.get_follower_count(
                            session, followee_id
                        )

                    if follower_count > settings.CELEBRITY_THRESHOLD:
                        # Celebrity: do nothing on follow — tweets merged at read time
                        logger.debug(
                            "Follow event for celebrity %s — skipping backfill",
                            followee_id,
                        )
                        continue

                    # Regular user: backfill recent tweets into follower's home timeline
                    async with session_factory() as session:
                        recent_tweets = await TweetRepository.get_recent_tweets_by_user(
                            session, followee_id, limit=20
                        )

                    if recent_tweets:
                        tweet_dicts = []
                        for tweet in recent_tweets:
                            tweet_dicts.append({
                                "id": str(tweet.id),
                                "content": tweet.content,
                                "user_id": str(tweet.user_id),
                                "username": "",
                                "created_at": tweet.created_at.isoformat(),
                            })

                        # Push each tweet to follower's home timeline
                        for td in tweet_dicts:
                            await TimelineRepository.push_to_home_timeline(
                                main_redis, follower_id, td
                            )

                        # Sort the home timeline: fetch all, sort in Python, rewrite
                        home_key = f"tl:home:{follower_id}"
                        all_raw = await main_redis.lrange(home_key, 0, -1)
                        if all_raw:
                            parsed = [json.loads(t) for t in all_raw]
                            parsed.sort(
                                key=lambda x: x.get("created_at", ""),
                                reverse=True,
                            )
                            pipeline = main_redis.pipeline()
                            await pipeline.delete(home_key)
                            for t in parsed:
                                await pipeline.rpush(home_key, json.dumps(t))
                            await pipeline.ltrim(home_key, 0, 999)
                            await pipeline.expire(home_key, 7 * 24 * 60 * 60)
                            await pipeline.execute()

                    logger.debug(
                        "Backfilled %d tweets from %s into %s's home timeline",
                        len(recent_tweets) if recent_tweets else 0,
                        followee_id,
                        follower_id,
                    )

                elif topic == "follow.deleted":
                    # Invalidate follower's home timeline cache
                    await TimelineRepository.invalidate_home_timeline(
                        main_redis, follower_id
                    )
                    logger.debug(
                        "Invalidated home timeline for %s after unfollowing %s",
                        follower_id,
                        followee_id,
                    )

            except Exception as exc:
                logger.error(
                    "Error processing follow message: %s | payload: %s",
                    str(exc),
                    msg.value,
                    exc_info=True,
                )
                continue
    finally:
        await consumer.stop()
        logger.info("Follow consumer stopped.")
