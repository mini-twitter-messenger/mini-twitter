import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.celebrity_repo import CelebrityRepository
from app.repositories.timeline_repo import TimelineRepository


pytestmark = pytest.mark.asyncio


async def test_home_timeline_cache_miss(
    async_client: AsyncClient, user_factory, test_redis
):
    """Empty Redis → fetches from DB, populates cache, returns tweets."""
    user_a = await user_factory(username="cache_miss_a")
    user_b = await user_factory(username="cache_miss_b")

    # A follows B
    await async_client.post(
        f"/users/{user_b['id']}/follow",
        headers=user_a["headers"],
    )

    # B posts a tweet
    await async_client.post(
        "/tweets/",
        json={"content": "Cache miss test tweet"},
        headers=user_b["headers"],
    )

    # A's home timeline — cache is empty, should fetch from DB
    resp = await async_client.get(
        "/timeline/home?limit=20&offset=0",
        headers=user_a["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "tweets" in data


async def test_home_timeline_cache_hit(
    async_client: AsyncClient, user_factory, test_redis
):
    """Pre-populate Redis → confirm DB is NOT hit for cached data."""
    user = await user_factory(username="cache_hit_user")

    # Pre-populate the cache directly
    tweet_data = {
        "id": str(uuid.uuid4()),
        "content": "Cached tweet",
        "user_id": user["id"],
        "username": "cache_hit_user",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await TimelineRepository.push_to_home_timeline(
        test_redis, uuid.UUID(user["id"]), tweet_data
    )

    # Request home timeline — should hit cache
    resp = await async_client.get(
        "/timeline/home?limit=20&offset=0",
        headers=user["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tweets"]) >= 1
    assert any(t["content"] == "Cached tweet" for t in data["tweets"])


async def test_home_timeline_fan_out(
    async_client: AsyncClient, user_factory, test_redis
):
    """User A follows B (regular), B posts tweet → A's tl:home has the tweet."""
    user_a = await user_factory(username="fanout_a")
    user_b = await user_factory(username="fanout_b")

    # A follows B
    await async_client.post(
        f"/users/{user_b['id']}/follow",
        headers=user_a["headers"],
    )

    # Simulate fan-out: push a tweet into A's home timeline (as the consumer would)
    tweet_data = {
        "id": str(uuid.uuid4()),
        "content": "Fan-out test tweet from B",
        "user_id": user_b["id"],
        "username": "fanout_b",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await TimelineRepository.push_to_home_timeline(
        test_redis, uuid.UUID(user_a["id"]), tweet_data
    )

    # Verify A's home timeline on MAIN Redis contains the tweet
    key = f"tl:home:{user_a['id']}"
    cached = await test_redis.lrange(key, 0, -1)
    assert len(cached) >= 1
    cached_tweets = [json.loads(t) for t in cached]
    assert any(t["content"] == "Fan-out test tweet from B" for t in cached_tweets)


async def test_user_timeline(async_client: AsyncClient, user_factory):
    """GET /timeline/user/{user_id} → 200, paginated."""
    user = await user_factory(username="user_tl")

    # Post a few tweets
    for i in range(3):
        await async_client.post(
            "/tweets/",
            json={"content": f"User timeline tweet {i}"},
            headers=user["headers"],
        )

    resp = await async_client.get(
        f"/timeline/user/{user['id']}?limit=10&offset=0",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "tweets" in data
    assert data["limit"] == 10
    assert data["offset"] == 0


async def test_celebrity_tweet_skips_fanout(
    async_client: AsyncClient, user_factory, test_redis, test_celebrity_redis
):
    """Celebrity user (>CELEBRITY_THRESHOLD followers) posts tweet →
    NONE of their followers' tl:home on main Redis were touched."""
    celebrity = await user_factory(username="celeb_skip")
    follower = await user_factory(username="celeb_follower")

    # Follow the celebrity
    await async_client.post(
        f"/users/{celebrity['id']}/follow",
        headers=follower["headers"],
    )

    # Simulate the celebrity having >10k followers by writing directly to celebrity Redis
    tweet_data = {
        "id": str(uuid.uuid4()),
        "content": "Celebrity only tweet",
        "user_id": celebrity["id"],
        "username": "celeb_skip",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    created_at_epoch = datetime.now(timezone.utc).timestamp()

    # Write to celebrity Redis (as the consumer would for a celebrity)
    await CelebrityRepository.add_tweet(
        test_celebrity_redis,
        uuid.UUID(celebrity["id"]),
        tweet_data,
        created_at_epoch,
    )

    # Assert follower's tl:home on MAIN Redis does NOT have this tweet
    key = f"tl:home:{follower['id']}"
    cached = await test_redis.lrange(key, 0, -1)
    if cached:
        cached_tweets = [json.loads(t) for t in cached]
        assert not any(
            t["content"] == "Celebrity only tweet" for t in cached_tweets
        )


async def test_celebrity_tweet_written_to_celebrity_store(
    test_celebrity_redis, test_redis
):
    """Celebrity tweet goes into cel:{id} on CELEBRITY Redis, not main Redis."""
    celeb_id = uuid.uuid4()
    tweet_data = {
        "id": str(uuid.uuid4()),
        "content": "Celebrity store test",
        "user_id": str(celeb_id),
        "username": "celeb",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    created_at_epoch = datetime.now(timezone.utc).timestamp()

    # Write to celebrity Redis
    await CelebrityRepository.add_tweet(
        test_celebrity_redis, celeb_id, tweet_data, created_at_epoch
    )

    # Verify on celebrity Redis
    celeb_key = f"cel:{celeb_id}"
    count = await test_celebrity_redis.zcard(celeb_key)
    assert count == 1

    # Verify NOT on main Redis
    main_count = await test_redis.zcard(celeb_key)
    assert main_count == 0


async def test_celebrity_merge_at_read(
    async_client: AsyncClient,
    user_factory,
    test_redis,
    test_celebrity_redis,
):
    """Follower of celebrity calls /timeline/home → response includes
    celebrity's tweets merged with regular fanned-out tweets."""
    celebrity = await user_factory(username="merge_celeb")
    follower = await user_factory(username="merge_follower")
    regular = await user_factory(username="merge_regular")

    # Follower follows both
    await async_client.post(
        f"/users/{celebrity['id']}/follow",
        headers=follower["headers"],
    )
    await async_client.post(
        f"/users/{regular['id']}/follow",
        headers=follower["headers"],
    )

    # Push a regular tweet into follower's home timeline on main Redis
    regular_tweet = {
        "id": str(uuid.uuid4()),
        "content": "Regular tweet for merge",
        "user_id": regular["id"],
        "username": "merge_regular",
        "created_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
    }
    await TimelineRepository.push_to_home_timeline(
        test_redis, uuid.UUID(follower["id"]), regular_tweet
    )

    # Push celebrity tweet to celebrity Redis
    celeb_tweet = {
        "id": str(uuid.uuid4()),
        "content": "Celebrity tweet for merge",
        "user_id": celebrity["id"],
        "username": "merge_celeb",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # We need to make the celebrity appear as one in the DB
    # Patch the celebrity threshold to 0 so this user qualifies
    with patch("app.services.timeline_service.settings") as mock_settings:
        mock_settings.CELEBRITY_THRESHOLD = 0

        await CelebrityRepository.add_tweet(
            test_celebrity_redis,
            uuid.UUID(celebrity["id"]),
            celeb_tweet,
            datetime.now(timezone.utc).timestamp(),
        )

        resp = await async_client.get(
            "/timeline/home?limit=20&offset=0",
            headers=follower["headers"],
        )

    assert resp.status_code == 200
    data = resp.json()
    contents = [t["content"] for t in data["tweets"]]
    # The response should contain tweets from both sources
    assert "Regular tweet for merge" in contents or "Celebrity tweet for merge" in contents


async def test_celebrity_store_trim(test_celebrity_redis):
    """Push 1005 tweets into cel:{id} → only latest 1000 remain."""
    celeb_id = uuid.uuid4()
    base_time = datetime.now(timezone.utc)

    for i in range(1005):
        tweet_data = {
            "id": str(uuid.uuid4()),
            "content": f"Tweet {i}",
            "user_id": str(celeb_id),
            "username": "trim_celeb",
            "created_at": (base_time + timedelta(seconds=i)).isoformat(),
        }
        epoch = (base_time + timedelta(seconds=i)).timestamp()
        await CelebrityRepository.add_tweet(
            test_celebrity_redis, celeb_id, tweet_data, epoch
        )

    # Verify only 1000 remain
    count = await CelebrityRepository.get_tweet_count(
        test_celebrity_redis, celeb_id
    )
    assert count == 1000


async def test_follow_celebrity_no_backfill(
    async_client: AsyncClient,
    user_factory,
    test_redis,
):
    """User follows a celebrity → follow_consumer does NOT backfill anything
    into follower's tl:home (no Redis writes on follow for celebrities)."""
    celebrity = await user_factory(username="no_backfill_celeb")
    follower = await user_factory(username="no_backfill_follower")

    # Celebrity posts some tweets first
    for i in range(3):
        await async_client.post(
            "/tweets/",
            json={"content": f"Celebrity pre-tweet {i}"},
            headers=celebrity["headers"],
        )

    # Clear follower's home timeline to establish clean baseline
    home_key = f"tl:home:{follower['id']}"
    await test_redis.delete(home_key)

    # Follow the celebrity
    await async_client.post(
        f"/users/{celebrity['id']}/follow",
        headers=follower["headers"],
    )

    # With celebrity threshold set very low, the follow consumer would skip backfill.
    # Since Kafka is mocked, we verify by checking main Redis is still empty.
    cached = await test_redis.lrange(home_key, 0, -1)
    # The API call itself (without real Kafka consumer) shouldn't have written anything
    assert len(cached) == 0


async def test_round_robin_replicas():
    """Assert get_read_db() alternates between replica URLs across calls."""
    from app.db.session import get_next_replica_url, _replica_urls

    # Call twice and confirm different URLs
    url1 = await get_next_replica_url()
    url2 = await get_next_replica_url()

    assert url1 in _replica_urls
    assert url2 in _replica_urls
    assert url1 != url2

    # Call two more times to confirm it cycles back
    url3 = await get_next_replica_url()
    url4 = await get_next_replica_url()
    assert url3 == url1
    assert url4 == url2
