"""
Sprint 7 — Rate Limiter Tests

Tests the sliding window rate limiter. Uses a mock Redis client
to avoid requiring a real Redis connection in unit tests.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/rag-pipeline-service'))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


def make_limiter():
    """Return a SlidingWindowRateLimiter backed by a mock Redis client."""
    mock_redis = MagicMock()
    with patch.dict(os.environ, {
        'DATABASE_URL': 'postgresql://localhost/dummy',
        'KAFKA_BOOTSTRAP_SERVERS': 'localhost:9092',
        'ANTHROPIC_API_KEY': 'dummy',
        'VOYAGE_API_KEY': 'dummy',
    }):
        from src.rate_limiter import SlidingWindowRateLimiter
        from src.config import settings
        limiter = SlidingWindowRateLimiter(mock_redis, settings)
    return limiter, mock_redis


def make_pipeline_mock(zcard_return: int):
    """Return a mock Redis pipeline whose ZCARD returns zcard_return."""
    pipeline = MagicMock()
    pipeline.__aenter__ = AsyncMock(return_value=pipeline)
    pipeline.__aexit__ = AsyncMock(return_value=False)
    pipeline.zremrangebyscore = MagicMock()
    pipeline.zadd = MagicMock()
    pipeline.zcard = MagicMock()
    pipeline.expire = MagicMock()
    pipeline.execute = AsyncMock(return_value=[None, None, zcard_return, None])
    return pipeline


# ---------------------------------------------------------------------------
# Endpoint limit configuration
# ---------------------------------------------------------------------------

class TestRateLimiterLimits:

    def test_default_limit_is_100(self):
        limiter, _ = make_limiter()
        assert limiter._get_limit('/unknown/path') == 100

    def test_generate_endpoint_limit_is_20(self):
        limiter, _ = make_limiter()
        assert limiter._get_limit('/narratives/generate') == 20

    def test_search_endpoint_limit_is_200(self):
        limiter, _ = make_limiter()
        assert limiter._get_limit('/narratives/search') == 200

    def test_embeddings_endpoint_limit_is_50(self):
        limiter, _ = make_limiter()
        assert limiter._get_limit('/embeddings/index') == 50


# ---------------------------------------------------------------------------
# Sliding window behaviour
# ---------------------------------------------------------------------------

class TestSlidingWindow:

    @pytest.mark.asyncio
    async def test_first_request_allowed(self):
        limiter, mock_redis = make_limiter()
        # ZCARD returns 0 — no prior requests in window
        pipeline = make_pipeline_mock(zcard_return=0)
        mock_redis.pipeline = MagicMock(return_value=pipeline)

        result = await limiter.check(
            tenant_id='tenant-1',
            endpoint='/narratives/generate',
        )
        assert result.allowed is True
        # remaining = limit - current_count_after_adding (1) = 20 - 1 = 19
        limit = limiter._get_limit('/narratives/generate')
        assert result.remaining == limit - 1

    @pytest.mark.asyncio
    async def test_request_at_limit_blocked(self):
        limiter, mock_redis = make_limiter()
        limit = limiter._get_limit('/narratives/generate')
        # ZCARD returns exactly the limit — window is full
        pipeline = make_pipeline_mock(zcard_return=limit)
        mock_redis.pipeline = MagicMock(return_value=pipeline)

        result = await limiter.check(
            tenant_id='tenant-1',
            endpoint='/narratives/generate',
        )
        assert result.allowed is False
        assert result.retry_after > 0

    @pytest.mark.asyncio
    async def test_request_below_limit_allowed(self):
        limiter, mock_redis = make_limiter()
        limit = limiter._get_limit('/narratives/generate')
        # ZCARD returns limit - 1 (one slot still free before this request)
        pipeline = make_pipeline_mock(zcard_return=limit - 1)
        mock_redis.pipeline = MagicMock(return_value=pipeline)

        result = await limiter.check(
            tenant_id='tenant-1',
            endpoint='/narratives/generate',
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_remaining_decrements(self):
        limiter, mock_redis = make_limiter()
        limit = limiter._get_limit('/narratives/generate')
        existing_count = 5
        pipeline = make_pipeline_mock(zcard_return=existing_count)
        mock_redis.pipeline = MagicMock(return_value=pipeline)

        result = await limiter.check(
            tenant_id='tenant-1',
            endpoint='/narratives/generate',
        )
        # remaining = limit - existing_count - 1 (this request was just added)
        assert result.remaining == limit - existing_count - 1

    @pytest.mark.asyncio
    async def test_redis_connection_error_allows_request(self):
        limiter, mock_redis = make_limiter()
        pipeline = MagicMock()
        pipeline.__aenter__ = AsyncMock(return_value=pipeline)
        pipeline.__aexit__ = AsyncMock(return_value=False)
        pipeline.execute = AsyncMock(side_effect=ConnectionError("Redis unavailable"))
        mock_redis.pipeline = MagicMock(return_value=pipeline)

        result = await limiter.check(
            tenant_id='tenant-1',
            endpoint='/narratives/generate',
        )
        # Fail-open: when Redis is unreachable the request must be allowed
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_reset_at_is_in_future(self):
        limiter, mock_redis = make_limiter()
        pipeline = make_pipeline_mock(zcard_return=0)
        mock_redis.pipeline = MagicMock(return_value=pipeline)

        result = await limiter.check(
            tenant_id='tenant-1',
            endpoint='/narratives/generate',
        )
        assert result.reset_at > datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Key isolation between tenants and endpoints
# ---------------------------------------------------------------------------

class TestRateLimiterKeyIsolation:

    @pytest.mark.asyncio
    async def test_different_tenants_have_different_keys(self):
        limiter, mock_redis = make_limiter()

        captured_keys = []

        def capture_pipeline():
            pipeline = make_pipeline_mock(zcard_return=0)
            original_zremrange = pipeline.zremrangebyscore

            def track_key(key, *args, **kwargs):
                captured_keys.append(key)

            pipeline.zremrangebyscore = track_key
            return pipeline

        mock_redis.pipeline = MagicMock(side_effect=capture_pipeline)

        await limiter.check(tenant_id='tenant-alpha', endpoint='/narratives/generate')
        await limiter.check(tenant_id='tenant-beta', endpoint='/narratives/generate')

        assert len(captured_keys) == 2
        assert captured_keys[0] != captured_keys[1]
        assert 'tenant-alpha' in captured_keys[0]
        assert 'tenant-beta' in captured_keys[1]

    @pytest.mark.asyncio
    async def test_different_endpoints_have_different_keys(self):
        limiter, mock_redis = make_limiter()

        captured_keys = []

        def capture_pipeline():
            pipeline = make_pipeline_mock(zcard_return=0)

            def track_key(key, *args, **kwargs):
                captured_keys.append(key)

            pipeline.zremrangebyscore = track_key
            return pipeline

        mock_redis.pipeline = MagicMock(side_effect=capture_pipeline)

        await limiter.check(tenant_id='tenant-1', endpoint='/narratives/generate')
        await limiter.check(tenant_id='tenant-1', endpoint='/narratives/search')

        assert len(captured_keys) == 2
        assert captured_keys[0] != captured_keys[1]
