import logging
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # PostgreSQL
    POSTGRES_PRIMARY_URL: str = "postgresql+asyncpg://twitter:twitter@postgres_primary:5432/twitter"
    POSTGRES_REPLICA1_URL: str = "postgresql+asyncpg://twitter:twitter@postgres_replica1:5432/twitter"
    POSTGRES_REPLICA2_URL: str = "postgresql+asyncpg://twitter:twitter@postgres_replica2:5432/twitter"

    # Redis (main — timelines, sessions, rate limiting)
    REDIS_URL: str = "redis://redis:6379/0"

    # Redis Celebrity (SEPARATE dedicated instance — celebrity tweet store ONLY)
    CELEBRITY_REDIS_URL: str = "redis://redis_celebrity:6379/0"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"

    # Auth
    JWT_SECRET_KEY: str = "change_this_to_a_long_random_secret_key_at_least_32_chars"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # App
    LOG_LEVEL: str = "INFO"
    CELEBRITY_THRESHOLD: int = 10000

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 100

    # Service identification
    SERVICE_NAME: str = "user"
    INSTANCE_ID: int = 1

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
