"""Sprint 14 — SyncEngine unit tests."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/integration-service"),
)

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    from src.sync_engine import SyncEngine
    from src.encryption import TokenEncryption
    settings = MagicMock()
    enc = TokenEncryption("test-key")
    return SyncEngine(settings, enc)


TENANT = "00000000-0000-0000-0000-000000000014"
INTEGRATION_ID = "aaaa1400-0000-0000-0000-000000000002"


def make_pool_conn():
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSyncEngine:

    @pytest.mark.asyncio
    async def test_fetch_data_employees_returns_list(self, engine):
        """_fetch_data for 'employees' must return a non-empty list."""
        result = await engine._fetch_data({}, "employees", {})
        assert isinstance(result, list)
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_fetch_data_gl_transactions_returns_list(self, engine):
        """_fetch_data for 'gl_transactions' must return a non-empty list."""
        result = await engine._fetch_data({}, "gl_transactions", {})
        assert isinstance(result, list)
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_fetch_data_unknown_type_returns_generic(self, engine):
        """_fetch_data for an unknown data_type must return a list of generic
        records each containing at least an 'id' key."""
        result = await engine._fetch_data({}, "unknown_type", {})
        assert isinstance(result, list)
        assert len(result) >= 1
        for item in result:
            assert "id" in item

    @pytest.mark.asyncio
    async def test_normalize_no_mappings_returns_raw(self, engine):
        """When mappings is empty, _normalize_record returns the raw record unchanged."""
        raw = {"Worker_ID": "W001", "FirstName": "Alice"}
        result = await engine._normalize_record(raw, "workday", "employees", [])
        assert result == raw

    @pytest.mark.asyncio
    async def test_normalize_simple_field_mapping(self, engine):
        """A simple source→target mapping renames the field correctly."""
        raw = {"Worker_ID": "W001"}
        mappings = [
            {"source_field": "Worker_ID", "target_field": "employee_id", "transform_fn": None}
        ]
        result = await engine._normalize_record(raw, "workday", "employees", mappings)
        assert result.get("employee_id") == "W001"

    @pytest.mark.asyncio
    async def test_normalize_map_transform(self, engine):
        """transform_fn='map: Active→active, Terminated→terminated' maps status correctly."""
        raw = {"status": "Active"}
        mappings = [
            {
                "source_field": "status",
                "target_field": "status",
                "transform_fn": "map: Active→active, Terminated→terminated",
            }
        ]
        result = await engine._normalize_record(raw, "workday", "employees", mappings)
        assert result.get("status") == "active"

    @pytest.mark.asyncio
    async def test_normalize_concat_transform(self, engine):
        """transform_fn='concat: firstName lastName' concatenates two source fields."""
        raw = {"firstName": "John", "lastName": "Doe"}
        target_field = "full_name"
        mappings = [
            {
                "source_field": "firstName",
                "target_field": target_field,
                "transform_fn": "concat: firstName lastName",
            }
        ]
        result = await engine._normalize_record(raw, "workday", "employees", mappings)
        assert result.get(target_field) == "John Doe"

    @pytest.mark.asyncio
    async def test_normalize_missing_source_field_skipped(self, engine):
        """When a source_field is absent from raw, the target_field is omitted from result."""
        raw = {"other_field": "value"}
        mappings = [
            {
                "source_field": "nonexistent_field",
                "target_field": "employee_id",
                "transform_fn": None,
            }
        ]
        result = await engine._normalize_record(raw, "workday", "employees", mappings)
        assert "employee_id" not in result

    @pytest.mark.asyncio
    async def test_normalize_required_field_missing_still_skipped(self, engine):
        """Even when is_required=True, a missing source_field does not raise;
        the target_field receives None and no exception is thrown."""
        raw = {}
        mappings = [
            {
                "source_field": "required_field",
                "target_field": "mandatory_output",
                "transform_fn": None,
                "is_required": True,
            }
        ]
        # Must not raise
        result = await engine._normalize_record(raw, "workday", "employees", mappings)
        # The implementation sets target to None for required missing fields
        assert result.get("mandatory_output") is None

    @pytest.mark.asyncio
    async def test_sync_run_inserts_sync_log(self, engine):
        """run_sync must INSERT a row into integration_sync_logs."""
        from src.models import SyncRequest

        pool, conn = make_pool_conn()

        # Integration row returned from the initial SELECT
        integration_data = {
            "id": INTEGRATION_ID,
            "tenant_id": TENANT,
            "connector_id": "conn-id",
            "connector_key": "workday",
            "supported_data_types": ["employees"],
            "auth_type": "api_key",
            "auth_config": json.dumps({}),
            "field_mappings": json.dumps({}),
            "sync_schedule": "0 */6 * * *",
            "webhook_secret": None,
            "status": "active",
            "integration_name": "Workday",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        integration_row = MagicMock()
        integration_row.__getitem__ = lambda self, key: integration_data[key]
        integration_row.get = lambda key, default=None: integration_data.get(key, default)
        integration_row._data = integration_data
        integration_row.__iter__ = lambda self: iter(integration_data.items())

        conn.fetchrow = AsyncMock(return_value=integration_row)
        conn.execute = AsyncMock()
        conn.fetchval = AsyncMock(return_value=None)

        execute_calls: list = []

        async def capture_execute(sql, *args):
            execute_calls.append(sql)

        conn.execute = capture_execute

        # Patch _fetch_data to return a tiny synthetic list
        async def fake_fetch(integration, data_type, auth_config):
            return [{"id": "emp-0001", "name": "Test User"}]

        engine._fetch_data = fake_fetch

        sync_request = SyncRequest(data_types=["employees"], sync_type="manual")

        with patch("src.sync_engine.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await engine.run_sync(pool, TENANT, INTEGRATION_ID, sync_request)

        # At least one INSERT on integration_sync_logs must have been executed
        log_inserts = [s for s in execute_calls if "integration_sync_logs" in s]
        assert len(log_inserts) >= 1, (
            "run_sync must INSERT into integration_sync_logs"
        )
