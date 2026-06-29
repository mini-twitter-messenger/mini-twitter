"""
user_agent.py — A single simulated user's behavior loop.

Each UserAgent:
  1. Registers a new account (or logs in if already exists)
  2. Loops N times: pick a weighted-random action → execute → sleep
  3. Shares discovered user_ids and tweet_ids with all other agents
     via the global SharedPools so they can interact with each other.
"""

import random
import asyncio
import logging
from dataclasses import dataclass, field

from api_client import MiniTwitterClient

logger = logging.getLogger("simulator.agent")

# ──────────── Tweet content corpus (realistic-ish) ────────────

TWEET_TEMPLATES = [
    "Just deployed a new microservice! 🚀",
    "Working on my DBMS project, distributed systems are fascinating",
    "Hot take: PostgreSQL > everything else for OLTP",
    "Kafka fan-out on write is so elegant once you get it",
    "Morning coffee and code reviews ☕",
    "Redis sorted sets are underrated data structures",
    "Anyone else love async Python? FastAPI + uvicorn = 🔥",
    "Scaling to 10k followers should trigger the celebrity path",
    "Read replicas really help with timeline queries",
    "The timeline fanout architecture is similar to how real Twitter works",
    "Just learned about KRaft mode — no more Zookeeper dependency!",
    "Clean architecture patterns: repository → service → router",
    "Horizontal scaling is the way. Docker Compose makes it easy",
    "Eventual consistency is fine for timelines tbh",
    "gRPC or REST? For this project REST all the way",
    "Mini Twitter load test running... fingers crossed 🤞",
    "Rate limiting is important — 100 req/min per user",
    "JWT tokens expire in 24h, that's pretty generous",
    "The dual-Redis setup (main + celebrity) is a smart optimization",
    "Nginx least_conn balancing across 3 instances per service",
    "asyncio + aiohttp = perfect for concurrent user simulation",
    "Database indexing makes or breaks query performance",
    "Streaming replication lag should stay under 100ms ideally",
    "Fan-out on write vs fan-out on read — classic tradeoff",
    "Building this at {time} — late night coding session",
    "User #{user_index} checking in! Everything running smooth",
    "Following some interesting accounts today",
    "My timeline is getting busier — the simulation is working!",
    "Testing edge cases: what happens with 280 character tweets?",
    "Microservices are great until you need distributed transactions",
]

SEARCH_QUERIES = [
    "sim_user_", "sim_user_1", "sim_user_5", "sim_user_9",
    "user", "sim", "test",
]


@dataclass
class SharedPools:
    """
    Global pools of discovered resources. All user agents read from
    and append to these. Safe in single-threaded asyncio.
    """
    user_ids: list[str] = field(default_factory=list)
    usernames: list[str] = field(default_factory=list)
    tweet_ids: list[str] = field(default_factory=list)
    my_tweets: dict[str, list[str]] = field(default_factory=dict)  # user_id → [tweet_ids]


class UserAgent:
    """
    Simulates one concurrent user performing random actions
    against the Mini Twitter API.
    """

    def __init__(
        self,
        index: int,
        client: MiniTwitterClient,
        pools: SharedPools,
        config: dict,
    ) -> None:
        self.index = index
        self.client = client
        self.pools = pools
        self.config = config

        # Identity
        prefix = config["users"]["username_prefix"]
        domain = config["users"]["email_domain"]
        self.username = f"{prefix}{index}"
        self.email = f"{prefix}{index}@{domain}"
        self.password = config["users"]["password"]
        self.user_id: str | None = None

        # Action config
        self.actions_per_user = config["simulation"]["actions_per_user"]
        self.delay_min = config["simulation"]["delay_min_seconds"]
        self.delay_max = config["simulation"]["delay_max_seconds"]

        # Build weighted action list
        weights_cfg = config["action_weights"]
        self.actions: list[str] = list(weights_cfg.keys())
        self.weights: list[int] = [weights_cfg[a] for a in self.actions]

        self.client.username = self.username

    async def setup(self) -> bool:
        """Register and login. Returns True if successful."""
        # Register (may fail if user already exists — that's fine)
        status, data, _ = await self.client.register(
            self.username, self.email, self.password
        )
        if status == 201 and data:
            self.user_id = str(data.get("id", ""))
            logger.debug("%s registered (id=%s)", self.username, self.user_id)
        elif status in (400, 409, 422):
            # Already exists or validation error — try to login anyway
            logger.debug("%s registration returned %d, attempting login", self.username, status)
        else:
            logger.warning("%s registration failed: %d %s", self.username, status, data)

        # Login
        status, data, _ = await self.client.login(self.username, self.password)
        if status != 200:
            logger.error("%s login failed: %d %s", self.username, status, data)
            return False

        # If we didn't get user_id from register, extract from token or search
        if not self.user_id:
            # The JWT sub claim has the user_id; we'll get it from profile search
            status2, data2, _ = await self.client.search_users(self.username, limit=1)
            if status2 == 200 and data2 and len(data2) > 0:
                self.user_id = str(data2[0].get("id", ""))

        if self.user_id:
            self.pools.user_ids.append(self.user_id)
            self.pools.usernames.append(self.username)
            self.pools.my_tweets[self.user_id] = []

        logger.info("%s ready (id=%s)", self.username, self.user_id)
        return True

    async def run(self) -> None:
        """Main behavior loop: perform N random actions with delays."""
        await self.client.metrics.user_started()
        try:
            if not await self.setup():
                logger.error("%s could not authenticate — skipping", self.username)
                return

            for i in range(self.actions_per_user):
                action = random.choices(self.actions, weights=self.weights, k=1)[0]
                try:
                    await self._execute_action(action)
                except Exception as exc:
                    logger.error("%s action %s crashed: %s", self.username, action, exc)

                # Random delay between actions
                delay = random.uniform(self.delay_min, self.delay_max)
                await asyncio.sleep(delay)

        finally:
            await self.client.metrics.user_finished()

    # ──────────── Action dispatcher ────────────

    async def _execute_action(self, action: str) -> None:
        handler = getattr(self, f"_action_{action}", None)
        if handler:
            await handler()
        else:
            logger.warning("%s unknown action: %s", self.username, action)

    # ──────────── Individual actions ────────────

    async def _action_create_tweet(self) -> None:
        template = random.choice(TWEET_TEMPLATES)
        content = template.format(
            time=asyncio.get_event_loop().time(),
            user_index=self.index,
        )
        # Ensure ≤280 chars
        content = content[:280]

        status, data, _ = await self.client.create_tweet(content)
        if status == 201 and data and "id" in data:
            tweet_id = str(data["id"])
            self.pools.tweet_ids.append(tweet_id)
            if self.user_id:
                self.pools.my_tweets.setdefault(self.user_id, []).append(tweet_id)

    async def _action_home_timeline(self) -> None:
        limit = random.choice([10, 20, 50])
        await self.client.home_timeline(limit=limit, offset=0)

    async def _action_user_timeline(self) -> None:
        target = self._random_user_id()
        if target:
            limit = random.choice([10, 20])
            await self.client.user_timeline(target, limit=limit)

    async def _action_get_profile(self) -> None:
        target = self._random_user_id()
        if target:
            await self.client.get_profile(target)

    async def _action_follow_user(self) -> None:
        target = self._random_other_user_id()
        if target:
            await self.client.follow_user(target)

    async def _action_unfollow_user(self) -> None:
        target = self._random_other_user_id()
        if target:
            await self.client.unfollow_user(target)

    async def _action_get_tweet(self) -> None:
        if self.pools.tweet_ids:
            tweet_id = random.choice(self.pools.tweet_ids)
            await self.client.get_tweet(tweet_id)

    async def _action_delete_tweet(self) -> None:
        if self.user_id and self.pools.my_tweets.get(self.user_id):
            tweet_id = self.pools.my_tweets[self.user_id].pop(0)
            # Also remove from global pool if present
            if tweet_id in self.pools.tweet_ids:
                try:
                    self.pools.tweet_ids.remove(tweet_id)
                except ValueError:
                    pass
            await self.client.delete_tweet(tweet_id)

    async def _action_search_users(self) -> None:
        query = random.choice(SEARCH_QUERIES)
        await self.client.search_users(query, limit=random.choice([5, 10, 20]))

    async def _action_get_followers(self) -> None:
        target = self._random_user_id()
        if target:
            await self.client.get_followers(target, limit=20)

    async def _action_get_following(self) -> None:
        target = self._random_user_id()
        if target:
            await self.client.get_following(target, limit=20)

    # ──────────── Helpers ────────────

    def _random_user_id(self) -> str | None:
        """Pick any random user from the pool."""
        if self.pools.user_ids:
            return random.choice(self.pools.user_ids)
        return self.user_id

    def _random_other_user_id(self) -> str | None:
        """Pick a random user that is NOT this user."""
        others = [uid for uid in self.pools.user_ids if uid != self.user_id]
        if others:
            return random.choice(others)
        return None
