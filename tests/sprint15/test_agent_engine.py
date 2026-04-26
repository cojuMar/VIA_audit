"""Sprint 15 — AgentEngine unit tests."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/ai-agent-service"),
)

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    from src.agent_engine import AgentEngine

    settings = MagicMock()
    settings.anthropic_api_key = ""  # No API key → fallback mode
    settings.agent_model = "claude-opus-4-5"
    settings.max_conversation_tokens = 100000

    tool_executor = AsyncMock()
    return AgentEngine(settings, tool_executor)


@pytest.fixture
def engine_with_key():
    from src.agent_engine import AgentEngine

    settings = MagicMock()
    settings.anthropic_api_key = "sk-dummy"
    settings.agent_model = "claude-opus-4-5"
    settings.max_conversation_tokens = 100000

    tool_executor = AsyncMock()
    return AgentEngine(settings, tool_executor)


TENANT = "tenant-00000000-0000-0000-0000-000000000015"


# ---------------------------------------------------------------------------
# Helper — build an async-context-manager mock for tenant_conn / pool
# ---------------------------------------------------------------------------

def _make_pool_conn():
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


def _mock_tenant_conn(conn):
    """Return a context-manager mock that yields *conn*."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAgentEngine:

    # --- Construction / client init ---

    def test_no_api_key_client_is_none(self, engine):
        """When anthropic_api_key is empty, the Anthropic client must not be created."""
        assert engine.client is None

    def test_with_api_key_client_created(self, engine_with_key):
        """When a non-empty API key is supplied, an Anthropic client must be created."""
        assert engine_with_key.client is not None

    # --- Fallback response ---

    def test_fallback_response_is_string(self, engine):
        """_fallback_response() must return a non-empty string."""
        response = engine._fallback_response("What is my compliance score?")
        assert isinstance(response, str)
        assert len(response) > 0

    def test_fallback_mentions_api_key(self, engine):
        """_fallback_response() must mention the missing API key."""
        response = engine._fallback_response("test")
        # Must guide the user toward the root cause
        assert "API" in response or "key" in response.lower()

    # --- System prompt ---

    def test_system_prompt_includes_tenant_id(self, engine):
        """_get_system_prompt() must embed the tenant_id in the returned string."""
        prompt = engine._get_system_prompt("tenant-123")
        assert "tenant-123" in prompt

    def test_system_prompt_mentions_tools(self, engine):
        """_get_system_prompt() must describe the agent's available tools/capabilities."""
        prompt = engine._get_system_prompt(TENANT)
        lower = prompt.lower()
        assert "tool" in lower or "capabilit" in lower or "function" in lower

    # --- History loading ---

    @pytest.mark.asyncio
    async def test_load_history_returns_list(self, engine):
        """_load_history() must return a list of message dicts."""
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[
            {"role": "user",      "content": "Hello", "message_id": "m1"},
            {"role": "assistant", "content": "Hi",    "message_id": "m2"},
            {"role": "user",      "content": "Bye",   "message_id": "m3"},
        ])

        with patch("src.agent_engine.tenant_conn") as mock_tc:
            mock_tc.return_value = _mock_tenant_conn(conn)
            pool = MagicMock()
            result = await engine._load_history(pool, TENANT, "conv-id")

        assert isinstance(result, list)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_load_history_reverses_to_chronological(self, engine):
        """_load_history() queries DESC (most-recent first) then reverses to ASC order."""
        conn = AsyncMock()
        # Simulate DESC order returned by the DB: newest first
        conn.fetch = AsyncMock(return_value=[
            {"role": "assistant", "content": "Hi",    "message_id": "m2"},
            {"role": "user",      "content": "Hello", "message_id": "m1"},
        ])

        with patch("src.agent_engine.tenant_conn") as mock_tc:
            mock_tc.return_value = _mock_tenant_conn(conn)
            pool = MagicMock()
            result = await engine._load_history(pool, TENANT, "conv-id")

        # After reversal, first element must be the oldest message
        assert result[0]["message_id"] == "m1"
        assert result[1]["message_id"] == "m2"

    # --- Chat (fallback path) ---

    @pytest.mark.asyncio
    async def test_chat_fallback_when_no_key(self, engine):
        """chat() must return a ChatResponse with fallback content when no API key."""
        from src.models import ChatRequest, ChatResponse

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value="new-conv-id")
        conn.fetchrow = AsyncMock(return_value={"id": "new-conv-id"})
        conn.fetch = AsyncMock(return_value=[])
        conn.execute = AsyncMock()

        pool = MagicMock()

        with patch("src.agent_engine.tenant_conn") as mock_tc:
            mock_tc.return_value = _mock_tenant_conn(conn)
            request = ChatRequest(message="What is my SOC 2 score?")
            result = await engine.chat(pool, TENANT, request)

        assert isinstance(result, ChatResponse)
        assert len(result.content) > 0

    @pytest.mark.asyncio
    async def test_chat_creates_new_conversation_when_no_id(self, engine):
        """When request.conversation_id is None, chat() must create a new conversation."""
        from src.models import ChatRequest

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value="brand-new-conv-id")
        conn.fetchrow = AsyncMock(return_value={"id": "brand-new-conv-id"})
        conn.fetch = AsyncMock(return_value=[])
        conn.execute = AsyncMock()

        pool = MagicMock()

        with patch("src.agent_engine.tenant_conn") as mock_tc:
            mock_tc.return_value = _mock_tenant_conn(conn)
            request = ChatRequest(message="Hello", conversation_id=None)
            await engine.chat(pool, TENANT, request)

        # fetchval must have been called to obtain a new conversation UUID
        assert conn.fetchval.called

    # --- Report generation ---

    @pytest.mark.asyncio
    async def test_generate_report_saves_immutable_record(self, engine_with_key):
        """generate_report() must INSERT an immutable record into agent_reports."""
        from src.models import ReportRequest

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value="report-uuid")
        conn.execute = AsyncMock()

        pool = MagicMock()

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="Report content here.")]
        mock_message.usage.input_tokens = 100
        mock_message.usage.output_tokens = 200

        with patch("src.agent_engine.tenant_conn") as mock_tc:
            mock_tc.return_value = _mock_tenant_conn(conn)
            with patch.object(
                engine_with_key.client.messages,
                "create",
                new=AsyncMock(return_value=mock_message),
            ):
                request = ReportRequest(
                    report_type="compliance_summary",
                    natural_language_request="Give me a compliance summary",
                )
                await engine_with_key.generate_report(pool, TENANT, request)

        # Verify at least one DB call contained INSERT and agent_reports
        all_execute_calls = [str(c) for c in conn.execute.call_args_list]
        all_fetchval_calls = [str(c) for c in conn.fetchval.call_args_list]
        all_calls = all_execute_calls + all_fetchval_calls

        assert any(
            "INSERT" in c and "agent_reports" in c
            for c in all_calls
        ), "generate_report must INSERT a record into agent_reports"

    @pytest.mark.asyncio
    async def test_generate_report_fallback_without_key(self, engine):
        """generate_report() without an API key must return a dict with content mentioning 'API key'."""
        from src.models import ReportRequest

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value="report-uuid")
        conn.execute = AsyncMock()

        pool = MagicMock()

        with patch("src.agent_engine.tenant_conn") as mock_tc:
            mock_tc.return_value = _mock_tenant_conn(conn)
            request = ReportRequest(
                report_type="gap_analysis",
                natural_language_request="Show me all gaps",
            )
            result = await engine.generate_report(pool, TENANT, request)

        assert isinstance(result, dict)
        content = result.get("content", "")
        assert "API" in content or "key" in content.lower() or "api key" in content.lower()
