# Mini Twitter

A production-grade, horizontally scalable Mini Twitter clone built with Python 3.11, FastAPI, PostgreSQL (1 primary + 2 read replicas), Redis, Apache Kafka, and Nginx.

## Quick Start

```bash
git clone <repo-url>
cd mini-twitter
cp .env.example .env
docker compose up --build
```

API available at **http://localhost:80**

## Services

| Service                              | Instances | Port (internal) |
|--------------------------------------|-----------|-----------------|
| User Service                         | 3         | 8000            |
| Tweet Service                        | 3         | 8000            |
| Timeline Service                     | 3         | 8000            |
| Nginx (reverse proxy / load balancer)| 1         | 80 (public)     |
| PostgreSQL Primary                   | 1         | 5432            |
| PostgreSQL Replica 1                 | 1         | 5433            |
| PostgreSQL Replica 2                 | 1         | 5434            |
| Redis (main)                         | 1         | 6379            |
| Redis (celebrity, separate container)| 1         | 6380 → 6379     |
| Kafka (KRaft)                        | 1         | 9092            |
| Kafka UI                             | 1         | 8080            |

## API Reference

### Auth

#### Register
```bash
curl -X POST http://localhost/users/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "email": "alice@example.com", "password": "secret123"}'
```

#### Login
```bash
curl -X POST http://localhost/users/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret123"}'
```

### Users

#### Get Profile
```bash
curl http://localhost/users/{user_id}/profile
```

#### Follow a User
```bash
curl -X POST http://localhost/users/{user_id}/follow \
  -H "Authorization: Bearer <token>"
```

#### Unfollow a User
```bash
curl -X DELETE http://localhost/users/{user_id}/follow \
  -H "Authorization: Bearer <token>"
```

#### List Followers
```bash
curl "http://localhost/users/{user_id}/followers?limit=20&offset=0"
```

#### List Following
```bash
curl "http://localhost/users/{user_id}/following?limit=20&offset=0"
```

### Tweets

#### Create Tweet
```bash
curl -X POST http://localhost/tweets/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"content": "Hello, Mini Twitter!"}'
```

#### Delete Tweet
```bash
curl -X DELETE http://localhost/tweets/{tweet_id} \
  -H "Authorization: Bearer <token>"
```

#### Get Tweet
```bash
curl http://localhost/tweets/{tweet_id}
```

### Timeline

#### Home Timeline
```bash
curl "http://localhost/timeline/home?limit=20&offset=0" \
  -H "Authorization: Bearer <token>"
```

#### User Timeline
```bash
curl "http://localhost/timeline/user/{user_id}?limit=20&offset=0"
```

## Environment Variables

| Variable                             | Description                                      | Default                                                          |
|--------------------------------------|--------------------------------------------------|------------------------------------------------------------------|
| `POSTGRES_PRIMARY_URL`               | Primary PostgreSQL connection URL                | `postgresql+asyncpg://twitter:twitter@postgres_primary:5432/twitter` |
| `POSTGRES_REPLICA1_URL`              | Read replica 1 connection URL                    | `postgresql+asyncpg://twitter:twitter@postgres_replica1:5432/twitter` |
| `POSTGRES_REPLICA2_URL`              | Read replica 2 connection URL                    | `postgresql+asyncpg://twitter:twitter@postgres_replica2:5432/twitter` |
| `REDIS_URL`                          | Main Redis (timelines, rate limiting)            | `redis://redis:6379/0`                                           |
| `CELEBRITY_REDIS_URL`                | Celebrity Redis (dedicated, separate container)  | `redis://redis_celebrity:6379/0`                                 |
| `KAFKA_BOOTSTRAP_SERVERS`            | Kafka bootstrap servers                          | `kafka:9092`                                                     |
| `JWT_SECRET_KEY`                     | Secret key for JWT HS256 signing                 | (change in production)                                           |
| `JWT_ALGORITHM`                      | JWT algorithm                                    | `HS256`                                                          |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`    | JWT token expiry in minutes                      | `1440` (24 hours)                                                |
| `LOG_LEVEL`                          | Python logging level                             | `INFO`                                                           |
| `CELEBRITY_THRESHOLD`                | Follower count above which a user is a celebrity | `10000`                                                          |
| `RATE_LIMIT_PER_MINUTE`              | Max API requests per minute per user/IP          | `100`                                                            |
| `SERVICE_NAME`                       | Service identifier (user/tweet/timeline)         | `user`                                                           |
| `INSTANCE_ID`                        | Instance number for logging                      | `1`                                                              |

## Architecture Notes

- **Read queries round-robin** between replica1 and replica2 using `asyncio.Lock` + `itertools.cycle`
- **Fan-out on write** for users with ≤10,000 followers (pushes tweets into each follower's `tl:home:{user_id}` on the main Redis)
- **Celebrity users** (>10,000 followers) are never fanned out on write — their tweets go into a **dedicated, separate Redis container** (the Celebrity Tweet Store: `cel:{celebrity_id}` sorted sets) and are merged into each follower's home timeline at read time
- **Two physically separate Redis containers**: `redis` (main timelines, rate limits) and `redis_celebrity` (celebrity tweet store only) — isolated to prevent celebrity fan-in from starving the regular cache
- **Kafka (KRaft, no Zookeeper)** handles async fan-out via `tweet.created`, `follow.created`, and `follow.deleted` topics
- **Nginx** load-balances 3 instances per service using `least_conn` strategy
- **No like/unlike functionality** — out of scope for this build
- **All async** — no blocking I/O anywhere in the app layer (AsyncSession, redis.asyncio, aiokafka)
- **Repository pattern** — zero raw SQL or Redis commands in routers or services

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Running Migrations

```bash
alembic upgrade head
```
