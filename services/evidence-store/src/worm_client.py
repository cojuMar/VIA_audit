from __future__ import annotations

import asyncio
import io
import json
import uuid
from datetime import datetime, timezone
from functools import partial
from urllib.parse import urlparse

import minio
import structlog

logger = structlog.get_logger(__name__)


class WORMStorageClient:
    """
    MinIO/S3 WORM storage client.  All MinIO SDK calls are synchronous and are
    dispatched via run_in_executor so they don't block the event loop.
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        use_ssl: bool = False,
    ) -> None:
        self._client = minio.Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=use_ssl,
        )
        self._bucket = bucket
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            self._loop = asyncio.get_event_loop()
        return self._loop

    async def _run(self, func, *args, **kwargs):
        loop = self._get_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    @staticmethod
    def _parse_uri(uri: str) -> tuple[str, str]:
        """Return (bucket, object_key) from a URI like s3://bucket/key or /bucket/key."""
        parsed = urlparse(uri)
        if parsed.scheme in ("s3", "minio"):
            bucket = parsed.netloc
            key = parsed.path.lstrip("/")
        else:
            # Treat as bare "bucket/key/..." string
            parts = uri.lstrip("/").split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""
        return bucket, key

    @staticmethod
    def _make_uri(bucket: str, key: str) -> str:
        return f"s3://{bucket}/{key}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def write_evidence_batch(
        self, tenant_id: str, records: list[dict]
    ) -> str:
        """
        Serializes records as newline-delimited JSON (NDJSON) and uploads to the
        evidence WORM bucket.

        Object key: evidence/{tenant_id}/{year}/{month}/{day}/{uuid4}.ndjson
        Returns the object URI.
        """
        now = datetime.now(tz=timezone.utc)
        key = (
            f"evidence/{tenant_id}/"
            f"{now.year:04d}/{now.month:02d}/{now.day:02d}/"
            f"{uuid.uuid4()}.ndjson"
        )

        ndjson_lines = "\n".join(json.dumps(r, default=str) for r in records)
        data = ndjson_lines.encode("utf-8")
        stream = io.BytesIO(data)

        await self._run(
            self._client.put_object,
            self._bucket,
            key,
            stream,
            length=len(data),
            content_type="application/x-ndjson",
        )

        uri = self._make_uri(self._bucket, key)
        logger.info(
            "worm_batch_written",
            tenant_id=tenant_id,
            record_count=len(records),
            uri=uri,
            bytes=len(data),
        )
        return uri

    async def write_single_record(
        self, tenant_id: str, evidence_id: str, record: dict
    ) -> str:
        """
        Writes a single evidence record as JSON.

        Object key: evidence/{tenant_id}/{evidence_id}.json
        Returns the object URI.
        """
        key = f"evidence/{tenant_id}/{evidence_id}.json"
        data = json.dumps(record, default=str).encode("utf-8")
        stream = io.BytesIO(data)

        await self._run(
            self._client.put_object,
            self._bucket,
            key,
            stream,
            length=len(data),
            content_type="application/json",
        )

        uri = self._make_uri(self._bucket, key)
        logger.info(
            "worm_single_record_written",
            tenant_id=tenant_id,
            evidence_id=evidence_id,
            uri=uri,
        )
        return uri

    async def write_zk_proof(
        self, tenant_id: str, proof_id: str, proof_bytes: bytes
    ) -> str:
        """
        Writes a ZK proof blob to the aegis-zk-proofs bucket.

        Object key: proofs/{tenant_id}/{proof_id}.bin
        Returns the object URI.
        """
        zk_bucket = "aegis-zk-proofs"
        key = f"proofs/{tenant_id}/{proof_id}.bin"
        stream = io.BytesIO(proof_bytes)

        await self._run(
            self._client.put_object,
            zk_bucket,
            key,
            stream,
            length=len(proof_bytes),
            content_type="application/octet-stream",
        )

        uri = self._make_uri(zk_bucket, key)
        logger.info(
            "zk_proof_written",
            tenant_id=tenant_id,
            proof_id=proof_id,
            uri=uri,
        )
        return uri

    async def get_object_hash(self, uri: str) -> bytes:
        """
        Returns the ETag of the stored object as bytes.
        MinIO uses MD5 by default; SHA-256 is stored in custom metadata
        (x-amz-meta-sha256) when available.

        Falls back to the raw ETag value encoded to UTF-8 bytes.
        """
        bucket, key = self._parse_uri(uri)
        stat: minio.datatypes.Object = await self._run(
            self._client.stat_object, bucket, key
        )
        # Prefer SHA-256 from custom metadata if present
        if stat.metadata:
            sha256_value = stat.metadata.get(
                "x-amz-meta-sha256"
            ) or stat.metadata.get("X-Amz-Meta-Sha256")
            if sha256_value:
                return bytes.fromhex(sha256_value)
        # Fall back to ETag (typically MD5)
        etag = (stat.etag or "").strip('"')
        return etag.encode("utf-8")

    async def verify_object_exists(self, uri: str) -> bool:
        """Returns True if the object at the given URI exists in storage."""
        bucket, key = self._parse_uri(uri)
        try:
            await self._run(self._client.stat_object, bucket, key)
            return True
        except minio.error.S3Error as exc:
            if exc.code == "NoSuchKey":
                return False
            raise
