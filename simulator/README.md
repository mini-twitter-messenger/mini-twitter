# Mini Twitter — Async User Simulator

## Quick Start

```bash
# 1. Make sure the backend is running
cd ..
docker compose up --build -d

# 2. Install simulator dependencies (separate from the backend)
cd simulator
pip install -r requirements.txt

# 3. Run the simulator
python simulator.py
```

## Configuration

All tunables are in [`config.yaml`](config.yaml):

| Setting | Default | Description |
|---------|---------|-------------|
| `server.base_url` | `http://localhost:80` | Backend endpoint (Nginx) |
| `simulation.num_users` | `100` | Concurrent simulated users |
| `simulation.actions_per_user` | `30` | Actions per user before stopping |
| `simulation.delay_min_seconds` | `2` | Min pause between actions |
| `simulation.delay_max_seconds` | `10` | Max pause between actions |
| `simulation.ramp_up_seconds` | `10` | Time to stagger user starts |
| `action_weights.*` | various | Weighted random action selection |

## Architecture

```
simulator/
├── config.yaml       # All configuration
├── requirements.txt  # aiohttp, pyyaml, rich
├── simulator.py      # Entry point: orchestration + dashboard
├── api_client.py     # HTTP client wrapping all 14 endpoints
├── user_agent.py     # Single user behavior loop
└── metrics.py        # Metrics collection + snapshots
```

## API Endpoints Covered

The simulator exercises **all 14** implemented endpoints:

| Action | Endpoint | Weight |
|--------|----------|--------|
| `create_tweet` | `POST /tweets/` | 25 |
| `home_timeline` | `GET /timeline/home` | 20 |
| `user_timeline` | `GET /timeline/user/{id}` | 15 |
| `get_profile` | `GET /users/{id}/profile` | 10 |
| `follow_user` | `POST /users/{id}/follow` | 10 |
| `unfollow_user` | `DELETE /users/{id}/follow` | 5 |
| `get_tweet` | `GET /tweets/{id}` | 5 |
| `search_users` | `GET /users/search` | 5 |
| `delete_tweet` | `DELETE /tweets/{id}` | 2 |
| `get_followers` | `GET /users/{id}/followers` | 2 |
| `get_following` | `GET /users/{id}/following` | 1 |

Plus `register`, `login`, and `health` during setup.

## Live Dashboard

The simulator prints a live dashboard every 5 seconds showing:
- Uptime, active users, RPS
- Total/success/failure counts with percentages
- Latency stats (avg, min, max, P95)
- Per-endpoint breakdown table
- Recent errors

Uses `rich` for a styled terminal UI. Falls back to plain text if `rich` is not installed.

## Output

After the simulation completes:
- **Final summary** printed to terminal (full stats, top 10 slowest requests, error breakdown)
- **`errors.json`** written to the simulator directory with all error details

---

## Backend Monitoring Guide

While the simulator runs, use these commands in **separate terminals** to observe the backend:

### 1. Backend Logs
```bash
# All services
docker compose logs -f --tail=50

# Specific service
docker compose logs -f user_service_1
docker compose logs -f tweet_service_2
docker compose logs -f timeline_service_3
```

### 2. CPU & Memory (live)
```bash
docker stats
```

### 3. Database Activity
```bash
# Connect to PostgreSQL primary
docker compose exec postgres_primary psql -U twitter -d twitter

# Active queries
SELECT pid, state, query, query_start FROM pg_stat_activity WHERE datname='twitter';

# Row counts
SELECT 'users' AS tbl, count(*) FROM users
UNION ALL SELECT 'tweets', count(*) FROM tweets
UNION ALL SELECT 'followers', count(*) FROM followers;

# Replication lag
SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn
FROM pg_stat_replication;
```

### 4. Redis Activity
```bash
# Main Redis — watch all commands in real-time
docker compose exec redis redis-cli MONITOR

# Key statistics
docker compose exec redis redis-cli INFO keyspace
docker compose exec redis redis-cli INFO memory

# Check timeline cache keys
docker compose exec redis redis-cli KEYS "tl:*"

# Celebrity Redis
docker compose exec redis_celebrity redis-cli MONITOR
docker compose exec redis_celebrity redis-cli KEYS "cel:*"
```

### 5. Kafka Topics
```bash
# List topics
docker compose exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --list

# Watch tweet events
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic tweet.created --from-beginning

# Consumer lag
docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --all-groups
```

### 6. Nginx Load Balancing
```bash
docker compose exec nginx tail -f /var/log/nginx/access.log
```
