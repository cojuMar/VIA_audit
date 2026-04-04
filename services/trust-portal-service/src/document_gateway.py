import io
import logging
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import asyncpg
from minio import Minio
from minio.error import S3Error

from .config import Settings
from .db import tenant_conn

logger = logging.getLogger(__name__)


class DocumentGateway:
    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.minio_bucket_portal
        try:
            self._minio = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=False,
            )
        except Exception as exc:
            logger.warning("MinIO client init failed — document uploads disabled: %s", exc)
            self._minio = None  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    async def get_visible_documents(
        self, pool: asyncpg.Pool, tenant_id: str, nda_verified: bool
    ) -> list[dict]:
        """Return visible portal documents, filtering NDA-gated ones when needed."""
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT id, tenant_id, display_name, description, document_type,
                       requires_nda, is_visible, valid_from, valid_until,
                       file_size_bytes
                FROM portal_documents
                WHERE tenant_id = $1
                  AND is_visible = true
                  AND ($2 OR requires_nda = false)
                ORDER BY display_name
                """,
                tenant_id,
                nda_verified,
            )
        return [dict(r) for r in rows]

    async def generate_presigned_url(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        document_id: str,
        visitor_email: str,
    ) -> str:
        """Verify ownership, generate a 1-hour presigned GET URL, log access."""
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT id, object_key, display_name, requires_nda
                FROM portal_documents
                WHERE id = $1 AND tenant_id = $2 AND is_visible = true
                """,
                document_id,
                tenant_id,
            )
            if row is None:
                raise ValueError("Document not found or not accessible")

            # Log access event
            await conn.execute(
                """
                INSERT INTO trust_portal_access_logs
                    (id, tenant_id, event_type, visitor_email, document_id,
                     ip_address, user_agent, occurred_at)
                VALUES ($1, $2, 'document_download', $3, $4, 'system', 'system', NOW())
                """,
                str(uuid4()),
                tenant_id,
                visitor_email,
                document_id,
            )

        if self._minio is None:
            raise RuntimeError("Document storage is temporarily unavailable")

        url = self._minio.presigned_get_object(
            self._bucket,
            row["object_key"],
            expires=timedelta(hours=1),
        )
        return url

    async def upload_document(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        display_name: str,
        doc_type: str,
        file_bytes: bytes,
        requires_nda: bool,
        filename: str = "document",
        description: str | None = None,
    ) -> dict:
        """Upload file to MinIO and create a DB record."""
        doc_id = str(uuid4())
        object_key = f"portal/{tenant_id}/{doc_id}/{filename}"

        if self._minio is not None:
            try:
                self._ensure_bucket()
                self._minio.put_object(
                    self._bucket,
                    object_key,
                    io.BytesIO(file_bytes),
                    length=len(file_bytes),
                )
            except S3Error as exc:
                logger.error("MinIO upload failed: %s", exc)
                raise RuntimeError("File upload failed") from exc
        else:
            logger.warning("MinIO unavailable — skipping actual upload for doc %s", doc_id)

        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO portal_documents (
                    id, tenant_id, display_name, description, document_type,
                    requires_nda, is_visible, object_key, file_size_bytes, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, true, $7, $8, NOW())
                RETURNING *
                """,
                doc_id,
                tenant_id,
                display_name,
                description,
                doc_type,
                requires_nda,
                object_key,
                len(file_bytes),
            )
        return dict(row)

    async def soft_delete(
        self, pool: asyncpg.Pool, tenant_id: str, document_id: str
    ) -> bool:
        """Set is_visible = false (soft delete)."""
        async with tenant_conn(pool, tenant_id) as conn:
            result = await conn.execute(
                """
                UPDATE portal_documents
                SET is_visible = false, updated_at = NOW()
                WHERE id = $1 AND tenant_id = $2
                """,
                document_id,
                tenant_id,
            )
        return result == "UPDATE 1"

    async def list_all_documents(
        self, pool: asyncpg.Pool, tenant_id: str
    ) -> list[dict]:
        """Admin view — returns all documents including hidden ones."""
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT id, tenant_id, display_name, description, document_type,
                       requires_nda, is_visible, valid_from, valid_until,
                       file_size_bytes, object_key, created_at
                FROM portal_documents
                WHERE tenant_id = $1
                ORDER BY created_at DESC
                """,
                tenant_id,
            )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_bucket(self) -> None:
        if not self._minio.bucket_exists(self._bucket):
            self._minio.make_bucket(self._bucket)
