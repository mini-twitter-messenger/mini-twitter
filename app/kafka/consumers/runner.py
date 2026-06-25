import asyncio
import logging
from typing import List

from app.kafka.consumers.tweet_consumer import start_tweet_consumer
from app.kafka.consumers.follow_consumer import start_follow_consumer

logger = logging.getLogger(__name__)


async def start_consumers() -> List[asyncio.Task]:
    """Start all Kafka consumers as asyncio background tasks.

    Returns a list of tasks so they can be cancelled during shutdown.
    """
    tasks = []

    tweet_task = asyncio.create_task(start_tweet_consumer())
    tweet_task.set_name("tweet_consumer")
    tasks.append(tweet_task)

    follow_task = asyncio.create_task(start_follow_consumer())
    follow_task.set_name("follow_consumer")
    tasks.append(follow_task)

    logger.info("Started %d Kafka consumer tasks.", len(tasks))
    return tasks
