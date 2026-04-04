import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/trust-portal-service'))

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

from src.portal_config import PortalConfigManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool(fetchrow_return=None, execute_return=None):
    """Build a mock pool whose conn.fetchrow returns the given value."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    mock_conn.execute = AsyncMock(return_value=execute_return)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


def _sample_config_row(slug: str = "acme-corp", portal_enabled: bool = True) -> dict:
    return {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "slug": slug,
        "company_name": "Acme Corporation",
        "tagline": "Security you can trust",
        "logo_url": "https://acme.com/logo.png",
        "primary_color": "#0066CC",
        "portal_enabled": portal_enabled,
        "require_nda": False,
        "nda_version": "1.0",
        "show_compliance_scores": True,
        "chatbot_enabled": False,
        "chatbot_welcome_message": None,
        "allowed_frameworks": ["soc2", "iso27001"],
    }


# ---------------------------------------------------------------------------
# TestPortalConfigManager
# ---------------------------------------------------------------------------

class TestPortalConfigManager:

    @pytest.mark.asyncio
    async def test_get_by_slug_found(self):
        """Mock asyncpg conn returning a row; assert config dict matches."""
        row = _sample_config_row(slug="acme-corp")
        mock_pool, mock_conn = _make_pool(fetchrow_return=row)
        mock_conn.fetchrow = AsyncMock(return_value=row)

        manager = PortalConfigManager()
        result = await manager.get_by_slug(mock_pool, "acme-corp")

        assert result is not None
        assert result["slug"] == "acme-corp"
        assert result["company_name"] == "Acme Corporation"
        assert result["primary_color"] == "#0066CC"

    @pytest.mark.asyncio
    async def test_get_by_slug_not_found(self):
        """Mock returning None; assert returns None."""
        mock_pool, mock_conn = _make_pool(fetchrow_return=None)
        mock_conn.fetchrow = AsyncMock(return_value=None)

        manager = PortalConfigManager()
        result = await manager.get_by_slug(mock_pool, "nonexistent-slug")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_slug_disabled_portal_returns_none(self):
        """Simulate portal_enabled=false filtered by SQL — mock returns None."""
        # The SQL WHERE clause filters portal_enabled=true at DB level.
        # When portal is disabled, the DB returns no row.
        mock_pool, mock_conn = _make_pool(fetchrow_return=None)
        mock_conn.fetchrow = AsyncMock(return_value=None)

        manager = PortalConfigManager()
        result = await manager.get_by_slug(mock_pool, "disabled-portal")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_tenant_returns_config(self):
        """Mock conn fetchrow returning config; verify dict returned."""
        tenant_id = str(uuid4())
        row = _sample_config_row()
        mock_pool, mock_conn = _make_pool(fetchrow_return=row)
        mock_conn.fetchrow = AsyncMock(return_value=row)
        mock_conn.execute = AsyncMock(return_value=None)

        manager = PortalConfigManager()
        result = await manager.get_by_tenant(mock_pool, tenant_id)

        assert result is not None
        assert result["company_name"] == "Acme Corporation"

    @pytest.mark.asyncio
    async def test_upsert_creates_new_config(self):
        """Mock conn.fetchrow returning new record after INSERT."""
        tenant_id = str(uuid4())
        new_row = _sample_config_row(slug="new-company")
        mock_pool, mock_conn = _make_pool(fetchrow_return=new_row)
        mock_conn.fetchrow = AsyncMock(return_value=new_row)
        mock_conn.execute = AsyncMock(return_value=None)

        manager = PortalConfigManager()
        result = await manager.upsert(mock_pool, tenant_id, {
            "slug": "new-company",
            "company_name": "Acme Corporation",
        })

        assert result["slug"] == "new-company"
        mock_conn.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self):
        """Mock INSERT ON CONFLICT UPDATE — returns updated row."""
        tenant_id = str(uuid4())
        updated_row = {**_sample_config_row(), "company_name": "Acme Corp Updated"}
        mock_pool, mock_conn = _make_pool(fetchrow_return=updated_row)
        mock_conn.fetchrow = AsyncMock(return_value=updated_row)
        mock_conn.execute = AsyncMock(return_value=None)

        manager = PortalConfigManager()
        result = await manager.upsert(mock_pool, tenant_id, {
            "slug": "acme-corp",
            "company_name": "Acme Corp Updated",
        })

        assert result["company_name"] == "Acme Corp Updated"

    def test_slug_validation_rejects_uppercase(self):
        """Slug 'My-Company' raises ValueError due to uppercase."""
        manager = PortalConfigManager()
        with pytest.raises(ValueError, match="lowercase"):
            manager.validate_slug("My-Company")

    def test_slug_validation_accepts_lowercase_hyphen(self):
        """Slug 'acme-corp' passes validation without error."""
        manager = PortalConfigManager()
        # Should not raise
        manager.validate_slug("acme-corp")

    def test_slug_validation_rejects_spaces(self):
        """Slug 'acme corp' raises ValueError due to spaces."""
        manager = PortalConfigManager()
        with pytest.raises(ValueError):
            manager.validate_slug("acme corp")

    @pytest.mark.asyncio
    async def test_upsert_sets_updated_at(self):
        """Verify updated_at is referenced in the upsert SQL."""
        tenant_id = str(uuid4())
        row = _sample_config_row()
        mock_pool, mock_conn = _make_pool(fetchrow_return=row)
        mock_conn.fetchrow = AsyncMock(return_value=row)
        mock_conn.execute = AsyncMock(return_value=None)

        manager = PortalConfigManager()
        await manager.upsert(mock_pool, tenant_id, {
            "slug": "acme-corp",
            "company_name": "Acme Corporation",
        })

        # Verify the fetchrow (INSERT...RETURNING) was called
        mock_conn.fetchrow.assert_called_once()
        # Inspect the SQL passed to fetchrow — it should contain updated_at
        call_args = mock_conn.fetchrow.call_args
        sql = call_args[0][0]
        assert "updated_at" in sql
