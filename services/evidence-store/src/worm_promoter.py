from __future__ import annotations

import asyncio
import time

import asyncpg
import structlog

from .config import settings
from .db import (
    get_all_tenant_ids_with_pending_worm,
    get_pending_worm_records,
    update_worm_status,
)
from .models import WORMPromotionResult
from .worm_client import WORMStorageClient

logger = structlog.get_logger(__name__)


class WORMPromoter:
    """
    Background task that promotes un-promoted evidence records to WORM
    (Write Once Read Many) storage on a configurable periodic schedule.
    """

    def __init__(self, pool: asyncpg.Pool, worm_client: WORMStorageClient) -> None:
        self._pool = pool
        self._worm_client = worm_client

    # ------------------------------------------------------------------
    # Core promotion logic
    # ------------------------------------------------------------------

    async def promote_batch(self) -> WORMPromotionResult:
        """
        1. Discover all tenants that have un-promoted records.
        2. For each tenant, fetch up to worm_promotion_batch_size records.
        3. Write them as an NDJSON batch to MinIO.
        4. Mark each record as promoted in the DB.

        Returns a WORMPromotionResult summarising the run.
        """
        start_ms = int(time.monotonic() * 1000)
        total_records = 0
        total_bytes = 0

        tenant_ids = await get_all_tenant_ids_with_pending_worm(self._pool)
        if not tenant_ids:
            logger.info("worm_promoter_no_pending_records")
            return WORMPromotionResult(
                records_promoted=0,
                bytes_written=0,
                duration_ms=int(time.monotonic() * 1000) - start_ms,
            )

        logger.info("worm_promoter_tenants_found", count=len(tenant_ids))

        for tenant_id in tenant_ids:
            try:
                promoted, bytes_written = await self._promote_tenant(tenant_id)
                total_records += promoted
                total_bytes += bytes_written
            except Exception as exc:
                logger.error(
                    "worm_promotion_tenant_failed",
                    tenant_id=tenant_id,
                    error=str(exc),
                    exc_info=True,
                )
                # Continue with other tenants rather than aborting the whole run

        duration_ms = int(time.monotonic() * 1000) - start_ms
        result = WORMPromotionResult(
            records_promoted=total_records,
            bytes_written=total_bytes,
            duration_ms=duration_ms,
        )
        logger.info(
            "worm_promotion_batch_complete",
            records_promoted=total_records,
            bytes_written=total_bytes,
            duration_ms=duration_ms,
        )
        return result

    async def _promote_tenant(self, tenant_id: str) -> tuple[int, int]:
        """
        Promotes one batch of records for a single tenant.
        Returns (records_promoted, bytes_written).
        """
        records = await get_pending_worm_records(
            self._pool,
            tenant_id,
            batch_size=settings.worm_promotion_batch_size,
        )
        if not records:
            return 0, 0

        log = logger.bind(tenant_id=tenant_id, record_count=len(records))
        log.info("worm_promoting_tenant_batch")

        # Serialize to NDJSON to estimate size before the upload
        import json

        ndjson = "\n".join(json.dumps(r, default=str) for r in records)
        bytes_written = len(ndjson.encode("utf-8"))

        # Write the batch to WORM storage
        worm_uri = await self._worm_client.write_evidence_batch(tenant_id, records)

        # Mark each individual record as promoted in the DB
        for record in records:
            evidence_id = str(record["evidence_id"])
            await update_worm_status(
                self._pool,
                evidence_id=evidence_id,
                tenant_id=tenant_id,
                worm_uri=worm_uri,
            )

        log.info(
            "worm_tenant_batch_promoted",
            worm_uri=worm_uri,
            bytes_written=bytes_written,
        )
        return len(records), bytes_written

    # ------------------------------------------------------------------
    # Periodic runner
    # ------------------------------------------------------------------

    async def run_periodic(self) -> None:
        """
        Runs promote_batch() on a fixed interval defined by
        settings.worm_promotion_interval_seconds.  Sleeps first so that the
        service has time to warm up before the initial promotion attempt.
        """
        logger.info(
            "worm_promoter_periodic_started",
            interval_seconds=settings.worm_promotion_interval_seconds,
        )
        while True:
            await asyncio.sleep(settings.worm_promotion_interval_seconds)
            try:
                await self.promote_batch()
            except Exception as exc:
                logger.error(
                    "worm_promoter_periodic_error",
                    error=str(exc),
                    exc_info=True,
                )
