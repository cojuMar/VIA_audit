import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/trust-portal-service'))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from src.chatbot import PortalChatbot
from src.config import Settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(**kwargs) -> Settings:
    defaults = {
        "database_url": "postgresql://localhost/dummy",
        "minio_access_key": "minioadmin",
        "minio_secret_key": "minioadmin",
        "anthropic_api_key": "",
        "rag_pipeline_url": "http://localhost:3010",
    }
    defaults.update(kwargs)
    return Settings(**defaults)


def _make_pool(fetchrow_return=None, execute_return=None):
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    mock_conn.execute = AsyncMock(return_value=execute_return)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


def _session_row(tenant_id=None, token=None, **kwargs) -> dict:
    defaults = {
        "id": uuid4(),
        "tenant_id": tenant_id or str(uuid4()),
        "visitor_email": "visitor@example.com",
        "visitor_company": "Example Corp",
        "session_token": token or "tok_abc123",
        "message_count": 0,
        "created_at": datetime.now(timezone.utc),
        "last_active_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return defaults


def _make_chatbot(settings=None) -> PortalChatbot:
    return PortalChatbot(settings or _make_settings())


def _mock_rag_response(narrative="Here is the answer.", sources=None):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(return_value=None)
    mock_resp.json = MagicMock(return_value={
        "narrative": narrative,
        "sources": sources or [],
    })
    return mock_resp


# ---------------------------------------------------------------------------
# TestPortalChatbot
# ---------------------------------------------------------------------------

class TestPortalChatbot:

    @pytest.mark.asyncio
    async def test_create_session_generates_unique_token(self):
        """Call create_session twice; verify tokens differ."""
        tenant_id = str(uuid4())
        tokens_seen = []

        # Each call returns a row with a unique token captured from the insert
        call_count = 0

        async def _fake_fetchrow(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Extract the token passed as $5 in the INSERT ($1=id, $2=tenant, $3=email, $4=company, $5=token)
            # args[0] is the SQL, args[1..] are params
            token = args[5] if len(args) > 5 else f"token_{call_count}"
            tokens_seen.append(token)
            return _session_row(tenant_id=tenant_id, token=token)

        mock_conn = AsyncMock()
        mock_conn.fetchrow = _fake_fetchrow
        mock_conn.execute = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        chatbot = _make_chatbot()
        session1 = await chatbot.create_session(mock_pool, tenant_id, "v@e.com", "Corp A")
        session2 = await chatbot.create_session(mock_pool, tenant_id, "v@e.com", "Corp A")

        # Tokens captured from the INSERT parameters must differ
        assert len(tokens_seen) == 2
        assert tokens_seen[0] != tokens_seen[1]

    @pytest.mark.asyncio
    async def test_create_session_stores_visitor_info(self):
        """Verify visitor_email and visitor_company appear in DB insert."""
        tenant_id = str(uuid4())
        visitor_email = "alice@example.com"
        visitor_company = "Alice Corp"

        row = _session_row(
            tenant_id=tenant_id,
            visitor_email=visitor_email,
            visitor_company=visitor_company,
        )
        mock_pool, mock_conn = _make_pool(fetchrow_return=row)
        mock_conn.execute = AsyncMock(return_value=None)

        chatbot = _make_chatbot()
        result = await chatbot.create_session(
            mock_pool, tenant_id, visitor_email, visitor_company
        )

        # Verify the INSERT call included visitor info
        call_args = mock_conn.fetchrow.call_args[0]
        assert visitor_email in call_args, (
            f"visitor_email '{visitor_email}' not found in INSERT args: {call_args}"
        )
        assert visitor_company in call_args, (
            f"visitor_company '{visitor_company}' not found in INSERT args: {call_args}"
        )

    @pytest.mark.asyncio
    async def test_get_session_returns_none_for_invalid_token(self):
        """Mock fetchrow returning None; verify get_session returns None."""
        tenant_id = str(uuid4())
        mock_pool, mock_conn = _make_pool(fetchrow_return=None)
        mock_conn.execute = AsyncMock(return_value=None)

        chatbot = _make_chatbot()
        result = await chatbot.get_session(mock_pool, tenant_id, "invalid-token-xyz")

        assert result is None

    @pytest.mark.asyncio
    async def test_send_message_inserts_both_messages(self):
        """Mock DB + RAG; verify execute called at least twice (user + assistant)."""
        tenant_id = str(uuid4())
        session_row = _session_row(tenant_id=tenant_id, token="valid-token")

        mock_pool, mock_conn = _make_pool(fetchrow_return=session_row)
        mock_conn.execute = AsyncMock(return_value=None)

        chatbot = _make_chatbot()

        with patch.object(
            chatbot._http, 'post',
            new=AsyncMock(return_value=_mock_rag_response("RAG answer."))
        ):
            result = await chatbot.send_message(
                mock_pool, tenant_id, "valid-token", "What is your encryption policy?", "127.0.0.1"
            )

        # At minimum: INSERT user message, INSERT assistant message, UPDATE session
        assert mock_conn.execute.call_count >= 2
        assert result["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_send_message_rag_unavailable_fallback(self):
        """Patch httpx ConnectError; verify assistant message still inserted with fallback."""
        import httpx
        tenant_id = str(uuid4())
        session_row = _session_row(tenant_id=tenant_id, token="valid-token")

        mock_pool, mock_conn = _make_pool(fetchrow_return=session_row)
        mock_conn.execute = AsyncMock(return_value=None)

        chatbot = _make_chatbot()

        with patch.object(
            chatbot._http, 'post',
            new=AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        ):
            result = await chatbot.send_message(
                mock_pool, tenant_id, "valid-token", "Tell me about your security.", "127.0.0.1"
            )

        # Should still return an assistant message (fallback text)
        assert result["role"] == "assistant"
        assert isinstance(result["content"], str) and len(result["content"]) > 0
        # Both user and assistant inserts must still have happened
        assert mock_conn.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_send_message_increments_count(self):
        """Verify UPDATE session is executed with message_count increment."""
        tenant_id = str(uuid4())
        session_row = _session_row(tenant_id=tenant_id, token="valid-token", message_count=4)

        mock_pool, mock_conn = _make_pool(fetchrow_return=session_row)
        mock_conn.execute = AsyncMock(return_value=None)

        chatbot = _make_chatbot()

        with patch.object(
            chatbot._http, 'post',
            new=AsyncMock(return_value=_mock_rag_response("Answer."))
        ):
            await chatbot.send_message(
                mock_pool, tenant_id, "valid-token", "Hello?", "127.0.0.1"
            )

        # Find the UPDATE call and confirm it references message_count
        update_calls = [
            c for c in mock_conn.execute.call_args_list
            if "UPDATE" in (c[0][0].upper() if c[0] else "")
        ]
        assert len(update_calls) >= 1
        update_sql = update_calls[0][0][0]
        assert "message_count" in update_sql

    @pytest.mark.asyncio
    async def test_send_message_invalid_session_raises(self):
        """get_session returns None; verify ValueError raised."""
        tenant_id = str(uuid4())
        mock_pool, mock_conn = _make_pool(fetchrow_return=None)
        mock_conn.execute = AsyncMock(return_value=None)

        chatbot = _make_chatbot()

        with pytest.raises(ValueError, match="[Ii]nvalid"):
            await chatbot.send_message(
                mock_pool, tenant_id, "bogus-token", "Hello?", "127.0.0.1"
            )

    @pytest.mark.asyncio
    async def test_sources_from_rag_stored(self):
        """Mock RAG returning sources; verify sources appear in assistant message."""
        tenant_id = str(uuid4())
        session_row = _session_row(tenant_id=tenant_id, token="valid-token")

        mock_pool, mock_conn = _make_pool(fetchrow_return=session_row)
        mock_conn.execute = AsyncMock(return_value=None)

        rag_sources = [{"title": "Policy X", "url": "https://example.com/policy-x"}]
        chatbot = _make_chatbot()

        with patch.object(
            chatbot._http, 'post',
            new=AsyncMock(return_value=_mock_rag_response(
                narrative="See Policy X for details.",
                sources=rag_sources,
            ))
        ):
            result = await chatbot.send_message(
                mock_pool, tenant_id, "valid-token", "What is your data retention policy?", "127.0.0.1"
            )

        assert result["sources"] == rag_sources

        # Verify the sources were serialized and passed to the DB INSERT for assistant message
        insert_calls = [
            c for c in mock_conn.execute.call_args_list
            if c[0] and "assistant" in c[0][0]
        ]
        assert len(insert_calls) >= 1
        # The sources JSON should appear somewhere in the call args
        assistant_args = insert_calls[0][0]
        sources_json_found = any(
            isinstance(arg, str) and "Policy X" in arg
            for arg in assistant_args
        )
        assert sources_json_found, (
            "RAG sources were not serialized into the assistant message INSERT"
        )
