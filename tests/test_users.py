import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


async def test_register_success(async_client: AsyncClient):
    """POST /users/register → 201, user returned."""
    resp = await async_client.post(
        "/users/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "secret123",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "alice"
    assert data["email"] == "alice@example.com"
    assert "id" in data
    assert data["follower_count"] == 0


async def test_register_duplicate_username(async_client: AsyncClient):
    """POST /users/register with duplicate username → 400."""
    await async_client.post(
        "/users/register",
        json={
            "username": "bob",
            "email": "bob1@example.com",
            "password": "secret123",
        },
    )
    resp = await async_client.post(
        "/users/register",
        json={
            "username": "bob",
            "email": "bob2@example.com",
            "password": "secret123",
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["detail"]["code"] == "DUPLICATE_USERNAME"


async def test_login_success(async_client: AsyncClient):
    """POST /users/login → 200, access_token present."""
    await async_client.post(
        "/users/register",
        json={
            "username": "charlie",
            "email": "charlie@example.com",
            "password": "secret123",
        },
    )
    resp = await async_client.post(
        "/users/login",
        json={"username": "charlie", "password": "secret123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password(async_client: AsyncClient):
    """POST /users/login with wrong password → 401."""
    await async_client.post(
        "/users/register",
        json={
            "username": "dave",
            "email": "dave@example.com",
            "password": "secret123",
        },
    )
    resp = await async_client.post(
        "/users/login",
        json={"username": "dave", "password": "wrong_password"},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert data["detail"]["code"] == "INVALID_CREDENTIALS"


async def test_follow_user(async_client: AsyncClient, user_factory):
    """POST /users/{user_id}/follow → 200, follow relation exists."""
    user_a = await user_factory(username="follower_a")
    user_b = await user_factory(username="followee_b")

    resp = await async_client.post(
        f"/users/{user_b['id']}/follow",
        headers=user_a["headers"],
    )
    assert resp.status_code == 200

    # Verify the follow relation by checking followers list
    followers_resp = await async_client.get(
        f"/users/{user_b['id']}/followers",
    )
    assert followers_resp.status_code == 200
    followers_data = followers_resp.json()
    follower_ids = [u["id"] for u in followers_data["users"]]
    assert user_a["id"] in follower_ids


async def test_follow_self(async_client: AsyncClient, user_factory):
    """POST /users/{user_id}/follow (self) → 400."""
    user = await user_factory(username="self_follow")

    resp = await async_client.post(
        f"/users/{user['id']}/follow",
        headers=user["headers"],
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["detail"]["code"] == "SELF_FOLLOW"


async def test_unfollow_user(async_client: AsyncClient, user_factory):
    """DELETE /users/{user_id}/follow → 200, relation gone."""
    user_a = await user_factory(username="unfollower_a")
    user_b = await user_factory(username="unfollowee_b")

    # Follow first
    await async_client.post(
        f"/users/{user_b['id']}/follow",
        headers=user_a["headers"],
    )

    # Unfollow
    resp = await async_client.delete(
        f"/users/{user_b['id']}/follow",
        headers=user_a["headers"],
    )
    assert resp.status_code == 200

    # Verify gone
    followers_resp = await async_client.get(
        f"/users/{user_b['id']}/followers",
    )
    followers_data = followers_resp.json()
    follower_ids = [u["id"] for u in followers_data["users"]]
    assert user_a["id"] not in follower_ids


async def test_get_followers_list(async_client: AsyncClient, user_factory):
    """GET /users/{user_id}/followers → 200, paginated."""
    user_a = await user_factory(username="lister_a")
    user_b = await user_factory(username="lister_b")
    user_c = await user_factory(username="lister_c")

    # B and C follow A
    await async_client.post(
        f"/users/{user_a['id']}/follow",
        headers=user_b["headers"],
    )
    await async_client.post(
        f"/users/{user_a['id']}/follow",
        headers=user_c["headers"],
    )

    resp = await async_client.get(
        f"/users/{user_a['id']}/followers?limit=10&offset=0",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["users"]) == 2
    assert data["limit"] == 10
    assert data["offset"] == 0
