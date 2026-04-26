"""Sprint 12 — PolicyManager unit tests."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/people-service"),
)

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.policy_manager import PolicyManager
from src.models import AcknowledgmentRecord, PolicyCreate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT = "00000000-0000-0000-0000-000000000002"
POLICY_ID = "bbbb0000-0000-0000-0000-000000000001"
EMPLOYEE_ID = "E001"

_POLICY_DICT = {
    "id": POLICY_ID,
    "tenant_id": TENANT,
    "policy_key": "sec-001",
    "title": "Information Security Policy",
    "description": "Security guidelines",
    "category": "security",
    "applies_to_roles": ["all"],
    "applies_to_departments": [],
    "current_version": "1.0",
    "acknowledgment_required": True,
    "acknowledgment_frequency_days": 365,
    "is_active": True,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
}

_UPDATED_POLICY_DICT = dict(_POLICY_DICT, current_version="1.1", title="Updated Security Policy")

_ACK_DICT = {
    "id": "cccc0000-0000-0000-0000-000000000001",
    "tenant_id": TENANT,
    "policy_id": POLICY_ID,
    "employee_id": EMPLOYEE_ID,
    "policy_version": "1.0",
    "acknowledged_at": datetime.now(timezone.utc),
    "acknowledgment_method": "portal",
}


def make_policy(**kwargs):
    defaults = dict(
        policy_key="sec-001",
        title="Information Security Policy",
        description=None,
        category="security",
        applies_to_roles=["all"],
        applies_to_departments=[],
        acknowledgment_required=True,
        acknowledgment_frequency_days=365,
    )
    defaults.update(kwargs)
    return PolicyCreate(**defaults)


def make_ack(**kwargs):
    defaults = dict(
        policy_id=POLICY_ID,
        employee_id=EMPLOYEE_ID,
        policy_version="1.0",
        acknowledgment_method="portal",
    )
    defaults.update(kwargs)
    return AcknowledgmentRecord(**defaults)


def make_pool_with_conn(conn):
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def make_transactional_conn():
    """Return a conn mock that supports async context manager transaction()."""
    conn = AsyncMock()
    tx = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    return conn


# ---------------------------------------------------------------------------
# TestPolicyManager
# ---------------------------------------------------------------------------


class TestPolicyManager:

    @pytest.mark.asyncio
    async def test_create_policy_inserts_and_creates_version(self):
        """create_policy() must INSERT into policies AND policy_versions."""
        conn = make_transactional_conn()
        conn.fetchrow = AsyncMock(return_value=_POLICY_DICT)
        conn.execute = AsyncMock(return_value=None)
        pool = make_pool_with_conn(conn)

        mgr = PolicyManager()
        await mgr.create_policy(pool, TENANT, make_policy())

        # fetchrow for the policy INSERT
        conn.fetchrow.assert_called_once()
        policy_query = conn.fetchrow.call_args[0][0]
        assert "INSERT INTO" in policy_query

        # execute for the version INSERT
        conn.execute.assert_called_once()
        version_query = conn.execute.call_args[0][0]
        assert "INSERT INTO policy_versions" in version_query

    @pytest.mark.asyncio
    async def test_create_policy_returns_dict_with_id(self):
        """create_policy() returns a dict containing an 'id' key."""
        conn = make_transactional_conn()
        conn.fetchrow = AsyncMock(return_value=_POLICY_DICT)
        conn.execute = AsyncMock(return_value=None)
        pool = make_pool_with_conn(conn)

        mgr = PolicyManager()
        result = await mgr.create_policy(pool, TENANT, make_policy())

        assert "id" in result

    @pytest.mark.asyncio
    async def test_update_policy_inserts_new_version_only(self):
        """update_policy() inserts a new policy_version; never UPDATE on policy_versions."""
        conn = make_transactional_conn()
        # First fetchrow: SELECT current policy
        # Second fetchrow: UPDATE policies RETURNING *
        conn.fetchrow = AsyncMock(side_effect=[_POLICY_DICT, _UPDATED_POLICY_DICT])
        conn.execute = AsyncMock(return_value=None)
        pool = make_pool_with_conn(conn)

        mgr = PolicyManager()
        await mgr.update_policy(
            pool, TENANT, POLICY_ID,
            {"title": "Updated Security Policy"},
            "Revised for compliance",
        )

        # execute must have been called for INSERT INTO policy_versions
        execute_queries = [c[0][0] for c in conn.execute.call_args_list]
        version_inserts = [q for q in execute_queries if "INSERT INTO policy_versions" in q]
        assert len(version_inserts) >= 1

        # Must NOT have UPDATE or DELETE on policy_versions
        bad_ops = [
            q for q in execute_queries
            if ("UPDATE policy_versions" in q or "DELETE FROM policy_versions" in q)
        ]
        assert len(bad_ops) == 0

    @pytest.mark.asyncio
    async def test_version_increments_minor(self):
        """After update_policy, returned dict has version '1.1' (was '1.0')."""
        conn = make_transactional_conn()
        conn.fetchrow = AsyncMock(side_effect=[_POLICY_DICT, _UPDATED_POLICY_DICT])
        conn.execute = AsyncMock(return_value=None)
        pool = make_pool_with_conn(conn)

        mgr = PolicyManager()
        result = await mgr.update_policy(
            pool, TENANT, POLICY_ID, {}, "Minor update"
        )

        assert result["current_version"] == "1.1"

    @pytest.mark.asyncio
    async def test_record_acknowledgment_is_immutable_insert(self):
        """record_acknowledgment() uses INSERT; must not call UPDATE or DELETE."""
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=_ACK_DICT)
        pool = make_pool_with_conn(conn)

        mgr = PolicyManager()
        await mgr.record_acknowledgment(
            pool, TENANT, make_ack(), "127.0.0.1", "TestAgent/1.0"
        )

        # The only database call is fetchrow (INSERT RETURNING)
        conn.fetchrow.assert_called_once()
        query = conn.fetchrow.call_args[0][0]
        assert "INSERT INTO policy_acknowledgments" in query

        # No execute calls containing UPDATE/DELETE
        for c in conn.execute.call_args_list:
            q = c[0][0]
            assert "UPDATE policy_acknowledgments" not in q
            assert "DELETE FROM policy_acknowledgments" not in q

    @pytest.mark.asyncio
    async def test_record_acknowledgment_returns_record(self):
        """record_acknowledgment() returns a dict containing 'acknowledged_at'."""
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=_ACK_DICT)
        pool = make_pool_with_conn(conn)

        mgr = PolicyManager()
        result = await mgr.record_acknowledgment(
            pool, TENANT, make_ack(), "127.0.0.1", "TestAgent/1.0"
        )

        assert "acknowledged_at" in result

    @pytest.mark.asyncio
    async def test_get_employee_ack_status_returns_per_policy(self):
        """get_employee_ack_status() returns one item per applicable policy."""
        conn = AsyncMock()
        emp_row = {"job_role": "engineer", "department": "Engineering"}
        policy1 = dict(_POLICY_DICT, id="p1")
        policy2 = dict(_POLICY_DICT, id="p2", policy_key="hr-001", title="HR Policy")

        # fetchrow: employee; then 2x ack lookups per policy
        conn.fetchrow = AsyncMock(side_effect=[emp_row, None, None])
        conn.fetch = AsyncMock(return_value=[policy1, policy2])
        pool = make_pool_with_conn(conn)

        mgr = PolicyManager()
        result = await mgr.get_employee_ack_status(pool, TENANT, EMPLOYEE_ID)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_ack_status_is_overdue_when_no_recent_ack(self):
        """An employee who never acknowledged a policy has is_overdue=True."""
        conn = AsyncMock()
        emp_row = {"job_role": "engineer", "department": "Engineering"}
        policy = dict(_POLICY_DICT, acknowledgment_frequency_days=365)

        conn.fetchrow = AsyncMock(side_effect=[emp_row, None])  # no ack found
        conn.fetch = AsyncMock(return_value=[policy])
        pool = make_pool_with_conn(conn)

        mgr = PolicyManager()
        result = await mgr.get_employee_ack_status(pool, TENANT, EMPLOYEE_ID)

        assert result[0]["is_overdue"] is True

    @pytest.mark.asyncio
    async def test_ack_status_not_overdue_when_recently_acked(self):
        """Acknowledged 30 days ago with 365-day frequency → is_overdue=False."""
        conn = AsyncMock()
        emp_row = {"job_role": "engineer", "department": "Engineering"}
        policy = dict(_POLICY_DICT, acknowledgment_frequency_days=365)

        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        ack_row = {"acknowledged_at": thirty_days_ago}

        conn.fetchrow = AsyncMock(side_effect=[emp_row, ack_row])
        conn.fetch = AsyncMock(return_value=[policy])
        pool = make_pool_with_conn(conn)

        mgr = PolicyManager()
        result = await mgr.get_employee_ack_status(pool, TENANT, EMPLOYEE_ID)

        assert result[0]["is_overdue"] is False

    @pytest.mark.asyncio
    async def test_get_overdue_returns_list(self):
        """get_overdue_acknowledgments() returns list from DB fetch."""
        conn = AsyncMock()
        overdue_rows = [
            {"employee_id": "E001", "full_name": "Alice", "email": "a@x.com",
             "policy_id": "p1", "policy_title": "Sec Policy",
             "acknowledgment_frequency_days": 365, "last_acked_at": None},
            {"employee_id": "E002", "full_name": "Bob", "email": "b@x.com",
             "policy_id": "p1", "policy_title": "Sec Policy",
             "acknowledgment_frequency_days": 365, "last_acked_at": None},
            {"employee_id": "E003", "full_name": "Carol", "email": "c@x.com",
             "policy_id": "p1", "policy_title": "Sec Policy",
             "acknowledgment_frequency_days": 365, "last_acked_at": None},
        ]
        conn.fetch = AsyncMock(return_value=overdue_rows)
        pool = make_pool_with_conn(conn)

        mgr = PolicyManager()
        result = await mgr.get_overdue_acknowledgments(pool, TENANT)

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_policy_compliance_rate_computes_pct(self):
        """8 employees acked out of 10 required → pct = 80.0."""
        conn = AsyncMock()
        compliance_rows = [
            {
                "policy_id": POLICY_ID,
                "title": "Information Security Policy",
                "acked_count": 8,
                "total_required": 10,
                "pct": 80.0,
            }
        ]
        conn.fetch = AsyncMock(return_value=compliance_rows)
        pool = make_pool_with_conn(conn)

        mgr = PolicyManager()
        result = await mgr.get_policy_compliance_rate(pool, TENANT)

        assert result["overall_pct"] == 80.0
        assert result["by_policy"][0]["pct"] == 80.0

    @pytest.mark.asyncio
    async def test_applies_to_roles_filters_correct_employees(self):
        """Policy with applies_to_roles=['finance'] → ack status query uses role filter."""
        conn = AsyncMock()
        finance_emp = {"job_role": "finance", "department": "Finance"}
        finance_policy = dict(
            _POLICY_DICT,
            applies_to_roles=["finance"],
            policy_key="fin-001",
            title="Finance Policy",
        )

        conn.fetchrow = AsyncMock(side_effect=[finance_emp, None])
        conn.fetch = AsyncMock(return_value=[finance_policy])
        pool = make_pool_with_conn(conn)

        mgr = PolicyManager()
        result = await mgr.get_employee_ack_status(pool, TENANT, "FIN001")

        # Exactly one policy returned for this role
        assert len(result) == 1
        assert result[0]["policy_id"] == POLICY_ID

        # Verify the fetch query filters by role
        fetch_query = conn.fetch.call_args[0][0]
        assert "applies_to_roles" in fetch_query
