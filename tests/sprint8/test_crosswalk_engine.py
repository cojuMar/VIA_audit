import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/framework-service'))

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.crosswalk_engine import CrosswalkEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool(fetch_return=None, fetchval_return=None, execute_return=None):
    """Build a mock asyncpg-style pool with a context-manager acquire()."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=fetch_return or [])
    conn.fetchval = AsyncMock(return_value=fetchval_return)
    conn.execute = AsyncMock(return_value=execute_return)

    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


def _row(overrides: dict):
    """Return a dict that behaves like an asyncpg Record (dict-compatible)."""
    defaults = {
        "id": uuid4(),
        "framework_id": uuid4(),
        "control_id": "CC1.1",
        "domain": "Security (CC)",
        "title": "Access Control",
        "framework_name": "SOC 2 Type II",
        "slug": "soc2-type2",
        "equivalence_type": "full",
        "notes": None,
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# TestCrosswalkCoverage
# ---------------------------------------------------------------------------

class TestCrosswalkCoverage:

    @pytest.mark.asyncio
    async def test_get_equivalent_controls_returns_list(self):
        rows = [_row({"equivalence_type": "full"}),
                _row({"equivalence_type": "partial"}),
                _row({"equivalence_type": "related"})]
        pool, conn = _make_pool(fetch_return=rows)
        engine = CrosswalkEngine(pool)

        result = await engine.get_equivalent_controls(uuid4())

        assert isinstance(result, list)
        assert len(result) == 3
        for item in result:
            assert "id" in item
            assert "framework_name" in item
            assert "equivalence_type" in item

    @pytest.mark.asyncio
    async def test_full_equivalence_credited_on_apply(self):
        eq1 = _row({"equivalence_type": "full"})
        eq2 = _row({"equivalence_type": "full"})
        pool, conn = _make_pool(fetch_return=[eq1, eq2])
        engine = CrosswalkEngine(pool)

        credited = await engine.apply_crosswalk_credit(uuid4(), uuid4(), uuid4())

        assert credited == 2
        assert conn.execute.call_count >= 2  # at least one INSERT per full-equiv entry

    @pytest.mark.asyncio
    async def test_partial_equivalence_not_auto_credited(self):
        partial1 = _row({"equivalence_type": "partial"})
        partial2 = _row({"equivalence_type": "partial"})
        pool, conn = _make_pool(fetch_return=[partial1, partial2])
        engine = CrosswalkEngine(pool)

        credited = await engine.apply_crosswalk_credit(uuid4(), uuid4(), uuid4())

        assert credited == 0
        # No INSERT into tenant_control_evidence for partial entries
        insert_calls = [
            c for c in conn.execute.call_args_list
            if "INSERT INTO tenant_control_evidence" in str(c)
        ]
        assert len(insert_calls) == 0

    @pytest.mark.asyncio
    async def test_no_equivalents_returns_zero(self):
        pool, conn = _make_pool(fetch_return=[])
        engine = CrosswalkEngine(pool)

        result = await engine.apply_crosswalk_credit(uuid4(), uuid4(), uuid4())

        assert result == 0

    @pytest.mark.asyncio
    async def test_crosswalk_coverage_requires_two_frameworks(self):
        """Tenant with only 1 active framework should get an explanatory message."""
        single_fw = [{"framework_id": uuid4(), "name": "SOC 2 Type II", "slug": "soc2-type2"}]
        pool, conn = _make_pool(fetch_return=single_fw)
        engine = CrosswalkEngine(pool)

        result = await engine.get_tenant_crosswalk_coverage(uuid4())

        assert "Need at least 2 active frameworks" in result.get("message", "")
        assert result.get("pairs") == []

    @pytest.mark.asyncio
    async def test_crosswalk_coverage_two_frameworks(self):
        """Tenant with 2 active frameworks + 5 crosswalk pairs returns correct structure."""
        fw_a_id = uuid4()
        fw_b_id = uuid4()
        active_frameworks = [
            {"framework_id": fw_a_id, "name": "SOC 2 Type II", "slug": "soc2-type2"},
            {"framework_id": fw_b_id, "name": "ISO 27001", "slug": "iso27001"},
        ]

        pool, conn = _make_pool()
        # First call: active frameworks; second call: crosswalk pair count
        conn.fetch = AsyncMock(return_value=active_frameworks)
        conn.fetchval = AsyncMock(return_value=5)

        engine = CrosswalkEngine(pool)
        result = await engine.get_tenant_crosswalk_coverage(uuid4())

        assert len(result["pairs"]) == 1
        assert result["pairs"][0]["crosswalk_control_pairs"] == 5
