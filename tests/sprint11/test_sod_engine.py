import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/monitoring-service"))

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.sod_engine import SoDEngine
from src.models import UserAccessRecord


# ---------------------------------------------------------------------------
# Mock SoD rules dataset
# ---------------------------------------------------------------------------

MOCK_SOD_RULES = [
    {
        "id": "uuid1",
        "rule_key": "ap_entry_approval",
        "display_name": "AP Entry and Approval",
        "role_a": "accounts_payable_entry",
        "role_b": "accounts_payable_approval",
        "severity": "critical",
        "is_active": True,
        "description": "User can both enter and approve AP transactions.",
    },
    {
        "id": "uuid2",
        "rule_key": "po_create_approve",
        "display_name": "PO Create and Approve",
        "role_a": "purchase_order_create",
        "role_b": "purchase_order_approve",
        "severity": "critical",
        "is_active": True,
        "description": "User can both create and approve purchase orders.",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool(rules=None):
    """Return a mock asyncpg pool whose conn.fetch() returns the given rules list."""
    if rules is None:
        rules = MOCK_SOD_RULES

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=rules)
    mock_conn.execute = AsyncMock(return_value=None)

    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool


def _make_user(user_id, roles, name=None, email=None, department=None):
    return UserAccessRecord(
        user_id=user_id,
        user_name=name or f"User {user_id}",
        user_email=email or f"{user_id}@example.com",
        department=department,
        roles=roles,
    )


# ---------------------------------------------------------------------------
# TestSoDEngine
# ---------------------------------------------------------------------------

class TestSoDEngine:

    @pytest.mark.asyncio
    async def test_no_violations_for_clean_user(self):
        """User with only role 'viewer' → 0 violations."""
        pool = _make_pool()
        engine = SoDEngine()
        tenant_id = "tenant-001"
        users = [_make_user("U001", ["viewer"])]
        violations = await engine.analyze(pool, tenant_id, users)
        assert len(violations) == 0

    @pytest.mark.asyncio
    async def test_detects_ap_conflict(self):
        """User with roles ['accounts_payable_entry', 'accounts_payable_approval'] → 1 violation."""
        pool = _make_pool()
        engine = SoDEngine()
        tenant_id = "tenant-001"
        users = [_make_user("U002", ["accounts_payable_entry", "accounts_payable_approval"])]
        violations = await engine.analyze(pool, tenant_id, users)
        ap_violations = [v for v in violations if v["rule_key"] == "ap_entry_approval"]
        assert len(ap_violations) == 1

    @pytest.mark.asyncio
    async def test_case_insensitive_role_matching(self):
        """Roles with different casing still match the rule tokens (substring + case-insensitive)."""
        pool = _make_pool()
        engine = SoDEngine()
        tenant_id = "tenant-001"
        # Uppercase roles that still contain the lowercase rule tokens
        users = [_make_user("U003", ["ACCOUNTS_PAYABLE_ENTRY", "ACCOUNTS_PAYABLE_APPROVAL"])]
        violations = await engine.analyze(pool, tenant_id, users)
        ap_violations = [v for v in violations if v["rule_key"] == "ap_entry_approval"]
        assert len(ap_violations) == 1

    @pytest.mark.asyncio
    async def test_substring_role_matching(self):
        """Role 'senior_accounts_payable_entry_manager' contains 'accounts_payable_entry' → matches."""
        pool = _make_pool()
        engine = SoDEngine()
        tenant_id = "tenant-001"
        users = [_make_user(
            "U004",
            [
                "senior_accounts_payable_entry_manager",
                "accounts_payable_approval",
            ],
        )]
        violations = await engine.analyze(pool, tenant_id, users)
        ap_violations = [v for v in violations if v["rule_key"] == "ap_entry_approval"]
        assert len(ap_violations) == 1

    @pytest.mark.asyncio
    async def test_multiple_violations_same_user(self):
        """User has 4 roles matching 2 SoD rules → 2 violations."""
        pool = _make_pool()
        engine = SoDEngine()
        tenant_id = "tenant-001"
        users = [_make_user(
            "U005",
            [
                "accounts_payable_entry",
                "accounts_payable_approval",
                "purchase_order_create",
                "purchase_order_approve",
            ],
        )]
        violations = await engine.analyze(pool, tenant_id, users)
        assert len(violations) == 2

    @pytest.mark.asyncio
    async def test_risk_score_higher_for_critical(self):
        """Critical rule violation has risk_score >= 7.0."""
        pool = _make_pool()
        engine = SoDEngine()
        tenant_id = "tenant-001"
        users = [_make_user("U006", ["accounts_payable_entry", "accounts_payable_approval"])]
        violations = await engine.analyze(pool, tenant_id, users)
        assert violations, "Expected at least one violation"
        critical_violations = [v for v in violations if v["severity"] == "critical"]
        assert critical_violations, "Expected at least one critical violation"
        assert critical_violations[0]["risk_score"] >= 7.0

    @pytest.mark.asyncio
    async def test_inactive_rule_not_checked(self):
        """Rule with is_active=False → not evaluated."""
        inactive_rules = [
            {
                "id": "uuid1",
                "rule_key": "ap_entry_approval",
                "display_name": "AP Entry and Approval",
                "role_a": "accounts_payable_entry",
                "role_b": "accounts_payable_approval",
                "severity": "critical",
                "is_active": False,  # inactive
                "description": None,
            },
        ]
        pool = _make_pool(rules=inactive_rules)
        engine = SoDEngine()
        tenant_id = "tenant-001"
        # The DB fetch returns only active rules (WHERE is_active = TRUE), so result is empty
        users = [_make_user("U007", ["accounts_payable_entry", "accounts_payable_approval"])]
        violations = await engine.analyze(pool, tenant_id, users)
        # With an empty rule list returned, no violations should be detected
        assert len(violations) == 0

    @pytest.mark.asyncio
    async def test_no_users_returns_empty(self):
        """[] → []."""
        pool = _make_pool()
        engine = SoDEngine()
        violations = await engine.analyze(pool, "tenant-001", [])
        assert violations == []

    @pytest.mark.asyncio
    async def test_violation_has_required_fields(self):
        """Violation dict has user_id, role_a_detail (role_a), role_b_detail (role_b), sod_rule_id (rule_id)."""
        pool = _make_pool()
        engine = SoDEngine()
        users = [_make_user("U008", ["accounts_payable_entry", "accounts_payable_approval"])]
        violations = await engine.analyze(pool, "tenant-001", users)
        assert violations, "Expected at least one violation"
        v = violations[0]
        assert "user_id" in v, "violation must have user_id"
        # The engine stores role_a and role_b (the rule token strings) in 'role_a' / 'role_b'
        assert "role_a" in v or "role_a_detail" in v, "violation must have role_a or role_a_detail"
        assert "role_b" in v or "role_b_detail" in v, "violation must have role_b or role_b_detail"
        assert "rule_id" in v or "sod_rule_id" in v, "violation must have rule_id or sod_rule_id"

    @pytest.mark.asyncio
    async def test_multiple_users_checked(self):
        """3 users, 1 has violation → exactly 1 violation returned."""
        pool = _make_pool()
        engine = SoDEngine()
        tenant_id = "tenant-001"
        users = [
            _make_user("CLEAN1", ["viewer", "reporter"]),
            _make_user("VIOLATOR", ["accounts_payable_entry", "accounts_payable_approval"]),
            _make_user("CLEAN2", ["purchase_order_create"]),  # only one role from rule
        ]
        violations = await engine.analyze(pool, tenant_id, users)
        assert len(violations) == 1
        assert violations[0]["user_id"] == "VIOLATOR"
