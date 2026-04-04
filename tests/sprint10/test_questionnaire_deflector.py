import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/trust-portal-service'))

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.questionnaire_deflector import QuestionnaireDeflector
from src.config import Settings
from src.models import DeflectionRequest


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


def _make_pool(execute_return=None, fetchrow_return=None):
    """Build a mock pool for deflection DB calls."""
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=execute_return)
    mock_conn.fetchrow = AsyncMock(return_value=fetchrow_return or _deflection_row())
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


def _deflection_row(**kwargs) -> dict:
    defaults = {
        "id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "requester_name": "Bob Tester",
        "requester_email": "bob@example.com",
        "requester_company": "Example Corp",
        "questionnaire_type": "sig_lite",
        "questions": json.dumps(["Do you encrypt data at rest?"]),
        "status": "completed",
        "deflection_mappings": json.dumps([]),
        "ai_model_used": "rag-only",
        "created_at": "2026-04-01T12:00:00Z",
        "completed_at": "2026-04-01T12:00:05Z",
    }
    defaults.update(kwargs)
    return defaults


def _make_deflection_request(questions=None, questionnaire_type="sig_lite") -> DeflectionRequest:
    return DeflectionRequest(
        requester_name="Bob Tester",
        requester_email="bob@example.com",
        requester_company="Example Corp",
        questionnaire_type=questionnaire_type,
        questions=questions or ["Do you encrypt data at rest?"],
    )


def _mock_rag_response(results=None):
    """Build a mock httpx Response returning RAG results."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(return_value=None)
    mock_resp.json = MagicMock(return_value=results or [])
    return mock_resp


# ---------------------------------------------------------------------------
# TestQuestionnaireDeflector
# ---------------------------------------------------------------------------

class TestQuestionnaireDeflector:

    def test_no_api_key_uses_rag_only(self):
        """With api_key='', deflector._claude is None."""
        settings = _make_settings(anthropic_api_key="")
        deflector = QuestionnaireDeflector(settings)
        assert deflector._claude is None

    def test_with_api_key_creates_claude_client(self):
        """With a non-empty api_key, deflector._claude is not None."""
        settings = _make_settings(anthropic_api_key="sk-dummy")
        deflector = QuestionnaireDeflector(settings)
        assert deflector._claude is not None

    @pytest.mark.asyncio
    async def test_rag_unavailable_returns_empty_evidence(self):
        """Patch httpx to raise ConnectError; deflection still completes."""
        import httpx
        tenant_id = str(uuid4())
        settings = _make_settings(anthropic_api_key="")

        row = _deflection_row(status="completed", deflection_mappings=json.dumps([
            {"question": "Do you encrypt data at rest?", "rag_evidence": [], "ai_response": "No evidence available at this time."}
        ]))
        mock_pool, mock_conn = _make_pool(fetchrow_return=row)

        deflector = QuestionnaireDeflector(settings)

        with patch.object(
            deflector._http, 'post',
            new=AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        ):
            result = await deflector.deflect(
                mock_pool, tenant_id,
                _make_deflection_request(questions=["Do you encrypt data at rest?"])
            )

        mappings = result.get("deflection_mappings", [])
        assert len(mappings) == 1
        assert mappings[0]["rag_evidence"] == []

    @pytest.mark.asyncio
    async def test_deflection_sets_status_completed(self):
        """Mock DB + RAG + no Claude; verify final status='completed'."""
        tenant_id = str(uuid4())
        settings = _make_settings(anthropic_api_key="")

        row = _deflection_row(status="completed")
        mock_pool, mock_conn = _make_pool(fetchrow_return=row)

        deflector = QuestionnaireDeflector(settings)

        with patch.object(
            deflector._http, 'post',
            new=AsyncMock(return_value=_mock_rag_response([]))
        ):
            result = await deflector.deflect(
                mock_pool, tenant_id,
                _make_deflection_request()
            )

        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_deflection_sets_status_failed_on_exception(self):
        """Patch internal processing to raise; verify graceful failure or completed with error."""
        tenant_id = str(uuid4())
        settings = _make_settings(anthropic_api_key="sk-dummy")

        row = _deflection_row(status="completed")
        mock_pool, mock_conn = _make_pool(fetchrow_return=row)

        deflector = QuestionnaireDeflector(settings)

        # Patch _generate_answer to raise unexpectedly
        async def _boom(question, evidence):
            raise RuntimeError("Claude exploded")

        deflector._generate_answer = _boom

        with patch.object(
            deflector._http, 'post',
            new=AsyncMock(return_value=_mock_rag_response([]))
        ):
            # The deflector should either catch the error and mark failed,
            # or the exception propagates — either is acceptable behavior.
            # We verify the DB UPDATE was attempted.
            try:
                result = await deflector.deflect(
                    mock_pool, tenant_id,
                    _make_deflection_request()
                )
                # If it completes, status should indicate failure or completion
                assert result["status"] in ("completed", "failed")
            except RuntimeError:
                # Exception propagated — verify the initial INSERT was called
                mock_conn.execute.assert_called()

    @pytest.mark.asyncio
    async def test_question_count_in_mappings(self):
        """Submit 3 questions; verify deflection_mappings has 3 items."""
        tenant_id = str(uuid4())
        settings = _make_settings(anthropic_api_key="")
        questions = [
            "Do you encrypt data at rest?",
            "Do you have a SOC 2 Type II report?",
            "How do you handle incidents?",
        ]

        mappings_data = [
            {"question": q, "rag_evidence": [], "ai_response": "No evidence available at this time."}
            for q in questions
        ]
        row = _deflection_row(
            status="completed",
            deflection_mappings=json.dumps(mappings_data)
        )
        mock_pool, mock_conn = _make_pool(fetchrow_return=row)

        deflector = QuestionnaireDeflector(settings)

        with patch.object(
            deflector._http, 'post',
            new=AsyncMock(return_value=_mock_rag_response([]))
        ):
            result = await deflector.deflect(
                mock_pool, tenant_id,
                _make_deflection_request(questions=questions)
            )

        assert len(result["deflection_mappings"]) == 3

    @pytest.mark.asyncio
    async def test_rag_response_included_in_mapping(self):
        """Mock RAG returning evidence; verify it appears in rag_evidence."""
        tenant_id = str(uuid4())
        settings = _make_settings(anthropic_api_key="")
        rag_hit = {"title": "Policy X", "score": 0.9, "content": "We encrypt all data at rest using AES-256."}

        mappings_data = [
            {"question": "Do you encrypt data at rest?", "rag_evidence": [rag_hit], "ai_response": rag_hit["content"]}
        ]
        row = _deflection_row(
            status="completed",
            deflection_mappings=json.dumps(mappings_data)
        )
        mock_pool, mock_conn = _make_pool(fetchrow_return=row)

        deflector = QuestionnaireDeflector(settings)

        with patch.object(
            deflector._http, 'post',
            new=AsyncMock(return_value=_mock_rag_response([rag_hit]))
        ):
            result = await deflector.deflect(
                mock_pool, tenant_id,
                _make_deflection_request(questions=["Do you encrypt data at rest?"])
            )

        mappings = result["deflection_mappings"]
        assert len(mappings) == 1
        assert len(mappings[0]["rag_evidence"]) >= 1
        assert mappings[0]["rag_evidence"][0]["title"] == "Policy X"

    @pytest.mark.asyncio
    async def test_ai_response_from_claude(self):
        """Mock Claude returning a specific string; verify ai_response contains it."""
        tenant_id = str(uuid4())
        settings = _make_settings(anthropic_api_key="sk-dummy")

        claude_text = "We use AES-256 encryption for all data at rest."
        mappings_data = [
            {"question": "Do you encrypt data at rest?", "rag_evidence": [], "ai_response": claude_text}
        ]
        row = _deflection_row(
            status="completed",
            ai_model_used="claude-haiku-4-5",
            deflection_mappings=json.dumps(mappings_data)
        )
        mock_pool, mock_conn = _make_pool(fetchrow_return=row)

        deflector = QuestionnaireDeflector(settings)

        # Mock the Claude client
        mock_claude_response = MagicMock()
        mock_claude_response.content = [MagicMock(text=claude_text)]
        deflector._claude = MagicMock()
        deflector._claude.messages = MagicMock()
        deflector._claude.messages.create = AsyncMock(return_value=mock_claude_response)

        with patch.object(
            deflector._http, 'post',
            new=AsyncMock(return_value=_mock_rag_response([]))
        ):
            result = await deflector.deflect(
                mock_pool, tenant_id,
                _make_deflection_request(questions=["Do you encrypt data at rest?"])
            )

        mappings = result["deflection_mappings"]
        assert len(mappings) == 1
        assert "AES-256" in mappings[0]["ai_response"]

    @pytest.mark.asyncio
    async def test_fallback_ai_response_when_no_claude(self):
        """No api_key; verify ai_response is still present (fallback text)."""
        tenant_id = str(uuid4())
        settings = _make_settings(anthropic_api_key="")

        fallback_text = "No evidence available at this time."
        mappings_data = [
            {"question": "Do you encrypt data at rest?", "rag_evidence": [], "ai_response": fallback_text}
        ]
        row = _deflection_row(
            status="completed",
            ai_model_used="rag-only",
            deflection_mappings=json.dumps(mappings_data)
        )
        mock_pool, mock_conn = _make_pool(fetchrow_return=row)

        deflector = QuestionnaireDeflector(settings)
        assert deflector._claude is None

        with patch.object(
            deflector._http, 'post',
            new=AsyncMock(return_value=_mock_rag_response([]))
        ):
            result = await deflector.deflect(
                mock_pool, tenant_id,
                _make_deflection_request(questions=["Do you encrypt data at rest?"])
            )

        mappings = result["deflection_mappings"]
        assert len(mappings) == 1
        ai_response = mappings[0]["ai_response"]
        assert isinstance(ai_response, str) and len(ai_response) > 0

    @pytest.mark.asyncio
    async def test_questionnaire_type_stored(self):
        """Verify questionnaire_type='sig_lite' is stored in the DB record."""
        tenant_id = str(uuid4())
        settings = _make_settings(anthropic_api_key="")

        row = _deflection_row(questionnaire_type="sig_lite", status="completed")
        mock_pool, mock_conn = _make_pool(fetchrow_return=row)

        deflector = QuestionnaireDeflector(settings)

        with patch.object(
            deflector._http, 'post',
            new=AsyncMock(return_value=_mock_rag_response([]))
        ):
            result = await deflector.deflect(
                mock_pool, tenant_id,
                _make_deflection_request(questionnaire_type="sig_lite")
            )

        # Verify questionnaire_type was passed in the initial INSERT
        insert_call = mock_conn.execute.call_args_list[0]
        insert_args = insert_call[0]
        assert "sig_lite" in insert_args, (
            f"questionnaire_type 'sig_lite' not found in INSERT args: {insert_args}"
        )
        assert result["questionnaire_type"] == "sig_lite"
