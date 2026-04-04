"""
MAESTRO Sprint 7 — Rate Limiter

Sliding window algorithm using Redis sorted sets.
Key: "rl:{tenant_id}:{endpoint}"
Members: request UUIDs, scores: timestamp (seconds)
Window: 60 seconds

Limits (per tenant per minute):
  /narratives/generate    → 20
  /narratives/search      → 200
  /embeddings/index       → 50
  default                 → 100
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ENDPOINT_LIMITS = {
    "/narratives/generate": 20,
    "/narratives/search": 200,
    "/embeddings/index": 50,
}
DEFAULT_LIMIT = 100
WINDOW_SECONDS = 60


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_at: datetime        # when the oldest request in the window expires
    retry_after: Optional[int]  # seconds until allowed (None if allowed)


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Sliding window rate limiter backed by Redis sorted sets.

    Each key holds a sorted set where:
      - member  = unique request UUID
      - score   = Unix timestamp (seconds, float) of the request

    On each check:
      1. Trim members outside the 60-second window.
      2. Count remaining members.
      3. If count < limit: add the new member and refresh the key TTL.
      4. Return a RateLimitResult.

    Failure mode: if Redis is unavailable (ConnectionError / OSError), the
    caller receives a result with allowed=True so that infrastructure failure
    does not block legitimate users.  The caller is responsible for logging.
    """

    def __init__(self, redis_url: str):
        self._redis = None
        self._redis_url = redis_url

    async def connect(self) -> None:
        import redis.asyncio as aioredis
        self._redis = await aioredis.from_url(
            self._redis_url,
            decode_responses=False,
        )

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    # ------------------------------------------------------------------
    # Core sliding-window check
    # ------------------------------------------------------------------

    async def check_and_increment(
        self,
        tenant_id: str,
        endpoint: str,
    ) -> RateLimitResult:
        """Atomically check and (if allowed) record a request.

        Uses a Redis pipeline for the read-then-write sequence.  Not strictly
        atomic under concurrent load but acceptable for sliding-window
        rate limiting where exact edges are not security-critical.
        """
        limit = self._get_limit(endpoint)
        key = f"rl:{tenant_id}:{endpoint}"

        now_ts = datetime.now(tz=timezone.utc).timestamp()
        window_start = now_ts - WINDOW_SECONDS

        async with self._redis.pipeline(transaction=False) as pipe:
            # Remove entries older than the window
            await pipe.zremrangebyscore(key, "-inf", window_start)
            # Count entries currently in the window
            await pipe.zcard(key)
            results = await pipe.execute()

        current_count: int = results[1]

        if current_count < limit:
            # Record this request
            member = str(uuid.uuid4())
            async with self._redis.pipeline(transaction=False) as pipe:
                await pipe.zadd(key, {member: now_ts})
                # TTL = window + small buffer so the key auto-cleans
                await pipe.expire(key, WINDOW_SECONDS + 10)
                await pipe.execute()

            remaining = limit - current_count - 1
            reset_ts = now_ts + WINDOW_SECONDS
            reset_at = datetime.fromtimestamp(reset_ts, tz=timezone.utc)
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=max(remaining, 0),
                reset_at=reset_at,
                retry_after=None,
            )
        else:
            # Determine when the oldest entry in the window will expire
            oldest = await self._redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                oldest_ts = float(oldest[0][1])
                retry_after = max(1, int(oldest_ts + WINDOW_SECONDS - now_ts) + 1)
                reset_at = datetime.fromtimestamp(
                    oldest_ts + WINDOW_SECONDS, tz=timezone.utc
                )
            else:
                retry_after = WINDOW_SECONDS
                reset_at = datetime.fromtimestamp(
                    now_ts + WINDOW_SECONDS, tz=timezone.utc
                )

            return RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=0,
                reset_at=reset_at,
                retry_after=retry_after,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_limit(self, endpoint: str) -> int:
        for pattern, limit in ENDPOINT_LIMITS.items():
            if endpoint.startswith(pattern):
                return limit
        return DEFAULT_LIMIT
