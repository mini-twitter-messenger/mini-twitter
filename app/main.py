import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.dependencies import init_redis, close_redis
from app.kafka.producer import kafka_producer
from app.kafka.consumers.runner import start_consumers
from app.middleware.rate_limit import limiter
from app.routers import users, tweets, timeline

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic."""
    logger.info(
        "Starting Mini Twitter service: %s (instance %s)",
        settings.SERVICE_NAME,
        settings.INSTANCE_ID,
    )

    # Initialize Redis clients
    await init_redis()

    # Start Kafka producer
    try:
        await kafka_producer.start()
    except Exception as e:
        logger.warning("Failed to start Kafka producer: %s", str(e))

    # Start Kafka consumers as background tasks
    consumer_tasks = []
    try:
        consumer_tasks = await start_consumers()
    except Exception as e:
        logger.warning("Failed to start Kafka consumers: %s", str(e))

    yield

    # Shutdown
    logger.info("Shutting down Mini Twitter service...")

    # Cancel consumer tasks
    for task in consumer_tasks:
        task.cancel()

    # Stop Kafka producer
    await kafka_producer.stop()

    # Close Redis
    await close_redis()

    logger.info("Shutdown complete.")


app = FastAPI(
    title="Mini Twitter",
    description="A production-grade, horizontally scalable Mini Twitter clone",
    version="1.0.0",
    lifespan=lifespan,
)

# Add rate limiter state
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """Handle rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded",
            "code": "RATE_LIMIT_EXCEEDED",
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handle unhandled exceptions."""
    logger.error("Unhandled exception: %s", str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "code": "INTERNAL_ERROR",
        },
    )


# Mount routers
app.include_router(users.router)
app.include_router(tweets.router)
app.include_router(timeline.router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": settings.SERVICE_NAME, "instance": settings.INSTANCE_ID}
