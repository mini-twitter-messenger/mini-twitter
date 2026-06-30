import json
import logging
from typing import Optional

from aiokafka import AIOKafkaProducer

from app.config import settings

logger = logging.getLogger(__name__)


class KafkaProducerWrapper:
    """Singleton wrapper around AIOKafkaProducer."""

    def __init__(self) -> None:
        self._producer: Optional[AIOKafkaProducer] = None

    async def start(self) -> None:
        """Start the Kafka producer."""
        producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            request_timeout_ms=5000,
        )
        await producer.start()
        self._producer = producer
        logger.info("Kafka producer started.")

    async def stop(self) -> None:
        """Stop the Kafka producer."""
        if self._producer:
            await self._producer.stop()
            self._producer = None
            logger.info("Kafka producer stopped.")

    async def send(
        self,
        topic: str,
        value: dict,
        key: Optional[str] = None,
    ) -> None:
        """Send a message to a Kafka topic."""
        if not self._producer:
            logger.warning(
                "Kafka producer not started. Skipping message to topic %s",
                topic,
            )
            return
        try:
            await self._producer.send(topic, value=value, key=key)
            logger.debug("Queued message to topic %s: %s", topic, value)
        except Exception as e:
            logger.error(
                "Failed to send message to topic %s: %s", topic, str(e)
            )


kafka_producer = KafkaProducerWrapper()
