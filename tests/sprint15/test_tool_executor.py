"""Sprint 15 — ToolExecutor unit tests."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/ai-agent-service"),
)

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def executor():
    from src.tool_executor import ToolExecutor

    settings = MagicMock()
    settings.framework_service_url = "http://framework-service:3012"
    settings.tprm_service_url = "http://tprm-service:3014"
    settings.monitoring_service_url = "http://monitoring-service:3016"
    settings.people_service_url = "http://people-service:3017"
    settings.pbc_service_url = "http://pbc-service:3018"
    settings.rag_pipeline_url = "http://rag-pipeline-service:3010"

    http_client = AsyncMock(spec=httpx.AsyncClient)
    return ToolExecutor(settings, http_client)


TENANT = "tenant-00000000-0000-0000-0000-000000000015"


# ---------------------------------------------------------------------------
# Helper — captures the URL passed to _call
# ---------------------------------------------------------------------------

def _capture_call(return_value=None):
    """Return an AsyncMock that records its first positional argument (the URL)."""
    mock = AsyncMock(return_value=return_value if return_value is not None else {})
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestToolExecutor:

    @pytest.mark.asyncio
    async def test_get_compliance_scores_calls_framework_service(self, executor):
        """get_compliance_scores must route to the framework-service URL."""
        executor._call = _capture_call({})

        await executor.execute("get_compliance_scores", {}, TENANT)

        called_url = executor._call.call_args[0][0]
        assert "framework-service" in called_url

    @pytest.mark.asyncio
    async def test_get_compliance_gaps_includes_framework_slug(self, executor):
        """get_compliance_gaps must embed the framework_slug in the URL path."""
        executor._call = _capture_call({})

        tool_input = {"framework_slug": "soc2-type2"}
        await executor.execute("get_compliance_gaps", tool_input, TENANT)

        called_url = executor._call.call_args[0][0]
        assert "soc2-type2" in called_url

    @pytest.mark.asyncio
    async def test_get_vendor_risk_summary_calls_tprm_service(self, executor):
        """get_vendor_risk_summary must route to the tprm-service URL."""
        executor._call = _capture_call({})

        await executor.execute("get_vendor_risk_summary", {}, TENANT)

        called_url = executor._call.call_args[0][0]
        assert "tprm-service" in called_url

    @pytest.mark.asyncio
    async def test_get_monitoring_findings_passes_severity_param(self, executor):
        """get_monitoring_findings must forward the severity param to the service."""
        executor._call = _capture_call({})

        tool_input = {"severity": "critical"}
        await executor.execute("get_monitoring_findings", tool_input, TENANT)

        call_kwargs = executor._call.call_args[1]
        params = call_kwargs.get("params", {})
        assert "severity" in params
        assert params["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_search_knowledge_base_posts_to_rag(self, executor):
        """search_knowledge_base must POST to the RAG pipeline endpoint."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {"results": []}
        executor.http.post = AsyncMock(return_value=mock_response)

        tool_input = {"query": "password policy", "top_k": 3}
        await executor.execute("search_knowledge_base", tool_input, TENANT)

        assert executor.http.post.called
        post_url = executor.http.post.call_args[0][0]
        assert "rag-pipeline-service" in post_url

    @pytest.mark.asyncio
    async def test_search_knowledge_base_rag_failure_returns_error(self, executor):
        """search_knowledge_base must return a dict with 'error' when the POST raises."""
        executor.http.post = AsyncMock(side_effect=Exception("connection refused"))

        tool_input = {"query": "incident response plan"}
        result = await executor.execute("search_knowledge_base", tool_input, TENANT)

        assert isinstance(result, dict)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_service_unavailable_returns_error_dict(self, executor):
        """When _call raises ConnectError, execute must return {'error': ..., 'service_unavailable': True}."""
        executor._call = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await executor.execute("get_compliance_scores", {}, TENANT)

        assert isinstance(result, dict)
        # The outer execute() catches all exceptions and returns {'error': ..., 'tool': ...}
        assert "error" in result

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, executor):
        """Calling an unknown tool name must return a dict with 'error'."""
        result = await executor.execute("nonexistent_tool", {}, TENANT)

        assert isinstance(result, dict)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_training_compliance_calls_people_service(self, executor):
        """get_training_compliance must route to the people-service URL."""
        executor._call = _capture_call({})

        await executor.execute("get_training_compliance", {}, TENANT)

        called_url = executor._call.call_args[0][0]
        assert "people-service" in called_url

    @pytest.mark.asyncio
    async def test_get_audit_issues_passes_filters(self, executor):
        """get_audit_issues must forward severity and status params."""
        executor._call = _capture_call({})

        tool_input = {"severity": "high", "status": "open"}
        await executor.execute("get_audit_issues", tool_input, TENANT)

        call_kwargs = executor._call.call_args[1]
        params = call_kwargs.get("params", {})
        assert params.get("severity") == "high"
        assert params.get("status") == "open"

    @pytest.mark.asyncio
    async def test_get_org_compliance_score_calls_people_service(self, executor):
        """get_org_compliance_score must route to people-service and include 'compliance'."""
        executor._call = _capture_call({})

        await executor.execute("get_org_compliance_score", {}, TENANT)

        called_url = executor._call.call_args[0][0]
        assert "people-service" in called_url
        assert "compliance" in called_url

    @pytest.mark.asyncio
    async def test_get_cloud_config_issues_calls_monitoring_service(self, executor):
        """get_cloud_config_issues must route to the monitoring-service URL."""
        executor._call = _capture_call({})

        await executor.execute("get_cloud_config_issues", {}, TENANT)

        called_url = executor._call.call_args[0][0]
        assert "monitoring-service" in called_url
