from __future__ import annotations

import io
from datetime import timedelta
from uuid import uuid4

import asyncpg
from minio import Minio
from minio.commonconfig import ENABLED
from minio.lifecycleconfig import LifecycleConfig, Rule, Expiration, Filter

from .config import settings
from .db import tenant_conn


class PhotoManager:
    def __init__(self, pool: asyncpg.Pool, minio_client: Minio) -> None:
        self.pool = pool
        self.minio = minio_client
        self.bucket = settings.minio_bucket

    # ------------------------------------------------------------------

    async def ensure_bucket(self) -> None:
        """Create MinIO bucket if it does not exist, with a lifecycle policy."""
        found = self.minio.bucket_exists(self.bucket)
        if not found:
            self.minio.make_bucket(self.bucket)
            # Set a 365-day expiration lifecycle for cost management
            config = LifecycleConfig(
                [
                    Rule(
                        ENABLED,
                        rule_filter=Filter(prefix=""),
                        rule_id="expire-after-365-days",
                        expiration=Expiration(days=365),
                    )
                ]
            )
            self.minio.set_bucket_lifecycle(self.bucket, config)

    # ------------------------------------------------------------------

    async def upload_photo(
        self,
        tenant_id: str,
        audit_id: str,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
        response_id: str | None = None,
        caption: str | None = None,
        gps_lat: float | None = None,
        gps_lon: float | None = None,
        taken_at: str | None = None,
        sync_id: str | None = None,
    ) -> dict:
        """
        Upload photo bytes to MinIO and record the metadata in field_audit_photos
        (immutable table). Deduplicates by sync_id.
        """
        # Check dedup by sync_id before uploading
        if sync_id:
            async with tenant_conn(self.pool, tenant_id) as conn:
                existing = await conn.fetchrow(
                    "SELECT * FROM field_audit_photos WHERE sync_id = $1",
                    sync_id,
                )
            if existing:
                presigned = await self.get_presigned_url(
                    existing["minio_object_key"]
                )
                result = dict(existing)
                result["photo_url"] = presigned
                return result

        object_key = f"{tenant_id}/{audit_id}/{uuid4()}-{filename}"

        # Upload to MinIO
        self.minio.put_object(
            self.bucket,
            object_key,
            io.BytesIO(file_bytes),
            length=len(file_bytes),
            content_type=mime_type,
        )

        presigned_url = await self.get_presigned_url(object_key)

        # Insert immutable record
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO field_audit_photos (
                    field_audit_id,
                    response_id,
                    minio_object_key,
                    filename,
                    mime_type,
                    caption,
                    gps_latitude,
                    gps_longitude,
                    taken_at,
                    sync_id,
                    created_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8,
                    $9::timestamptz, $10, NOW()
                )
                RETURNING *
                """,
                audit_id,
                response_id,
                object_key,
                filename,
                mime_type,
                caption,
                gps_lat,
                gps_lon,
                taken_at,
                sync_id,
            )

        result = dict(row)
        result["photo_url"] = presigned_url
        return result

    # ------------------------------------------------------------------

    async def get_presigned_url(
        self, object_key: str, expires_hours: int = 24
    ) -> str:
        """Generate a presigned GET URL for a MinIO object."""
        url = self.minio.presigned_get_object(
            self.bucket,
            object_key,
            expires=timedelta(hours=expires_hours),
        )
        return url

    # ------------------------------------------------------------------

    async def get_photos_for_audit(
        self, tenant_id: str, audit_id: str
    ) -> list[dict]:
        """Return all photos for an audit with presigned URLs attached."""
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM field_audit_photos
                WHERE field_audit_id = $1
                ORDER BY taken_at NULLS LAST, created_at
                """,
                audit_id,
            )

        photos = []
        for r in rows:
            photo = dict(r)
            try:
                photo["photo_url"] = await self.get_presigned_url(
                    r["minio_object_key"]
                )
            except Exception:
                photo["photo_url"] = None
            photos.append(photo)
        return photos

    # ------------------------------------------------------------------

    async def get_photo_upload_url(
        self, tenant_id: str, audit_id: str, filename: str
    ) -> dict:
        """
        Generate a presigned PUT URL so the mobile client can upload directly
        to MinIO without routing large files through the service.
        """
        object_key = f"{tenant_id}/{audit_id}/{uuid4()}-{filename}"
        expires_seconds = 3600

        upload_url = self.minio.presigned_put_object(
            self.bucket,
            object_key,
            expires=timedelta(seconds=expires_seconds),
        )

        return {
            "upload_url": upload_url,
            "object_key": object_key,
            "expires_in_seconds": expires_seconds,
        }
