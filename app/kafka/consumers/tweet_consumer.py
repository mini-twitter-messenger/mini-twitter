import json
import logging
import uuid
from datetime import datetime, timezone

from aiokafka import AIOKafkaConsumer

from app.config import settings
from app.db.session import _primary_engine
import app.dependencies as deps
from app.repositories.celebrity_repo import CelebrityRepository
from app.repositories.timeline_repo import TimelineRepository
from app.repositories.user_repo import UserRepository

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


async def start_tweet_consumer() -> None:
    """Consume tweet.created events and perform fan-out or celebrity store write.

    - Non-celebrity (follower_count <= CELEBRITY_THRESHOLD):
      Fan out to all followers' tl:home:{follower_id} on MAIN Redis.
    - Celebrity (follower_count > CELEBRITY_THRESHOLD):
      Write once to cel:{user_id} on the CELEBRITY Redis.
    - Always: write to tl:user:{user_id} on MAIN Redis.
    """
    consumer = AIOKafkaConsumer(
        "tweet.created",
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="tweet_consumer_group",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        enable_auto_commit=True,
        auto_commit_interval_ms=1000,
    )
    await consumer.start()
    logger.info("Tweet consumer started.")

    session_factory = async_sessionmaker(
        bind=_primary_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async for msg in consumer:
            try:
                payload = msg.value
                user_id_str = payload["user_id"]
                user_id = uuid.UUID(user_id_str)
                tweet_data = {
                    "id": payload.get("tweet_id", ""),
                    "content": payload.get("content", ""),
                    "user_id": user_id_str,
                    "username": payload.get("username", ""),
                    "created_at": payload.get("created_at", ""),
                }

                # Parse created_at for celebrity sorted set score
                created_at_str = payload.get("created_at", "")
                try:
                    created_at_dt = datetime.fromisoformat(created_at_str)
                    created_at_epoch = created_at_dt.timestamp()
                except (ValueError, TypeError):
                    created_at_epoch = datetime.now(timezone.utc).timestamp()

                # Get follower count from DB
                async with session_factory() as session:
                    follower_count = await UserRepository.get_follower_count(
                        session, user_id
                    )

                main_redis = deps._main_redis
                celebrity_redis = deps._celebrity_redis

                if follower_count <= settings.CELEBRITY_THRESHOLD:
                    # Non-celebrity: fan out to all followers' home timelines
                    async with session_factory() as session:
                        follower_ids = await UserRepository.get_all_follower_ids(
                            session, user_id
                        )
                    for follower_id in follower_ids:
                        await TimelineRepository.push_to_home_timeline(
                            main_redis, follower_id, tweet_data
                        )
                    logger.debug(
                        "Fan-out tweet %s to %d followers",
                        payload.get("tweet_id"),
                        len(follower_ids),
                    )
                else:
                    # Celebrity: write to celebrity Redis store
                    await CelebrityRepository.add_tweet(
                        celebrity_redis, user_id, tweet_data, created_at_epoch
                    )
                    logger.debug(
                        "Celebrity tweet %s stored in celebrity Redis for %s",
                        payload.get("tweet_id"),
                        user_id,
                    )

                # Always push to user's own timeline on main Redis
                await TimelineRepository.push_to_user_timeline(
                    main_redis, user_id, tweet_data
                )

            except Exception as exc:
                logger.error(
                    "Error processing tweet.created message: %s | payload: %s",
                    str(exc),
                    msg.value,
                    exc_info=True,
                )
                continue
    finally:
        await consumer.stop()
        logger.info("Tweet consumer stopped.")
