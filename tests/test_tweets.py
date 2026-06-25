import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


async def test_create_tweet_success(async_client: AsyncClient, user_factory):
    """POST /tweets/ → 201, tweet returned."""
    user = await user_factory(username="tweeter")

    resp = await async_client.post(
        "/tweets/",
        json={"content": "Hello, Mini Twitter!"},
        headers=user["headers"],
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["content"] == "Hello, Mini Twitter!"
    assert data["user_id"] == user["id"]
    assert "id" in data
    assert "created_at" in data


async def test_create_tweet_too_long(async_client: AsyncClient, user_factory):
    """POST /tweets/ with > 280 chars → 422."""
    user = await user_factory(username="long_tweeter")

    long_content = "x" * 281
    resp = await async_client.post(
        "/tweets/",
        json={"content": long_content},
        headers=user["headers"],
    )
    assert resp.status_code == 422


async def test_create_tweet_unauthenticated(async_client: AsyncClient):
    """POST /tweets/ without auth → 401."""
    resp = await async_client.post(
        "/tweets/",
        json={"content": "This should fail"},
    )
    assert resp.status_code == 401


async def test_delete_tweet_owner(async_client: AsyncClient, user_factory):
    """DELETE /tweets/{tweet_id} by owner → 204."""
    user = await user_factory(username="deleter")

    # Create tweet
    create_resp = await async_client.post(
        "/tweets/",
        json={"content": "To be deleted"},
        headers=user["headers"],
    )
    tweet_id = create_resp.json()["id"]

    # Delete
    resp = await async_client.delete(
        f"/tweets/{tweet_id}",
        headers=user["headers"],
    )
    assert resp.status_code == 204

    # Confirm gone
    get_resp = await async_client.get(f"/tweets/{tweet_id}")
    assert get_resp.status_code == 404


async def test_delete_tweet_non_owner(async_client: AsyncClient, user_factory):
    """DELETE /tweets/{tweet_id} by non-owner → 403."""
    owner = await user_factory(username="tweet_owner")
    other = await user_factory(username="not_owner")

    # Owner creates tweet
    create_resp = await async_client.post(
        "/tweets/",
        json={"content": "Owner's tweet"},
        headers=owner["headers"],
    )
    tweet_id = create_resp.json()["id"]

    # Other tries to delete
    resp = await async_client.delete(
        f"/tweets/{tweet_id}",
        headers=other["headers"],
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["detail"]["code"] == "FORBIDDEN"


async def test_get_tweet(async_client: AsyncClient, user_factory):
    """GET /tweets/{tweet_id} → 200."""
    user = await user_factory(username="getter")

    create_resp = await async_client.post(
        "/tweets/",
        json={"content": "Fetchable tweet"},
        headers=user["headers"],
    )
    tweet_id = create_resp.json()["id"]

    resp = await async_client.get(f"/tweets/{tweet_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == tweet_id
    assert data["content"] == "Fetchable tweet"
