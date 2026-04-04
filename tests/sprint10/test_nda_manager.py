import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/trust-portal-service'))

import pytest
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4
from datetime import datetime, timezone

from src.nda_manager import NDAManager
from src.models import NDAAcceptance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool(fetchrow_return=None, fetchval_return=None, execute_return=None):
    """Build a mock pool with configurable return values."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    mock_conn.fetchval = AsyncMock(return_value=fetchval_return)
    mock_conn.execute = AsyncMock(return_value=execute_return)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


def _make_acceptance(**kwargs) -> NDAAcceptance:
    defaults = {
        "signatory_name": "Jane Smith",
        "signatory_email": "jane@example.com",
        "signatory_company": "Example Corp",
        "nda_version": "1.0",
    }
    defaults.update(kwargs)
    return NDAAcceptance(**defaults)


def _acceptance_row(**kwargs) -> dict:
    defaults = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "signatory_name": "Jane Smith",
        "signatory_email": "jane@example.com",
        "signatory_company": "Example Corp",
        "nda_version": "1.0",
        "ip_address": "127.0.0.1",
        "user_agent": "Mozilla/5.0",
        "accepted_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# TestNDAManager
# ---------------------------------------------------------------------------

class TestNDAManager:

    @pytest.mark.asyncio
    async def test_has_valid_nda_true(self):
        """Mock fetchrow returning a row (id present); assert has_valid_nda returns True."""
        tenant_id = str(uuid4())
        existing_row = {"id": uuid4()}
        mock_pool, mock_conn = _make_pool(fetchrow_return=existing_row)
        mock_conn.fetchrow = AsyncMock(return_value=existing_row)
        mock_conn.execute = AsyncMock(return_value=None)

        manager = NDAManager()
        result = await manager.has_valid_nda(
            mock_pool, tenant_id, "jane@example.com", "1.0"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_has_valid_nda_false_wrong_version(self):
        """Mock returning None (wrong nda_version); assert has_valid_nda returns False."""
        tenant_id = str(uuid4())
        mock_pool, mock_conn = _make_pool(fetchrow_return=None)
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock(return_value=None)

        manager = NDAManager()
        result = await manager.has_valid_nda(
            mock_pool, tenant_id, "jane@example.com", "2.0"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_has_valid_nda_false_no_record(self):
        """Mock returning None (no record at all); assert has_valid_nda returns False."""
        tenant_id = str(uuid4())
        mock_pool, mock_conn = _make_pool(fetchrow_return=None)
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock(return_value=None)

        manager = NDAManager()
        result = await manager.has_valid_nda(
            mock_pool, tenant_id, "nobody@example.com", "1.0"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_record_acceptance_inserts_immutable_row(self):
        """Verify execute was called and no UPDATE/DELETE SQL was issued."""
        tenant_id = str(uuid4())
        row = _acceptance_row()
        mock_pool, mock_conn = _make_pool(fetchrow_return=row)
        mock_conn.fetchrow = AsyncMock(return_value=row)
        mock_conn.execute = AsyncMock(return_value=None)

        manager = NDAManager()
        acceptance = _make_acceptance()
        await manager.record_acceptance(
            mock_pool, tenant_id, acceptance, "127.0.0.1", "Mozilla/5.0"
        )

        # Verify a DB write happened (fetchrow for INSERT...RETURNING)
        mock_conn.fetchrow.assert_called_once()

        # Confirm no UPDATE or DELETE was issued via execute
        for execute_call in mock_conn.execute.call_args_list:
            sql = execute_call[0][0].upper() if execute_call[0] else ""
            assert "UPDATE" not in sql, "NDA table must be append-only — no UPDATE"
            assert "DELETE" not in sql, "NDA table must be append-only — no DELETE"

    @pytest.mark.asyncio
    async def test_record_acceptance_returns_dict(self):
        """Verify returned dict has id, signatory_email, accepted_at."""
        tenant_id = str(uuid4())
        row = _acceptance_row()
        mock_pool, mock_conn = _make_pool(fetchrow_return=row)
        mock_conn.fetchrow = AsyncMock(return_value=row)
        mock_conn.execute = AsyncMock(return_value=None)

        manager = NDAManager()
        acceptance = _make_acceptance()
        result = await manager.record_acceptance(
            mock_pool, tenant_id, acceptance, "127.0.0.1", "Mozilla/5.0"
        )

        assert "id" in result
        assert "signatory_email" in result
        assert "accepted_at" in result

    @pytest.mark.asyncio
    async def test_get_nda_stats_returns_counts(self):
        """Mock fetchrow returning stats dict; verify structure."""
        tenant_id = str(uuid4())
        stats_row = {"total": 42, "last_7_days": 5, "unique_companies": 12}
        mock_pool, mock_conn = _make_pool(fetchrow_return=stats_row)
        mock_conn.fetchrow = AsyncMock(return_value=stats_row)
        mock_conn.execute = AsyncMock(return_value=None)

        manager = NDAManager()
        result = await manager.get_nda_stats(mock_pool, tenant_id)

        assert result["total"] == 42
        assert result["last_7_days"] == 5
        assert result["unique_companies"] == 12

    @pytest.mark.asyncio
    async def test_duplicate_nda_still_inserts(self):
        """NDA table is append-only — same email can sign twice; both records inserted."""
        tenant_id = str(uuid4())
        row1 = _acceptance_row(signatory_email="repeat@example.com")
        row2 = _acceptance_row(signatory_email="repeat@example.com")

        # Simulate two successive fetchrow calls returning two distinct rows
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(side_effect=[row1, row2])
        mock_conn.execute = AsyncMock(return_value=None)
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        manager = NDAManager()
        acceptance = _make_acceptance(signatory_email="repeat@example.com")

        result1 = await manager.record_acceptance(
            mock_pool, tenant_id, acceptance, "10.0.0.1", "Browser/1.0"
        )
        result2 = await manager.record_acceptance(
            mock_pool, tenant_id, acceptance, "10.0.0.2", "Browser/1.0"
        )

        # Both inserts occurred (fetchrow called twice)
        assert mock_conn.fetchrow.call_count == 2
        # Both returned valid records
        assert result1["signatory_email"] == "repeat@example.com"
        assert result2["signatory_email"] == "repeat@example.com"

    @pytest.mark.asyncio
    async def test_nda_version_recorded_correctly(self):
        """Verify the nda_version from the acceptance model is passed through."""
        tenant_id = str(uuid4())
        row = _acceptance_row(nda_version="2.5")
        mock_pool, mock_conn = _make_pool(fetchrow_return=row)
        mock_conn.fetchrow = AsyncMock(return_value=row)
        mock_conn.execute = AsyncMock(return_value=None)

        manager = NDAManager()
        acceptance = _make_acceptance(nda_version="2.5")
        result = await manager.record_acceptance(
            mock_pool, tenant_id, acceptance, "127.0.0.1", "Mozilla/5.0"
        )

        # Verify the version appears in the INSERT call args
        call_args = mock_conn.fetchrow.call_args[0]
        # The nda_version "2.5" is passed as a positional parameter
        assert "2.5" in call_args, (
            f"nda_version '2.5' not found in INSERT call args: {call_args}"
        )
        assert result["nda_version"] == "2.5"
