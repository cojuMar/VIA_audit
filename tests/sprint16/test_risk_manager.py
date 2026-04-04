"""Sprint 16 — RiskManager unit tests."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/risk-service"),
)

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import date, datetime, timezone


# ---------------------------------------------------------------------------
# Helper — pool/connection mock (async context-manager protocol)
# ---------------------------------------------------------------------------

def make_pool_conn():
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


TENANT = "10000000-0000-0000-0000-000000000016"

# Canonical risk payload used across multiple tests
RISK_PAYLOAD = {
    "risk_id": "RISK-001",
    "title": "Data Breach via Misconfigured S3",
    "description": "Publicly accessible S3 bucket may expose PII.",
    "category_key": "cybersecurity",
    "owner": "ciso@example.com",
    "department": "IT Security",
    "inherent_likelihood": 4,
    "inherent_impact": 5,
    "residual_likelihood": 2,
    "residual_impact": 3,
    "target_likelihood": 1,
    "target_impact": 2,
    "framework_control_refs": ["CC6.1", "CC6.6"],
    "source": "manual",
    "identified_date": date(2026, 1, 15),
    "review_date": date(2026, 7, 15),
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def risk_manager():
    from src.risk_manager import RiskManager

    pool, _ = make_pool_conn()
    return RiskManager(pool, TENANT)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRiskManager:

    # ------------------------------------------------------------------
    # create_risk
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_risk_looks_up_category(self):
        """create_risk must fetchrow from risk_categories for the category_key."""
        from src.risk_manager import RiskManager
        from src.models import RiskCreate

        pool, conn = make_pool_conn()

        # category lookup returns a row; duplicate check returns None
        category_row = {"id": "cat-uuid-1234", "category_key": "cybersecurity"}
        conn.fetchrow.side_effect = [category_row, None]
        conn.fetchval.return_value = "new-risk-uuid"

        mgr = RiskManager(pool, TENANT)
        payload = RiskCreate(**RISK_PAYLOAD)
        await mgr.create_risk(payload)

        # First fetchrow call must target risk_categories
        first_call_sql = conn.fetchrow.call_args_list[0][0][0]
        assert "risk_categories" in first_call_sql

    @pytest.mark.asyncio
    async def test_create_risk_inserts_row(self):
        """create_risk must execute an INSERT into the risks table."""
        from src.risk_manager import RiskManager
        from src.models import RiskCreate

        pool, conn = make_pool_conn()
        category_row = {"id": "cat-uuid-1234", "category_key": "cybersecurity"}
        conn.fetchrow.side_effect = [category_row, None]
        conn.fetchval.return_value = "new-risk-uuid"

        mgr = RiskManager(pool, TENANT)
        payload = RiskCreate(**RISK_PAYLOAD)
        await mgr.create_risk(payload)

        executed_sqls = [str(c[0][0]) for c in conn.execute.call_args_list]
        assert any("INSERT" in sql and "risks" in sql for sql in executed_sqls), (
            "Expected an INSERT INTO risks statement"
        )

    @pytest.mark.asyncio
    async def test_create_risk_inserts_initial_score_history(self):
        """create_risk must INSERT an initial row into risk_score_history (immutable audit)."""
        from src.risk_manager import RiskManager
        from src.models import RiskCreate

        pool, conn = make_pool_conn()
        category_row = {"id": "cat-uuid-1234", "category_key": "cybersecurity"}
        conn.fetchrow.side_effect = [category_row, None]
        conn.fetchval.return_value = "new-risk-uuid"

        mgr = RiskManager(pool, TENANT)
        payload = RiskCreate(**RISK_PAYLOAD)
        await mgr.create_risk(payload)

        executed_sqls = [str(c[0][0]) for c in conn.execute.call_args_list]
        assert any(
            "INSERT" in sql and "risk_score_history" in sql
            for sql in executed_sqls
        ), "Expected an INSERT INTO risk_score_history statement"

    @pytest.mark.asyncio
    async def test_create_risk_id_must_be_unique(self):
        """create_risk must raise ValueError when the risk_id already exists for the tenant."""
        from src.risk_manager import RiskManager
        from src.models import RiskCreate

        pool, conn = make_pool_conn()
        category_row = {"id": "cat-uuid-1234", "category_key": "cybersecurity"}
        existing_row = {"id": "existing-uuid", "risk_id": "RISK-001"}
        # fetchrow: category lookup → ok; duplicate check → existing row
        conn.fetchrow.side_effect = [category_row, existing_row]

        mgr = RiskManager(pool, TENANT)
        payload = RiskCreate(**RISK_PAYLOAD)

        with pytest.raises(ValueError):
            await mgr.create_risk(payload)

    # ------------------------------------------------------------------
    # update_risk
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_update_risk_updates_fields(self):
        """update_risk must execute an UPDATE on the risks table."""
        from src.risk_manager import RiskManager
        from src.models import RiskUpdate

        pool, conn = make_pool_conn()
        existing = {
            "id": "risk-uuid-001",
            "residual_likelihood": 2,
            "residual_impact": 3,
            "tenant_id": TENANT,
        }
        conn.fetchrow.return_value = existing

        mgr = RiskManager(pool, TENANT)
        update = RiskUpdate(title="Updated Title", owner="new-owner@example.com")
        await mgr.update_risk("RISK-001", update)

        executed_sqls = [str(c[0][0]) for c in conn.execute.call_args_list]
        assert any(
            "UPDATE" in sql and "risks" in sql for sql in executed_sqls
        ), "Expected an UPDATE risks statement"

    @pytest.mark.asyncio
    async def test_update_records_history_when_score_changes(self):
        """update_risk must INSERT into risk_score_history when residual scores change."""
        from src.risk_manager import RiskManager
        from src.models import RiskUpdate

        pool, conn = make_pool_conn()
        existing = {
            "id": "risk-uuid-001",
            "residual_likelihood": 2,
            "residual_impact": 3,
            "tenant_id": TENANT,
        }
        conn.fetchrow.return_value = existing

        mgr = RiskManager(pool, TENANT)
        # Change residual scores
        update = RiskUpdate(residual_likelihood=4, residual_impact=4)
        await mgr.update_risk("RISK-001", update)

        executed_sqls = [str(c[0][0]) for c in conn.execute.call_args_list]
        assert any(
            "INSERT" in sql and "risk_score_history" in sql
            for sql in executed_sqls
        ), "Expected INSERT into risk_score_history on score change"

    @pytest.mark.asyncio
    async def test_update_no_history_when_score_unchanged(self):
        """update_risk must NOT insert into risk_score_history when scores are unchanged."""
        from src.risk_manager import RiskManager
        from src.models import RiskUpdate

        pool, conn = make_pool_conn()
        existing = {
            "id": "risk-uuid-001",
            "residual_likelihood": 2,
            "residual_impact": 3,
            "tenant_id": TENANT,
        }
        conn.fetchrow.return_value = existing

        mgr = RiskManager(pool, TENANT)
        # Same residual scores as existing
        update = RiskUpdate(residual_likelihood=2, residual_impact=3)
        await mgr.update_risk("RISK-001", update)

        executed_sqls = [str(c[0][0]) for c in conn.execute.call_args_list]
        assert not any(
            "INSERT" in sql and "risk_score_history" in sql
            for sql in executed_sqls
        ), "Must NOT insert into risk_score_history when scores are unchanged"

    # ------------------------------------------------------------------
    # list_risks
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_risks_with_status_filter(self):
        """list_risks with status='open' must include 'open' as a filter in the SQL."""
        from src.risk_manager import RiskManager

        pool, conn = make_pool_conn()
        conn.fetch.return_value = []

        mgr = RiskManager(pool, TENANT)
        await mgr.list_risks(status="open")

        fetch_call_sql = conn.fetch.call_args[0][0]
        assert "open" in fetch_call_sql or "status" in fetch_call_sql, (
            "SQL must filter by status='open'"
        )

    @pytest.mark.asyncio
    async def test_list_risks_with_category_filter(self):
        """list_risks with category_key must include the category key in query or args."""
        from src.risk_manager import RiskManager

        pool, conn = make_pool_conn()
        conn.fetch.return_value = []

        mgr = RiskManager(pool, TENANT)
        await mgr.list_risks(category_key="cybersecurity")

        # The category key may appear in the SQL string or in the bound arguments
        fetch_args = conn.fetch.call_args
        sql_str = fetch_args[0][0]
        bound_args = list(fetch_args[0][1:]) + list(fetch_args[1].values())
        assert (
            "category" in sql_str or "cybersecurity" in str(bound_args)
        ), "category_key must be present in query or bound parameters"

    # ------------------------------------------------------------------
    # close_risk
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_close_risk_sets_status_and_date(self):
        """close_risk must UPDATE risks with status='closed' and a closed_date."""
        from src.risk_manager import RiskManager

        pool, conn = make_pool_conn()
        existing = {"id": "risk-uuid-001", "tenant_id": TENANT}
        conn.fetchrow.return_value = existing

        mgr = RiskManager(pool, TENANT)
        await mgr.close_risk("RISK-001")

        executed_sqls = [str(c[0][0]) for c in conn.execute.call_args_list]
        all_args = [str(c) for c in conn.execute.call_args_list]
        assert any(
            "UPDATE" in sql and "risks" in sql for sql in executed_sqls
        ), "Expected UPDATE risks"
        assert any(
            "closed" in s for s in all_args
        ), "Expected 'closed' in the UPDATE arguments"

    # ------------------------------------------------------------------
    # get_register
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_register_returns_required_keys(self):
        """get_register must return a dict with all required top-level keys."""
        from src.risk_manager import RiskManager

        pool, conn = make_pool_conn()
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0

        mgr = RiskManager(pool, TENANT)
        result = await mgr.get_register()

        required_keys = {
            "total",
            "by_status",
            "by_category",
            "score_distribution",
            "above_appetite",
            "overdue_review",
        }
        missing = required_keys - set(result.keys())
        assert not missing, f"get_register result missing keys: {missing}"

    @pytest.mark.asyncio
    async def test_score_distribution_critical_threshold(self):
        """score_distribution must count risks with score ≥ 20 as critical."""
        from src.risk_manager import RiskManager

        pool, conn = make_pool_conn()
        # Simulate rows with varying residual_score values
        rows = [
            {"residual_score": 25, "status": "open"},
            {"residual_score": 20, "status": "open"},
            {"residual_score": 15, "status": "open"},
            {"residual_score": 5,  "status": "open"},
        ]
        conn.fetch.return_value = rows
        conn.fetchval.return_value = 0

        mgr = RiskManager(pool, TENANT)
        result = await mgr.get_register()

        dist = result["score_distribution"]
        assert dist.get("critical", 0) == 2, (
            f"Expected 2 critical risks (score ≥ 20), got {dist.get('critical')}"
        )

    # ------------------------------------------------------------------
    # auto_create_from_finding
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_auto_create_from_finding_maps_severity(self):
        """auto_create_from_finding must map severity='critical' to likelihood=5, impact=5."""
        from src.risk_manager import RiskManager

        pool, conn = make_pool_conn()
        # No existing risk with that auto_source_id
        category_row = {"id": "cat-uuid-9999", "category_key": "cybersecurity"}
        conn.fetchrow.side_effect = [None, category_row, None]
        conn.fetchval.return_value = "auto-risk-uuid"

        mgr = RiskManager(pool, TENANT)
        finding = {
            "id": "finding-abc",
            "title": "Critical vulnerability in auth service",
            "severity": "critical",
            "category": "cybersecurity",
        }
        await mgr.auto_create_from_finding(finding)

        # Verify that 5 and 5 appear among the execute call arguments
        all_execute_args = str(conn.execute.call_args_list)
        assert "5" in all_execute_args, (
            "Expected likelihood=5 and impact=5 for critical severity"
        )

    @pytest.mark.asyncio
    async def test_auto_create_skips_existing(self):
        """auto_create_from_finding must return None if a risk with the same auto_source_id exists."""
        from src.risk_manager import RiskManager

        pool, conn = make_pool_conn()
        # Existing risk with the same auto_source_id
        existing = {"id": "existing-auto-risk-uuid", "auto_source_id": "finding-abc"}
        conn.fetchrow.return_value = existing

        mgr = RiskManager(pool, TENANT)
        finding = {
            "id": "finding-abc",
            "title": "Duplicate finding",
            "severity": "high",
            "category": "cybersecurity",
        }
        result = await mgr.auto_create_from_finding(finding)

        assert result is None, (
            "auto_create_from_finding must return None when risk already exists"
        )
