"""
Report storage via MinIO S3-compatible object store.

Reports are stored with:
  - Object Lock COMPLIANCE mode (7-year retention for audit reports)
  - Content-type set correctly per format
  - SHA-256 checksum stored as object metadata
  - Path structure: reports/{tenant_id}/{format}/{year}/{month}/{export_id}.{ext}

The REPORTS_RETENTION_DAYS env var controls retention (default 2555 = ~7 years).
In dev mode (no object lock configured), retention is skipped.
"""

import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from minio import Minio
from minio.commonconfig import COMPLIANCE
from minio.retention import Retention
from .config import settings

logger = logging.getLogger(__name__)

FORMAT_EXTENSIONS = {
    'xbrl':  'xml',
    'ixbrl': 'html',
    'saft':  'xml',
    'gifi':  'xml',
    'pdf_a': 'pdf',
}

FORMAT_CONTENT_TYPES = {
    'xbrl':  'application/xml',
    'ixbrl': 'application/xhtml+xml',
    'saft':  'application/xml',
    'gifi':  'application/xml',
    'pdf_a': 'application/pdf',
}


class ReportStorage:
    """Stores and retrieves generated reports from MinIO."""

    def __init__(self):
        from urllib.parse import urlparse
        parsed = urlparse(settings.minio_endpoint)
        secure = parsed.scheme == 'https'
        host = parsed.netloc or parsed.path

        self._client = Minio(
            host,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=secure,
        )
        self._bucket = settings.minio_reports_bucket
        self._retention_days = settings.reports_retention_days

    def upload(
        self,
        export_id: str,
        tenant_id: str,
        report_format: str,
        data: bytes,
        checksum_sha256: Optional[bytes] = None,
    ) -> str:
        """Upload a report to MinIO and return the object path.

        Args:
            export_id: Report export UUID
            tenant_id: Tenant UUID (used in path)
            report_format: 'xbrl', 'ixbrl', 'saft', 'gifi', or 'pdf_a'
            data: Report bytes
            checksum_sha256: SHA-256 of data (computed if not provided)

        Returns:
            Object path in MinIO (e.g. 'reports/abc123/pdf_a/2026/04/xyz.pdf')
        """
        import io

        ext = FORMAT_EXTENSIONS.get(report_format, 'bin')
        content_type = FORMAT_CONTENT_TYPES.get(report_format, 'application/octet-stream')
        now = datetime.now(timezone.utc)

        object_path = (
            f"reports/{tenant_id[:8]}/{report_format}/"
            f"{now.year}/{now.month:02d}/{export_id}.{ext}"
        )

        checksum = checksum_sha256 or hashlib.sha256(data).digest()

        metadata = {
            "x-amz-meta-export-id": export_id,
            "x-amz-meta-tenant-id": tenant_id[:8],
            "x-amz-meta-format": report_format,
            "x-amz-meta-sha256": checksum.hex(),
            "x-amz-meta-generated-at": now.isoformat(),
        }

        # Ensure bucket exists
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
            logger.info("Created reports bucket: %s", self._bucket)

        # Upload with COMPLIANCE retention if Object Lock is enabled
        try:
            retain_until = now + timedelta(days=self._retention_days)
            self._client.put_object(
                self._bucket,
                object_path,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type,
                metadata=metadata,
                retention=Retention(COMPLIANCE, retain_until),
            )
        except Exception as e:
            if "object lock" in str(e).lower() or "retention" in str(e).lower():
                # Dev mode: bucket doesn't have object lock enabled
                logger.warning("Object lock not available (dev mode) — uploading without retention: %s", e)
                self._client.put_object(
                    self._bucket,
                    object_path,
                    io.BytesIO(data),
                    length=len(data),
                    content_type=content_type,
                    metadata=metadata,
                )
            else:
                raise

        logger.info("Report stored: %s (%d bytes)", object_path, len(data))
        return object_path

    def download(self, object_path: str) -> bytes:
        """Download a report from MinIO."""
        response = self._client.get_object(self._bucket, object_path)
        try:
            return response.read()
        finally:
            response.close()

    def get_presigned_url(self, object_path: str, expires_seconds: int = 3600) -> str:
        """Generate a presigned download URL."""
        from datetime import timedelta
        return self._client.presigned_get_object(
            self._bucket,
            object_path,
            expires=timedelta(seconds=expires_seconds),
        )
