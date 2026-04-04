import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/tprm-service'))

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.vendor_doc_analyzer import VendorDocAnalyzer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool():
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def _make_analyzer(api_key: str = "sk-dummy", minio_endpoint: str = "http://localhost:9000") -> VendorDocAnalyzer:
    return VendorDocAnalyzer(
        db_pool=_make_pool(),
        minio_endpoint=minio_endpoint,
        minio_access_key="minioadmin",
        minio_secret_key="minioadmin",
        bucket="aegis-vendor-docs",
        anthropic_api_key=api_key,
    )


_SAMPLE_DOC = b"SOC 2 Type II Report\nAudit period: 2024-01-01 to 2024-12-31\nNo exceptions noted."

_VALID_AI_RESPONSE = (
    '{"gaps": [], "score": 8.5, '
    '"summary": "Clean SOC 2 report with no exceptions.", '
    '"certifications_found": ["SOC 2 Type II"], '
    '"expiry_date": "2025-12-31"}'
)


# ---------------------------------------------------------------------------
# TestDocumentAnalysis
# ---------------------------------------------------------------------------

class TestDocumentAnalysis:
    @pytest.mark.asyncio
    async def test_analyze_returns_required_fields(self):
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=_VALID_AI_RESPONSE)]

        mock_client = AsyncMock()
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        analyzer = _make_analyzer(api_key="sk-dummy")
        analyzer._client = mock_client

        from uuid import uuid4
        result = await analyzer.analyze_document(uuid4(), uuid4(), _SAMPLE_DOC)

        assert isinstance(result, dict)
        assert 'gaps' in result
        assert 'score' in result
        assert 'summary' in result
        assert 'certifications_found' in result
        assert 'expiry_date' in result

    @pytest.mark.asyncio
    async def test_score_is_between_0_and_10(self):
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=_VALID_AI_RESPONSE)]

        mock_client = AsyncMock()
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        analyzer = _make_analyzer(api_key="sk-dummy")
        analyzer._client = mock_client

        from uuid import uuid4
        result = await analyzer.analyze_document(uuid4(), uuid4(), _SAMPLE_DOC)

        assert isinstance(result['score'], (int, float))
        assert 0.0 <= float(result['score']) <= 10.0

    @pytest.mark.asyncio
    async def test_no_api_key_returns_fallback(self):
        analyzer = _make_analyzer(api_key="")
        # _client is None

        from uuid import uuid4
        result = await analyzer.analyze_document(uuid4(), uuid4(), _SAMPLE_DOC)

        assert isinstance(result, dict)
        assert 'score' in result
        assert 'summary' in result
        assert 'manual review' in result['summary'].lower()

    @pytest.mark.asyncio
    async def test_claude_failure_returns_fallback(self):
        mock_client = AsyncMock()
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("Claude API timeout"))

        analyzer = _make_analyzer(api_key="sk-dummy")
        analyzer._client = mock_client

        from uuid import uuid4
        # Must not raise
        result = await analyzer.analyze_document(uuid4(), uuid4(), _SAMPLE_DOC)

        assert isinstance(result, dict)
        assert 'score' in result
        assert 'gaps' in result
        assert 'summary' in result

    @pytest.mark.asyncio
    async def test_upload_document_graceful_without_minio(self):
        """upload_document() returns a UUID-like value even when MinIO is unavailable."""
        from uuid import uuid4
        from unittest.mock import patch

        # Patch the conn.fetchval to return a UUID (simulating DB insert returning id)
        doc_id = uuid4()
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=doc_id)
        pool = MagicMock()
        pool.acquire = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        analyzer = VendorDocAnalyzer(
            db_pool=pool,
            minio_endpoint="http://invalid-host-does-not-exist:9000",
            minio_access_key="x",
            minio_secret_key="x",
            bucket="aegis-vendor-docs",
            anthropic_api_key="",
        )
        # _minio may be set (MinIO client init doesn't connect), force None for test
        analyzer._minio = None

        result = await analyzer.upload_document(
            tenant_id=uuid4(),
            vendor_id=uuid4(),
            document_type='soc2_type2',
            filename='report.pdf',
            content=_SAMPLE_DOC,
        )
        # Must return without raising and produce a non-None value (the UUID from DB)
        assert result is not None


# ---------------------------------------------------------------------------
# TestVendorDocAnalyzerInit
# ---------------------------------------------------------------------------

class TestVendorDocAnalyzerInit:
    def test_minio_failure_does_not_crash_init(self):
        """Passing an invalid MinIO endpoint must not raise during __init__."""
        # MinIO client initialisation is graceful — the constructor catches exceptions
        analyzer = VendorDocAnalyzer(
            db_pool=_make_pool(),
            minio_endpoint="http://completely-invalid-host-999.internal:9999",
            minio_access_key="bad",
            minio_secret_key="bad",
            bucket="test-bucket",
            anthropic_api_key="",
        )
        # Object created without exception; _minio may be None or a client object
        assert analyzer is not None
