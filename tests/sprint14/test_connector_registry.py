"""Sprint 14 — ConnectorRegistry unit tests."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/integration-service"),
)

import pytest
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pool_conn():
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


def _connector_row(connector_key="workday", category="hris", auth_type="api_key"):
    return {
        "id": f"cid-{connector_key}",
        "connector_key": connector_key,
        "display_name": connector_key.capitalize(),
        "category": category,
        "auth_type": auth_type,
        "supported_data_types": ["employees"],
        "description": f"{connector_key} integration",
        "logo_url": f"https://cdn.example.com/{connector_key}.png",
        "is_active": True,
        "created_at": "2026-01-01T00:00:00Z",
    }


def _mapping_row(source_field, target_field, data_type="employees"):
    return {
        "id": f"map-{source_field}",
        "data_type": data_type,
        "source_field": source_field,
        "target_field": target_field,
        "transform_fn": None,
        "is_required": True,
        "description": f"Map {source_field} to {target_field}",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestConnectorRegistry:

    @pytest.mark.asyncio
    async def test_list_connectors_no_tenant(self):
        """list_connectors() must NOT filter by tenant_id — it is a global catalog."""
        from src.connector_registry import ConnectorRegistry

        pool, conn = make_pool_conn()
        conn.fetch = AsyncMock(return_value=[_connector_row("workday")])

        registry = ConnectorRegistry()
        await registry.list_connectors(pool)

        fetch_sql = conn.fetch.call_args[0][0]
        assert "tenant_id" not in fetch_sql.lower(), (
            "list_connectors SQL must not filter by tenant_id"
        )

    @pytest.mark.asyncio
    async def test_list_connectors_returns_all_active(self):
        """list_connectors() must include WHERE is_active = true in its query."""
        from src.connector_registry import ConnectorRegistry

        pool, conn = make_pool_conn()
        conn.fetch = AsyncMock(return_value=[
            _connector_row("workday"),
            _connector_row("salesforce", category="crm"),
        ])

        registry = ConnectorRegistry()
        result = await registry.list_connectors(pool)

        fetch_sql = conn.fetch.call_args[0][0]
        assert "is_active" in fetch_sql, (
            "list_connectors SQL must filter on is_active"
        )
        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_connector_by_key(self):
        """get_connector() must return a dict when fetchrow finds the connector."""
        from src.connector_registry import ConnectorRegistry

        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(return_value=_connector_row("workday"))

        registry = ConnectorRegistry()
        result = await registry.get_connector(pool, "workday")

        assert result is not None
        assert isinstance(result, dict)
        assert result["connector_key"] == "workday"

    @pytest.mark.asyncio
    async def test_get_connector_missing_returns_none(self):
        """get_connector() must return None when fetchrow returns None."""
        from src.connector_registry import ConnectorRegistry

        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(return_value=None)

        registry = ConnectorRegistry()
        result = await registry.get_connector(pool, "nonexistent-connector")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_field_templates_returns_mappings(self):
        """get_field_mapping_templates() must return the list of mapping rows."""
        from src.connector_registry import ConnectorRegistry

        pool, conn = make_pool_conn()
        mock_rows = [
            _mapping_row("Worker_ID", "employee_id"),
            _mapping_row("First_Name", "first_name"),
            _mapping_row("Last_Name", "last_name"),
        ]
        conn.fetch = AsyncMock(return_value=mock_rows)

        registry = ConnectorRegistry()
        result = await registry.get_field_mapping_templates(pool, "workday", "employees")

        assert isinstance(result, list)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_get_field_templates_empty_for_unknown_connector(self):
        """get_field_mapping_templates() must return [] when no rows match."""
        from src.connector_registry import ConnectorRegistry

        pool, conn = make_pool_conn()
        conn.fetch = AsyncMock(return_value=[])

        registry = ConnectorRegistry()
        result = await registry.get_field_mapping_templates(
            pool, "unknown-connector-xyz", "employees"
        )

        assert result == []
