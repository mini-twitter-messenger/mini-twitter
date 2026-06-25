import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base
from app.services.auth_service import AuthService


# ---------------------------------------------------------------------------
# Test database (SQLite async for unit tests)
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

test_session_factory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(autouse=True)
async def test_db():
    """Create and tear down test database tables for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a test database session."""
    async with test_session_factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Test Redis (two separate fakeredis instances — main + celebrity)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def test_redis():
    """MAIN Redis — separate fakeredis instance for regular timelines."""
    server = fakeredis.aioredis.FakeServer()
    client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


@pytest_asyncio.fixture
async def test_celebrity_redis():
    """CELEBRITY Redis — separate fakeredis instance. Does NOT share state with test_redis."""
    server = fakeredis.aioredis.FakeServer()
    client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


# ---------------------------------------------------------------------------
# FastAPI async test client
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def async_client(
    test_redis, test_celebrity_redis
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient pointed at the test FastAPI app with overridden dependencies."""
    # Import here to avoid module-level import of settings
    from app.main import app
    from app.dependencies import (
        get_write_db,
        get_read_db,
        get_redis,
        get_celebrity_redis,
    )

    async def override_write_db():
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def override_read_db():
        async with test_session_factory() as session:
            yield session

    async def override_get_redis():
        return test_redis

    async def override_get_celebrity_redis():
        return test_celebrity_redis

    app.dependency_overrides[get_write_db] = override_write_db
    app.dependency_overrides[get_read_db] = override_read_db
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_celebrity_redis] = override_get_celebrity_redis

    # Mock Kafka producer to avoid real Kafka connections
    with patch("app.services.tweet_service.kafka_producer") as mock_tweet_prod, \
         patch("app.services.user_service.kafka_producer") as mock_user_prod:
        mock_tweet_prod.send = AsyncMock()
        mock_user_prod.send = AsyncMock()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# User factory helper
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def user_factory(async_client: AsyncClient):
    """Factory to create and return a registered + logged-in test user with JWT."""
    _counter = 0

    async def _create_user(
        username: str = None,
        email: str = None,
        password: str = "testpass123",
    ) -> dict:
        nonlocal _counter
        _counter += 1
        if username is None:
            username = f"testuser_{_counter}_{uuid.uuid4().hex[:6]}"
        if email is None:
            email = f"{username}@test.com"

        # Register
        reg_resp = await async_client.post(
            "/users/register",
            json={"username": username, "email": email, "password": password},
        )
        assert reg_resp.status_code == 201, f"Registration failed: {reg_resp.text}"
        user_data = reg_resp.json()

        # Login
        login_resp = await async_client.post(
            "/users/login",
            json={"username": username, "password": password},
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token_data = login_resp.json()

        return {
            "id": user_data["id"],
            "username": username,
            "email": email,
            "access_token": token_data["access_token"],
            "headers": {"Authorization": f"Bearer {token_data['access_token']}"},
        }

    return _create_user
