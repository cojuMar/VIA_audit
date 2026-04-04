import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/framework-service'))

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime

from src.compliance_scorer import ComplianceScorer
from src.models import ComplianceScore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _status_row(status: str, cnt: int) -> dict:
    return {"status": status, "cnt": cnt}


def _make_pool(total: int = 10, status_rows: list = None,
               framework_name: str = "SOC 2 Type II",
               active_frameworks: list = None):
    """
    Build a mock pool that satisfies ComplianceScorer's query pattern:
      1. execute (SET LOCAL)
      2. fetchval  -> framework name
      3. fetchval  -> total controls count
      4. fetch     -> status_counts rows
    Then an execute for the INSERT snapshot.
    """
    conn = AsyncMock()

    if status_rows is None:
        status_rows = [_status_row("passing", total)]

    # sequence of fetchval calls: first = framework name, second = total count
    conn.fetchval = AsyncMock(side_effect=[framework_name, total])
    conn.fetch = AsyncMock(return_value=status_rows)
    conn.execute = AsyncMock(return_value=None)

    if active_frameworks is not None:
        # compute_all_tenant_scores uses fetch for active frameworks
        conn.fetch = AsyncMock(return_value=active_frameworks)

    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


def _make_scoring_pool(total: int, status_rows: list, framework_name: str = "SOC 2 Type II"):
    """Convenience: returns (pool, conn) wired for compute_score()."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=[framework_name, total])
    conn.fetch = AsyncMock(return_value=status_rows)
    conn.execute = AsyncMock(return_value=None)

    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


# ---------------------------------------------------------------------------
# TestComplianceScorer
# ---------------------------------------------------------------------------

class TestComplianceScorer:

    @pytest.mark.asyncio
    async def test_score_100_when_all_passing(self):
        status_rows = [_status_row("passing", 10)]
        pool, _ = _make_scoring_pool(total=10, status_rows=status_rows)
        scorer = ComplianceScorer(pool)

        score = await scorer.compute_score(uuid4(), uuid4())

        assert score.score_pct == 100.0

    @pytest.mark.asyncio
    async def test_score_0_when_all_failing(self):
        status_rows = [_status_row("failing", 10)]
        pool, _ = _make_scoring_pool(total=10, status_rows=status_rows)
        scorer = ComplianceScorer(pool)

        score = await scorer.compute_score(uuid4(), uuid4())

        assert score.score_pct == 0.0

    @pytest.mark.asyncio
    async def test_score_50_when_half_passing(self):
        status_rows = [_status_row("passing", 5), _status_row("failing", 5)]
        pool, _ = _make_scoring_pool(total=10, status_rows=status_rows)
        scorer = ComplianceScorer(pool)

        score = await scorer.compute_score(uuid4(), uuid4())

        assert score.score_pct == 50.0

    @pytest.mark.asyncio
    async def test_not_applicable_excluded_from_denominator(self):
        """8 passing + 2 not_applicable = denominator of 8, score 100%."""
        status_rows = [
            _status_row("passing", 8),
            _status_row("not_applicable", 2),
        ]
        pool, _ = _make_scoring_pool(total=10, status_rows=status_rows)
        scorer = ComplianceScorer(pool)

        score = await scorer.compute_score(uuid4(), uuid4())

        assert score.score_pct == 100.0

    @pytest.mark.asyncio
    async def test_exception_counts_as_half(self):
        """4 passing + 2 exception + 4 not_started out of 10 = (4+1)/10 = 50%."""
        status_rows = [
            _status_row("passing", 4),
            _status_row("exception", 2),
            _status_row("not_started", 4),
        ]
        pool, _ = _make_scoring_pool(total=10, status_rows=status_rows)
        scorer = ComplianceScorer(pool)

        score = await scorer.compute_score(uuid4(), uuid4())

        assert score.score_pct == 50.0

    @pytest.mark.asyncio
    async def test_score_snapshot_persisted(self):
        """compute_score() must INSERT exactly one row into compliance_scores."""
        status_rows = [_status_row("passing", 5), _status_row("failing", 5)]
        pool, conn = _make_scoring_pool(total=10, status_rows=status_rows)
        scorer = ComplianceScorer(pool)

        await scorer.compute_score(uuid4(), uuid4())

        insert_calls = [
            c for c in conn.execute.call_args_list
            if "INSERT INTO compliance_scores" in str(c)
        ]
        assert len(insert_calls) == 1

        # Verify the score_pct argument passed to the INSERT
        call_args = insert_calls[0][0]
        # Positional args: (tenant_id, framework_id, score_pct, passing, failing, not_started, total)
        score_pct_arg = call_args[2]
        assert score_pct_arg == 50.0

    @pytest.mark.asyncio
    async def test_zero_applicable_controls_returns_100(self):
        """All not_applicable → denominator = 0 → score = 100%."""
        status_rows = [_status_row("not_applicable", 10)]
        pool, _ = _make_scoring_pool(total=10, status_rows=status_rows)
        scorer = ComplianceScorer(pool)

        score = await scorer.compute_score(uuid4(), uuid4())

        assert score.score_pct == 100.0

    @pytest.mark.asyncio
    async def test_score_result_has_all_fields(self):
        status_rows = [_status_row("passing", 7), _status_row("failing", 3)]
        pool, _ = _make_scoring_pool(total=10, status_rows=status_rows)
        scorer = ComplianceScorer(pool)

        score = await scorer.compute_score(uuid4(), uuid4())

        assert hasattr(score, "framework_id")
        assert hasattr(score, "score_pct")
        assert hasattr(score, "passing_controls")
        assert hasattr(score, "failing_controls")
        assert hasattr(score, "not_started_controls")
        assert hasattr(score, "total_controls")
        assert hasattr(score, "computed_at")
        assert isinstance(score.computed_at, datetime)


# ---------------------------------------------------------------------------
# TestComplianceScorerEdgeCases
# ---------------------------------------------------------------------------

class TestComplianceScorerEdgeCases:

    @pytest.mark.asyncio
    async def test_score_rounded_to_2_decimal_places(self):
        """1 passing out of 3 → 33.33...% should be rounded to 33.33."""
        status_rows = [_status_row("passing", 1), _status_row("failing", 2)]
        pool, _ = _make_scoring_pool(total=3, status_rows=status_rows)
        scorer = ComplianceScorer(pool)

        score = await scorer.compute_score(uuid4(), uuid4())

        assert score.score_pct == 33.33

    @pytest.mark.asyncio
    async def test_multiple_frameworks_scored_independently(self):
        """compute_all_tenant_scores for 3 active frameworks returns 3 scores."""
        fw_ids = [uuid4(), uuid4(), uuid4()]
        active_fw_rows = [{"framework_id": fid} for fid in fw_ids]

        # The outer pool.acquire is used for listing active frameworks.
        # compute_score() itself calls pool.acquire again for each framework.
        # We wire the pool so each acquire() call gets a fresh conn that
        # satisfies either the framework-list fetch or the scoring queries.

        call_count = {"n": 0}
        all_conns = []

        def make_conn_for_call():
            call_count["n"] += 1
            c = AsyncMock()
            if call_count["n"] == 1:
                # First acquire: list active frameworks
                c.fetch = AsyncMock(return_value=active_fw_rows)
                c.execute = AsyncMock(return_value=None)
            else:
                # Subsequent acquires: compute_score for each framework
                c.fetchval = AsyncMock(side_effect=["Framework Name", 10])
                c.fetch = AsyncMock(return_value=[_status_row("passing", 10)])
                c.execute = AsyncMock(return_value=None)
            all_conns.append(c)
            return c

        pool = MagicMock()

        def new_acquire():
            ctx = MagicMock()
            ctx.__aenter__ = AsyncMock(return_value=make_conn_for_call())
            ctx.__aexit__ = AsyncMock(return_value=False)
            return ctx

        pool.acquire = MagicMock(side_effect=new_acquire)

        scorer = ComplianceScorer(pool)
        results = await scorer.compute_all_tenant_scores(uuid4())

        assert len(results) == 3
        assert all(isinstance(s, ComplianceScore) for s in results)
