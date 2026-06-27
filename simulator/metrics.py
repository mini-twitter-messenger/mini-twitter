"""
metrics.py — Thread-safe (asyncio-safe) metrics collection for the simulator.

Tracks total requests, success/failure counts, per-endpoint latencies,
active user count, and error logs. Provides snapshots for the live
dashboard and a final summary at the end of the run.
"""

import time
import asyncio
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class EndpointStats:
    """Accumulated stats for a single endpoint / action type."""
    count: int = 0
    success: int = 0
    fail: int = 0
    latencies: list[float] = field(default_factory=list)

    @property
    def avg_ms(self) -> float:
        return sum(self.latencies) / len(self.latencies) if self.latencies else 0.0

    @property
    def min_ms(self) -> float:
        return min(self.latencies) if self.latencies else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.latencies) if self.latencies else 0.0

    @property
    def p95_ms(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_lats = sorted(self.latencies)
        idx = int(len(sorted_lats) * 0.95)
        return sorted_lats[min(idx, len(sorted_lats) - 1)]


@dataclass
class ErrorRecord:
    """A single recorded error."""
    timestamp: str
    user: str
    action: str
    status: int
    detail: str


class SimulatorMetrics:
    """
    Central metrics collector. All user agents write to this.
    Safe for single-threaded asyncio (no threading locks needed).
    """

    def __init__(self) -> None:
        self.start_time: float = time.time()
        self.total_requests: int = 0
        self.success_count: int = 0
        self.failure_count: int = 0
        self.all_latencies: list[float] = []
        self.active_users: int = 0
        self.peak_active_users: int = 0
        self.errors: list[ErrorRecord] = []
        self.per_endpoint: dict[str, EndpointStats] = defaultdict(EndpointStats)
        self._lock = asyncio.Lock()

    async def record_request(
        self,
        action: str,
        latency_ms: float,
        success: bool,
        user: str = "",
        status: int = 0,
        detail: str = "",
    ) -> None:
        """Record the outcome of a single API request."""
        async with self._lock:
            self.total_requests += 1
            self.all_latencies.append(latency_ms)

            ep = self.per_endpoint[action]
            ep.count += 1
            ep.latencies.append(latency_ms)

            if success:
                self.success_count += 1
                ep.success += 1
            else:
                self.failure_count += 1
                ep.fail += 1
                self.errors.append(ErrorRecord(
                    timestamp=time.strftime("%H:%M:%S"),
                    user=user,
                    action=action,
                    status=status,
                    detail=detail[:120],
                ))

    async def user_started(self) -> None:
        async with self._lock:
            self.active_users += 1
            if self.active_users > self.peak_active_users:
                self.peak_active_users = self.active_users

    async def user_finished(self) -> None:
        async with self._lock:
            self.active_users -= 1

    async def snapshot(self) -> dict:
        """Return a point-in-time snapshot for the dashboard."""
        async with self._lock:
            elapsed = max(time.time() - self.start_time, 0.001)
            lats = self.all_latencies
            sorted_lats = sorted(lats) if lats else [0.0]
            p95_idx = int(len(sorted_lats) * 0.95)

            return {
                "elapsed_s": round(elapsed, 1),
                "total": self.total_requests,
                "success": self.success_count,
                "fail": self.failure_count,
                "rps": round(self.total_requests / elapsed, 1),
                "avg_ms": round(sum(lats) / len(lats), 1) if lats else 0.0,
                "min_ms": round(min(lats), 1) if lats else 0.0,
                "max_ms": round(max(lats), 1) if lats else 0.0,
                "p95_ms": round(sorted_lats[min(p95_idx, len(sorted_lats) - 1)], 1),
                "active_users": self.active_users,
                "peak_users": self.peak_active_users,
                "recent_errors": [
                    f"[{e.timestamp}] {e.user} -> {e.action} -> {e.status}: {e.detail}"
                    for e in self.errors[-5:]
                ],
                "per_endpoint": {
                    name: {
                        "count": ep.count,
                        "fail": ep.fail,
                        "avg_ms": round(ep.avg_ms, 1),
                        "max_ms": round(ep.max_ms, 1),
                    }
                    for name, ep in sorted(self.per_endpoint.items())
                },
            }

    async def final_summary(self) -> dict:
        """Return the full end-of-run summary."""
        snap = await self.snapshot()
        async with self._lock:
            # Top 10 slowest
            indexed = [(lat, i) for i, lat in enumerate(self.all_latencies)]
            indexed.sort(key=lambda x: x[0], reverse=True)
            snap["top_slowest"] = [
                round(lat, 1) for lat, _ in indexed[:10]
            ]
            # Error summary by type
            error_types: dict[str, int] = defaultdict(int)
            for e in self.errors:
                key = f"{e.action} -> {e.status}"
                error_types[key] += 1
            snap["error_types"] = dict(sorted(error_types.items(), key=lambda x: -x[1]))
            snap["total_errors_list"] = [
                {"time": e.timestamp, "user": e.user, "action": e.action,
                 "status": e.status, "detail": e.detail}
                for e in self.errors
            ]
        return snap
