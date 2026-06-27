"""
api_client.py — Async HTTP client wrapping every Mini Twitter API endpoint.

Each method returns (status_code, response_data, latency_ms).
The client automatically injects the Bearer token when provided.
Metrics are recorded for every request.
"""

import time
import httpx
from typing import Any, Optional

from metrics import SimulatorMetrics


class MiniTwitterClient:
    """
    Async HTTP wrapper for all Mini Twitter API endpoints.

    One instance per simulated user. Shares an httpx.AsyncClient
    from the pool but maintains its own JWT token.
    """

    def __init__(
        self,
        session: httpx.AsyncClient,
        base_url: str,
        metrics: SimulatorMetrics,
        username: str = "",
    ) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.metrics = metrics
        self.username = username
        self.token: Optional[str] = None

    def _headers(self, auth: bool = False) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        action: str,
        auth: bool = False,
        json_body: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> tuple[int, Any, float]:
        """
        Execute an HTTP request and record metrics.
        Returns (status_code, response_json_or_None, latency_ms).
        """
        url = f"{self.base_url}{path}"
        start = time.perf_counter()
        status = 0
        data = None
        try:
            resp = await self.session.request(
                method,
                url,
                json=json_body,
                params=params,
                headers=self._headers(auth),
            )
            status = resp.status_code
            if "application/json" in resp.headers.get("content-type", ""):
                data = resp.json()
            else:
                data = resp.text
        except Exception as exc:
            status = 0
            data = {"detail": str(exc)}
        finally:
            latency = (time.perf_counter() - start) * 1000  # ms

        success = 200 <= status < 300
        detail = ""
        if not success and data:
            detail = str(data.get("detail", data) if isinstance(data, dict) else data)

        await self.metrics.record_request(
            action=action,
            latency_ms=latency,
            success=success,
            user=self.username,
            status=status,
            detail=detail,
        )
        return status, data, latency

    # ──────────────────── Health ────────────────────

    async def health(self) -> tuple[int, Any, float]:
        return await self._request("GET", "/health", "health")

    # ──────────────────── Users ────────────────────

    async def register(
        self, username: str, email: str, password: str
    ) -> tuple[int, Any, float]:
        return await self._request(
            "POST", "/users/register", "register",
            json_body={"username": username, "email": email, "password": password},
        )

    async def login(
        self, username: str, password: str
    ) -> tuple[int, Any, float]:
        status, data, latency = await self._request(
            "POST", "/users/login", "login",
            json_body={"username": username, "password": password},
        )
        if status == 200 and data and "access_token" in data:
            self.token = data["access_token"]
        return status, data, latency

    async def search_users(
        self, query: str, limit: int = 20
    ) -> tuple[int, Any, float]:
        return await self._request(
            "GET", "/users/search", "search_users",
            params={"q": query, "limit": limit},
        )

    async def get_profile(self, user_id: str) -> tuple[int, Any, float]:
        return await self._request(
            "GET", f"/users/{user_id}/profile", "get_profile",
        )

    async def follow_user(self, user_id: str) -> tuple[int, Any, float]:
        return await self._request(
            "POST", f"/users/{user_id}/follow", "follow_user", auth=True,
        )

    async def unfollow_user(self, user_id: str) -> tuple[int, Any, float]:
        return await self._request(
            "DELETE", f"/users/{user_id}/follow", "unfollow_user", auth=True,
        )

    async def get_followers(
        self, user_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[int, Any, float]:
        return await self._request(
            "GET", f"/users/{user_id}/followers", "get_followers",
            params={"limit": limit, "offset": offset},
        )

    async def get_following(
        self, user_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[int, Any, float]:
        return await self._request(
            "GET", f"/users/{user_id}/following", "get_following",
            params={"limit": limit, "offset": offset},
        )

    # ──────────────────── Tweets ────────────────────

    async def create_tweet(self, content: str) -> tuple[int, Any, float]:
        return await self._request(
            "POST", "/tweets/", "create_tweet", auth=True,
            json_body={"content": content},
        )

    async def delete_tweet(self, tweet_id: str) -> tuple[int, Any, float]:
        return await self._request(
            "DELETE", f"/tweets/{tweet_id}", "delete_tweet", auth=True,
        )

    async def get_tweet(self, tweet_id: str) -> tuple[int, Any, float]:
        return await self._request(
            "GET", f"/tweets/{tweet_id}", "get_tweet",
        )

    # ──────────────────── Timeline ────────────────────

    async def home_timeline(
        self, limit: int = 20, offset: int = 0
    ) -> tuple[int, Any, float]:
        return await self._request(
            "GET", "/timeline/home", "home_timeline", auth=True,
            params={"limit": limit, "offset": offset},
        )

    async def user_timeline(
        self, user_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[int, Any, float]:
        return await self._request(
            "GET", f"/timeline/user/{user_id}", "user_timeline",
            params={"limit": limit, "offset": offset},
        )
