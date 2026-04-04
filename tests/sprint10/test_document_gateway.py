import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/trust-portal-service'))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4
from datetime import datetime, timezone

from src.document_gateway import DocumentGateway
from src.config import Settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(**kwargs) -> Settings:
    defaults = {
        "database_url": "postgresql://localhost/dummy",
        "minio_access_key": "minioadmin",
        "minio_secret_key": "minioadmin",
        "minio_endpoint": "localhost:9000",
        "anthropic_api_key": "",
    }
    defaults.update(kwargs)
    return Settings(**defaults)


def _make_doc(
    doc_id=None,
    tenant_id=None,
    display_name="SOC 2 Report",
    requires_nda=False,
    is_visible=True,
    object_key=None,
) -> dict:
    t_id = tenant_id or str(uuid4())
    d_id = doc_id or str(uuid4())
    return {
        "id": d_id,
        "tenant_id": t_id,
        "display_name": display_name,
        "description": "Security audit report",
        "document_type": "audit_report",
        "requires_nda": requires_nda,
        "is_visible": is_visible,
        "valid_from": None,
        "valid_until": None,
        "file_size_bytes": 1024,
        "object_key": object_key or f"portal/{t_id}/{d_id}/report.pdf",
    }


def _make_pool_with_fetch(fetch_return=None, fetchrow_return=None, execute_return=None):
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=fetch_return or [])
    mock_conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    mock_conn.execute = AsyncMock(return_value=execute_return)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


def _make_gateway(settings=None, minio_client=None) -> DocumentGateway:
    settings = settings or _make_settings()
    with patch('src.document_gateway.Minio', return_value=minio_client or MagicMock()):
        gateway = DocumentGateway(settings)
    return gateway


# ---------------------------------------------------------------------------
# TestDocumentGateway
# ---------------------------------------------------------------------------

class TestDocumentGateway:

    @pytest.mark.asyncio
    async def test_get_visible_docs_no_nda_filters_protected(self):
        """Without NDA, only non-NDA-required docs returned."""
        tenant_id = str(uuid4())
        doc_a = _make_doc(requires_nda=True, display_name="Confidential NDA Doc")
        doc_b = _make_doc(requires_nda=False, display_name="Public SOC 2 Report")

        # The DB query filters requires_nda=false when nda_verified=False.
        # Simulate DB returning only doc_b.
        mock_pool, mock_conn = _make_pool_with_fetch(fetch_return=[doc_b])

        gateway = _make_gateway()
        results = await gateway.get_visible_documents(mock_pool, tenant_id, nda_verified=False)

        assert len(results) == 1
        assert results[0]["display_name"] == "Public SOC 2 Report"
        assert results[0]["requires_nda"] is False

    @pytest.mark.asyncio
    async def test_get_visible_docs_with_nda_returns_all(self):
        """With NDA verified, both NDA-gated and public docs returned."""
        tenant_id = str(uuid4())
        doc_a = _make_doc(requires_nda=True, display_name="Confidential NDA Doc")
        doc_b = _make_doc(requires_nda=False, display_name="Public SOC 2 Report")

        mock_pool, mock_conn = _make_pool_with_fetch(fetch_return=[doc_a, doc_b])

        gateway = _make_gateway()
        results = await gateway.get_visible_documents(mock_pool, tenant_id, nda_verified=True)

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_visible_docs_filters_invisible(self):
        """Doc with is_visible=False not returned regardless of NDA status."""
        tenant_id = str(uuid4())
        # DB already filters is_visible=true; simulate returning only visible docs.
        visible_doc = _make_doc(is_visible=True, display_name="Visible Doc")
        mock_pool, mock_conn = _make_pool_with_fetch(fetch_return=[visible_doc])

        gateway = _make_gateway()
        results = await gateway.get_visible_documents(mock_pool, tenant_id, nda_verified=True)

        # Invisible docs are filtered by DB — only visible doc returned
        assert len(results) == 1
        assert results[0]["is_visible"] is True

    @pytest.mark.asyncio
    async def test_generate_presigned_url_checks_tenant(self):
        """Doc belonging to different tenant raises ValueError."""
        own_tenant_id = str(uuid4())
        doc_id = str(uuid4())

        # DB returns None (doc not found for this tenant)
        mock_pool, mock_conn = _make_pool_with_fetch(fetchrow_return=None)
        mock_conn.fetchrow = AsyncMock(return_value=None)

        gateway = _make_gateway()

        with pytest.raises((ValueError, RuntimeError)):
            await gateway.generate_presigned_url(
                mock_pool, own_tenant_id, doc_id, "visitor@example.com"
            )

    @pytest.mark.asyncio
    async def test_generate_presigned_url_calls_minio(self):
        """Mock minio presigned_get_object; verify called with correct bucket + key."""
        tenant_id = str(uuid4())
        doc_id = str(uuid4())
        object_key = f"portal/{tenant_id}/{doc_id}/report.pdf"
        doc_row = _make_doc(
            doc_id=doc_id,
            tenant_id=tenant_id,
            object_key=object_key,
            requires_nda=False,
        )
        doc_row["id"] = doc_id

        mock_pool, mock_conn = _make_pool_with_fetch(fetchrow_return=doc_row)
        mock_conn.fetchrow = AsyncMock(return_value=doc_row)
        mock_conn.execute = AsyncMock(return_value=None)

        mock_minio = MagicMock()
        mock_minio.presigned_get_object = MagicMock(return_value="https://minio.local/signed-url")

        gateway = _make_gateway(minio_client=mock_minio)

        url = await gateway.generate_presigned_url(
            mock_pool, tenant_id, doc_id, "visitor@example.com"
        )

        mock_minio.presigned_get_object.assert_called_once()
        call_kwargs = mock_minio.presigned_get_object.call_args
        # First positional arg is bucket, second is object key
        assert call_kwargs[0][0] == gateway._bucket
        assert call_kwargs[0][1] == object_key
        assert url == "https://minio.local/signed-url"

    @pytest.mark.asyncio
    async def test_generate_presigned_url_no_minio_raises(self):
        """Set gateway._minio=None; verify raises RuntimeError."""
        tenant_id = str(uuid4())
        doc_id = str(uuid4())
        object_key = f"portal/{tenant_id}/{doc_id}/report.pdf"
        doc_row = _make_doc(
            doc_id=doc_id,
            tenant_id=tenant_id,
            object_key=object_key,
        )
        doc_row["id"] = doc_id

        mock_pool, mock_conn = _make_pool_with_fetch(fetchrow_return=doc_row)
        mock_conn.fetchrow = AsyncMock(return_value=doc_row)
        mock_conn.execute = AsyncMock(return_value=None)

        gateway = _make_gateway()
        gateway._minio = None  # Simulate MinIO unavailable

        with pytest.raises(RuntimeError, match="unavailable"):
            await gateway.generate_presigned_url(
                mock_pool, tenant_id, doc_id, "visitor@example.com"
            )

    @pytest.mark.asyncio
    async def test_upload_document_stores_in_minio(self):
        """Mock minio.put_object; verify called and DB insert called."""
        tenant_id = str(uuid4())
        file_bytes = b"PDF content here"
        new_doc_row = _make_doc(tenant_id=tenant_id, display_name="New Doc")

        mock_pool, mock_conn = _make_pool_with_fetch(fetchrow_return=new_doc_row)
        mock_conn.fetchrow = AsyncMock(return_value=new_doc_row)
        mock_conn.execute = AsyncMock(return_value=None)

        mock_minio = MagicMock()
        mock_minio.bucket_exists = MagicMock(return_value=True)
        mock_minio.put_object = MagicMock(return_value=None)

        gateway = _make_gateway(minio_client=mock_minio)

        result = await gateway.upload_document(
            mock_pool,
            tenant_id,
            display_name="New Doc",
            doc_type="policy",
            file_bytes=file_bytes,
            requires_nda=False,
            filename="new-doc.pdf",
        )

        mock_minio.put_object.assert_called_once()
        mock_conn.fetchrow.assert_called_once()
        assert result["display_name"] == "New Doc"

    @pytest.mark.asyncio
    async def test_upload_document_minio_failure_does_not_insert(self):
        """Mock minio.put_object raising exception; verify DB insert NOT called."""
        from minio.error import S3Error
        tenant_id = str(uuid4())
        file_bytes = b"PDF content here"

        mock_pool, mock_conn = _make_pool_with_fetch()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock(return_value=None)

        mock_minio = MagicMock()
        mock_minio.bucket_exists = MagicMock(return_value=True)
        mock_minio.put_object = MagicMock(
            side_effect=S3Error("NoSuchBucket", "Bucket not found", "resource", "request-id", "host-id", MagicMock())
        )

        gateway = _make_gateway(minio_client=mock_minio)

        with pytest.raises(RuntimeError, match="upload failed"):
            await gateway.upload_document(
                mock_pool,
                tenant_id,
                display_name="Failing Doc",
                doc_type="policy",
                file_bytes=file_bytes,
                requires_nda=False,
            )

        # DB insert must NOT have been called
        mock_conn.fetchrow.assert_not_called()
