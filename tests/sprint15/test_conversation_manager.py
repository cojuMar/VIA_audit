"""Sprint 15 — ConversationManager unit tests."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/ai-agent-service"),
)

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT = "tenant-00000000-0000-0000-0000-000000000015"
CONV_ID = "conv-00000000-0000-0000-0000-000000000001"


def _mock_tenant_conn(conn):
    """Return an async context manager that yields *conn*."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _make_conv_row(**kwargs):
    defaults = {
        "id": CONV_ID,
        "tenant_id": TENANT,
        "title": "Test Conversation",
        "status": "active",
        "message_count": 4,
        "tool_call_count": 2,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    defaults.update(kwargs)
    row = MagicMock()
    row.__getitem__ = lambda self, key: defaults[key]
    row.keys = MagicMock(return_value=list(defaults.keys()))
    row._data = defaults
    row.__iter__ = lambda self: iter(defaults.items())
    return row


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestConversationManager:

    @pytest.mark.asyncio
    async def test_list_conversations_filters_active(self):
        """list_conversations() SQL must filter on status = 'active'."""
        from src.conversation_manager import ConversationManager

        conn = AsyncMock()
        captured_sql = {}

        async def fake_fetch(sql, *args):
            captured_sql["sql"] = sql
            return []

        conn.fetch = fake_fetch

        mgr = ConversationManager()

        with patch("src.conversation_manager.tenant_conn") as mock_tc:
            mock_tc.return_value = _mock_tenant_conn(conn)
            pool = MagicMock()
            await mgr.list_conversations(pool, TENANT)

        assert "active" in captured_sql.get("sql", "")

    @pytest.mark.asyncio
    async def test_list_conversations_returns_list(self):
        """list_conversations() must return a Python list."""
        from src.conversation_manager import ConversationManager

        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[
            _make_conv_row(),
            _make_conv_row(id="conv-2", title="Another Conversation"),
        ])

        mgr = ConversationManager()

        with patch("src.conversation_manager.tenant_conn") as mock_tc:
            mock_tc.return_value = _mock_tenant_conn(conn)
            pool = MagicMock()
            result = await mgr.list_conversations(pool, TENANT)

        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_conversation_returns_none_for_missing(self):
        """get_conversation() must return None when fetchrow returns None."""
        from src.conversation_manager import ConversationManager

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)

        mgr = ConversationManager()

        with patch("src.conversation_manager.tenant_conn") as mock_tc:
            mock_tc.return_value = _mock_tenant_conn(conn)
            pool = MagicMock()
            result = await mgr.get_conversation(pool, TENANT, "nonexistent-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_archive_updates_status(self):
        """archive_conversation() must issue an UPDATE setting status='archived'."""
        from src.conversation_manager import ConversationManager

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=_make_conv_row())
        captured_sql = {}
        captured_args = {}

        async def fake_fetchrow(sql, *args):
            captured_sql["sql"] = sql
            captured_args["args"] = args
            return _make_conv_row(status="archived")

        conn.fetchrow = fake_fetchrow

        mgr = ConversationManager()

        with patch("src.conversation_manager.tenant_conn") as mock_tc:
            mock_tc.return_value = _mock_tenant_conn(conn)
            pool = MagicMock()
            await mgr.archive_conversation(pool, TENANT, CONV_ID)

        sql = captured_sql.get("sql", "")
        args = captured_args.get("args", ())
        assert "UPDATE" in sql
        assert "archived" in args or "archived" in sql

    @pytest.mark.asyncio
    async def test_update_title_sets_new_title(self):
        """update_title() must issue an UPDATE setting the new title."""
        from src.conversation_manager import ConversationManager

        conn = AsyncMock()
        new_title = "My Renamed Conversation"
        captured_sql = {}
        captured_args = {}

        async def fake_fetchrow(sql, *args):
            captured_sql["sql"] = sql
            captured_args["args"] = args
            return _make_conv_row(title=new_title)

        conn.fetchrow = fake_fetchrow

        mgr = ConversationManager()

        with patch("src.conversation_manager.tenant_conn") as mock_tc:
            mock_tc.return_value = _mock_tenant_conn(conn)
            pool = MagicMock()
            await mgr.update_title(pool, TENANT, CONV_ID, new_title)

        sql = captured_sql.get("sql", "")
        args = captured_args.get("args", ())
        assert "UPDATE" in sql
        assert new_title in args or new_title in sql

    @pytest.mark.asyncio
    async def test_get_stats_returns_required_keys(self):
        """get_stats() must return a dict with all required top-level keys."""
        from src.conversation_manager import ConversationManager

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={
            "total_conversations": 10,
            "total_messages": 45,
            "total_tool_calls": 22,
        })
        conn.fetchval = AsyncMock(side_effect=[
            # avg_tools_per_message
            2.3,
            # feedback_avg_rating
            4.1,
        ])
        conn.fetch = AsyncMock(return_value=[
            {"tool_name": "get_compliance_scores", "call_count": 12},
            {"tool_name": "search_knowledge_base",  "call_count": 7},
        ])

        mgr = ConversationManager()

        with patch("src.conversation_manager.tenant_conn") as mock_tc:
            mock_tc.return_value = _mock_tenant_conn(conn)
            pool = MagicMock()
            result = await mgr.get_stats(pool, TENANT)

        required_keys = {
            "total_conversations",
            "total_messages",
            "total_tool_calls",
            "avg_tools_per_message",
            "most_used_tools",
            "feedback_avg_rating",
        }
        assert required_keys.issubset(result.keys()), (
            f"Missing keys: {required_keys - result.keys()}"
        )

    @pytest.mark.asyncio
    async def test_get_stats_most_used_tools_is_list(self):
        """get_stats() must return most_used_tools as a list."""
        from src.conversation_manager import ConversationManager

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={
            "total_conversations": 5,
            "total_messages": 20,
            "total_tool_calls": 8,
        })
        conn.fetchval = AsyncMock(side_effect=[1.6, 3.8])
        conn.fetch = AsyncMock(return_value=[
            {"tool_name": "get_vendor_risk_summary", "call_count": 5},
        ])

        mgr = ConversationManager()

        with patch("src.conversation_manager.tenant_conn") as mock_tc:
            mock_tc.return_value = _mock_tenant_conn(conn)
            pool = MagicMock()
            result = await mgr.get_stats(pool, TENANT)

        assert isinstance(result["most_used_tools"], list)

    @pytest.mark.asyncio
    async def test_archive_nonexistent_raises(self):
        """archive_conversation() must raise ValueError when the conversation is not found."""
        from src.conversation_manager import ConversationManager

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)

        mgr = ConversationManager()

        with patch("src.conversation_manager.tenant_conn") as mock_tc:
            mock_tc.return_value = _mock_tenant_conn(conn)
            pool = MagicMock()
            with pytest.raises(ValueError):
                await mgr.archive_conversation(pool, TENANT, "does-not-exist")
