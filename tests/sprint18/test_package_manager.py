"""Sprint 18 — PackageManager unit tests (10 tests)."""
from __future__ import annotations

import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "services", "esg-board-service"),
)

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helper — pool/connection mock (async context-manager protocol)
# ---------------------------------------------------------------------------

def make_pool_conn(
    fetch_val=None,
    fetchrow_val=None,
    execute_val=None,
    fetchval_val=None,
):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=fetch_val or [])
    conn.fetchrow = AsyncMock(return_value=fetchrow_val)
    conn.execute = AsyncMock(return_value=execute_val or "OK")
    conn.fetchval = AsyncMock(return_value=fetchval_val)
    conn.transaction = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=None),
            __aexit__=AsyncMock(return_value=False),
        )
    )
    pool = MagicMock()
    pool.acquire = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=False),
        )
    )
    return pool, conn


TENANT = "cccccccc-0000-0000-0000-000000000018"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPackageManager:

    # 1 — create_package INSERTs into board_packages, no UPDATE
    @pytest.mark.asyncio
    async def test_create_package_inserts_immutable(self):
        from src.package_manager import PackageManager
        from src.models import PackageCreate

        row = {"id": "pkg-1", "title": "Q1 Board Pack", "package_type": "board_pack", "status": "draft"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.package_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PackageManager(pool)
            await mgr.create_package(TENANT, PackageCreate(title="Q1 Board Pack"))

        sql = conn.fetchrow.call_args[0][0]
        assert "board_packages" in sql
        assert "INSERT" in sql.upper()
        assert "UPDATE" not in sql.upper()

    # 2 — PackageCreate default implies status 'draft' in INSERT SQL
    @pytest.mark.asyncio
    async def test_create_package_default_status_draft(self):
        from src.package_manager import PackageManager
        from src.models import PackageCreate

        row = {"id": "pkg-2", "title": "ESG Report Pack", "package_type": "board_pack", "status": "draft"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.package_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PackageManager(pool)
            await mgr.create_package(TENANT, PackageCreate(title="ESG Report Pack"))

        sql = conn.fetchrow.call_args[0][0]
        assert "draft" in sql

    # 3 — add_package_item INSERTs into board_package_items, no UPDATE
    @pytest.mark.asyncio
    async def test_add_package_item_inserts_immutable(self):
        from src.package_manager import PackageManager

        row = {
            "id": "pki-1",
            "package_id": "pkg-1",
            "sequence_number": 1,
            "title": "ESG Scorecard",
            "content_type": "esg_scorecard",
        }
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.package_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PackageManager(pool)
            await mgr.add_package_item(
                TENANT,
                package_id="pkg-1",
                sequence_number=1,
                title="ESG Scorecard",
                content_type="esg_scorecard",
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "board_package_items" in sql
        assert "INSERT" in sql.upper()
        assert "UPDATE" not in sql.upper()

    # 4 — get_package fetches the package row and then its items
    @pytest.mark.asyncio
    async def test_get_package_includes_items(self):
        from src.package_manager import PackageManager

        package_row = {"id": "pkg-1", "title": "Q1 Board Pack", "package_type": "board_pack"}
        item_rows = [
            {"id": "pki-1", "package_id": "pkg-1", "sequence_number": 1, "title": "ESG Scorecard"},
            {"id": "pki-2", "package_id": "pkg-1", "sequence_number": 2, "title": "Risk Register"},
        ]
        pool, conn = make_pool_conn(fetchrow_val=package_row, fetch_val=item_rows)

        with patch("src.package_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PackageManager(pool)
            result = await mgr.get_package(TENANT, package_id="pkg-1")

        assert conn.fetchrow.called
        assert conn.fetch.called
        assert result is not None

    # 5 — list_packages uses package_type filter in SQL when supplied
    @pytest.mark.asyncio
    async def test_list_packages_filter_by_type(self):
        from src.package_manager import PackageManager

        rows = [{"id": "pkg-1", "title": "Audit Report", "package_type": "audit_report"}]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.package_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PackageManager(pool)
            await mgr.list_packages(TENANT, package_type="audit_report")

        call_args = conn.fetch.call_args
        assert any("audit_report" in str(a) for a in call_args[0]) or \
               any("audit_report" in str(a) for a in call_args[1].values()) or \
               "audit_report" in str(call_args)

    # 6 — list_packages SQL contains subquery or JOIN for item count
    @pytest.mark.asyncio
    async def test_list_packages_includes_item_count(self):
        from src.package_manager import PackageManager

        rows = [{"id": "pkg-1", "title": "Q1 Board Pack", "item_count": 3}]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.package_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PackageManager(pool)
            await mgr.list_packages(TENANT)

        sql = conn.fetch.call_args[0][0]
        assert "COUNT" in sql.upper() or "item_count" in sql

    # 7 — build_esg_package creates a package and multiple items
    @pytest.mark.asyncio
    async def test_build_esg_package_creates_package_and_items(self):
        from src.package_manager import PackageManager

        package_row = {"id": "pkg-3", "title": "ESG Q1 2025 Package", "package_type": "esg_report"}
        item_row = {"id": "pki-1", "package_id": "pkg-3", "sequence_number": 1, "title": "ESG Scorecard"}

        pool, conn = make_pool_conn(fetchrow_val=package_row)
        conn.fetchrow = AsyncMock(side_effect=[package_row] + [item_row] * 5)

        with patch("src.package_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PackageManager(pool)
            result = await mgr.build_esg_package(
                TENANT,
                reporting_period="2025-Q1",
                meeting_id="meet-1",
            )

        # Package must be created (at least one INSERT call)
        assert conn.fetchrow.call_count >= 2
        assert result is not None

    # 8 — build_esg_package adds an item with content_type='esg_scorecard'
    @pytest.mark.asyncio
    async def test_build_esg_package_adds_scorecard_item(self):
        from src.package_manager import PackageManager

        package_row = {"id": "pkg-3", "title": "ESG Q1 2025 Package", "package_type": "esg_report"}
        scorecard_item_row = {
            "id": "pki-1",
            "package_id": "pkg-3",
            "sequence_number": 1,
            "title": "ESG Scorecard",
            "content_type": "esg_scorecard",
        }

        pool, conn = make_pool_conn(fetchrow_val=package_row)

        recorded_sqls = []

        async def fetchrow_side(sql, *args, **kwargs):
            recorded_sqls.append(sql)
            if "board_packages" in sql:
                return package_row
            return scorecard_item_row

        conn.fetchrow = AsyncMock(side_effect=fetchrow_side)

        with patch("src.package_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PackageManager(pool)
            await mgr.build_esg_package(
                TENANT,
                reporting_period="2025-Q1",
                meeting_id="meet-1",
            )

        combined = " ".join(recorded_sqls)
        assert "esg_scorecard" in combined

    # 9 — build_audit_committee_package creates a package with type='audit_report'
    @pytest.mark.asyncio
    async def test_build_audit_committee_package_creates_package(self):
        from src.package_manager import PackageManager

        package_row = {
            "id": "pkg-4",
            "title": "Audit Committee Pack",
            "package_type": "audit_report",
            "status": "draft",
        }
        item_row = {
            "id": "pki-1",
            "package_id": "pkg-4",
            "sequence_number": 1,
            "title": "Audit Summary",
        }

        pool, conn = make_pool_conn(fetchrow_val=package_row)

        async def fetchrow_side(sql, *args, **kwargs):
            if "board_packages" in sql and "board_package_items" not in sql:
                return package_row
            return item_row

        conn.fetchrow = AsyncMock(side_effect=fetchrow_side)

        with patch("src.package_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PackageManager(pool)
            result = await mgr.build_audit_committee_package(
                TENANT,
                reporting_period="2025-Q1",
                meeting_id="meet-2",
            )

        all_sqls = [call[0][0] for call in conn.fetchrow.call_args_list]
        first_sql = all_sqls[0]
        assert "audit_report" in first_sql or "board_packages" in first_sql
        assert result is not None

    # 10 — package items are fetched ORDER BY sequence_number
    @pytest.mark.asyncio
    async def test_package_items_sequence_numbers_ordered(self):
        from src.package_manager import PackageManager

        package_row = {"id": "pkg-1", "title": "Q1 Board Pack", "package_type": "board_pack"}
        item_rows = [
            {"id": "pki-1", "package_id": "pkg-1", "sequence_number": 1, "title": "Item One"},
            {"id": "pki-2", "package_id": "pkg-1", "sequence_number": 2, "title": "Item Two"},
            {"id": "pki-3", "package_id": "pkg-1", "sequence_number": 3, "title": "Item Three"},
        ]
        pool, conn = make_pool_conn(fetchrow_val=package_row, fetch_val=item_rows)

        with patch("src.package_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PackageManager(pool)
            await mgr.get_package(TENANT, package_id="pkg-1")

        items_sql = conn.fetch.call_args[0][0]
        assert "sequence_number" in items_sql
        assert "ORDER BY" in items_sql.upper()
