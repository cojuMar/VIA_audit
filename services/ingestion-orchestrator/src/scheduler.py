"""
APScheduler-based polling orchestrator with circuit breaker.

Responsibilities:
  - On startup: load all active connectors from DB and schedule hourly polls
  - Each poll: load credentials from Vault, call fetch_incremental, publish to Kafka
  - Circuit breaker: after N consecutive failures, open the circuit and skip polls
    until the reset timeout has elapsed
  - Dynamic add/remove: support adding/removing connectors at runtime without restart

Database tables used:
  - connectors: source of connector configuration
  - ingestion_runs: audit log of every poll attempt
  - ingestion_watermarks: stores the last cursor per connector
  - connector_circuit_breakers: tracks failure counts and circuit state

Kafka topics written:
  - aegis.evidence.ingested (via KafkaPublisher)
  - aegis.connectors.health  (circuit open / skip events)
"""

import asyncio
import json
import random
from datetime import datetime, timezone
from uuid import UUID

import asyncpg
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import settings
from .connectors.registry import get_connector_class
from .hasher import build_chain_link
from .kafka_publisher import KafkaPublisher
from .vault_credentials import ConnectorVaultLoader

logger = structlog.get_logger()

_CIRCUIT_OPEN = "open"
_CIRCUIT_CLOSED = "closed"
_TOPIC_HEALTH = "aegis.connectors.health"

# Zero bytes for the genesis record in a new chain
_GENESIS_PREV_HASH = b"\x00" * 32


class PollScheduler:
    """
    Manages the scheduled polling of all registered connectors.

    Parameters
    ----------
    pool:
        asyncpg connection pool (injected on start).
    kafka:
        Started KafkaPublisher instance.
    """

    def __init__(self, kafka: KafkaPublisher):
        self._kafka = kafka
        self._pool: asyncpg.Pool | None = None
        self._scheduler = AsyncIOScheduler()
        self._vault_loader = ConnectorVaultLoader()
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_polls)
        # job_id -> connector_id mapping for dynamic removal
        self._job_ids: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, pool: asyncpg.Pool) -> None:
        """
        Load active connectors from DB and start the APScheduler.
        Called once during FastAPI lifespan startup.
        """
        self._pool = pool
        self._scheduler.start()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT connector_id, tenant_id, connector_type, config,
                       polling_interval_seconds, vault_path
                FROM connectors
                WHERE is_active = TRUE
                """
            )

        for row in rows:
            self._schedule_connector(dict(row))

        logger.info("poll_scheduler: started", connector_count=len(rows))

    async def stop(self) -> None:
        """Graceful shutdown — waits for running jobs to complete."""
        self._scheduler.shutdown(wait=True)
        logger.info("poll_scheduler: stopped")

    # ------------------------------------------------------------------
    # Scheduling helpers
    # ------------------------------------------------------------------

    def _schedule_connector(self, connector_row: dict) -> None:
        """
        Add an interval job for a single connector.

        A small random jitter (0-300 s) is added to avoid thundering-herd
        when all 400+ connectors share the same base interval.
        """
        connector_id = str(connector_row["connector_id"])
        tenant_id = str(connector_row["tenant_id"])
        connector_type = connector_row["connector_type"]
        interval_seconds = connector_row.get(
            "polling_interval_seconds",
            settings.default_polling_interval_seconds,
        )
        jitter = random.randint(0, 300)

        job_id = f"poll_{connector_id}"
        self._scheduler.add_job(
            self._execute_poll,
            "interval",
            seconds=interval_seconds + jitter,
            args=[connector_id, tenant_id, connector_type, connector_row],
            id=job_id,
            replace_existing=True,
            max_instances=1,  # Never overlap polls for the same connector
        )
        self._job_ids[connector_id] = job_id

    def add_connector(self, connector_row: dict) -> None:
        """Dynamically schedule a newly registered connector without restart."""
        self._schedule_connector(connector_row)
        logger.info(
            "poll_scheduler: connector added",
            connector_id=connector_row.get("connector_id"),
        )

    def remove_connector(self, connector_id: str) -> None:
        """Remove a connector's scheduled job (soft-delete path)."""
        job_id = self._job_ids.pop(str(connector_id), None)
        if job_id and self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            logger.info("poll_scheduler: connector removed", connector_id=connector_id)

    # ------------------------------------------------------------------
    # Poll execution
    # ------------------------------------------------------------------

    async def _execute_poll(
        self,
        connector_id: str,
        tenant_id: str,
        connector_type: str,
        connector_row: dict,
    ) -> None:
        """
        Core poll execution path.  Protected by a semaphore to cap concurrency.
        """
        async with self._semaphore:
            await self._do_poll(connector_id, tenant_id, connector_type, connector_row)

    async def _do_poll(
        self,
        connector_id: str,
        tenant_id: str,
        connector_type: str,
        connector_row: dict,
    ) -> None:
        pool = self._pool
        assert pool is not None, "PollScheduler not started"

        to_time = datetime.now(timezone.utc)

        # ----------------------------------------------------------------
        # 1. Circuit breaker check
        # ----------------------------------------------------------------
        async with pool.acquire() as conn:
            cb_row = await conn.fetchrow(
                """
                SELECT state, failure_count, opened_at
                FROM connector_circuit_breakers
                WHERE connector_id = $1
                """,
                UUID(connector_id),
            )

        if cb_row and cb_row["state"] == _CIRCUIT_OPEN:
            opened_at: datetime = cb_row["opened_at"]
            elapsed = (to_time - opened_at).total_seconds()
            if elapsed < settings.circuit_breaker_reset_timeout_seconds:
                logger.warning(
                    "poll_scheduler: circuit open, skipping poll",
                    connector_id=connector_id,
                    elapsed_seconds=int(elapsed),
                )
                await self._publish_health_event(
                    connector_id=connector_id,
                    tenant_id=tenant_id,
                    event="circuit_open_skip",
                )
                return
            else:
                # Reset to half-open; will close on next success
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE connector_circuit_breakers
                        SET state = 'half_open'
                        WHERE connector_id = $1
                        """,
                        UUID(connector_id),
                    )

        # ----------------------------------------------------------------
        # 2. Create ingestion_runs row
        # ----------------------------------------------------------------
        async with pool.acquire() as conn:
            run_id: UUID = await conn.fetchval(
                """
                INSERT INTO ingestion_runs
                  (connector_id, tenant_id, status, started_at)
                VALUES ($1, $2, 'running', now())
                RETURNING run_id
                """,
                UUID(connector_id),
                UUID(tenant_id),
            )

        run_status = "failed"
        records_published = 0
        bytes_ingested = 0
        error_message: str | None = None

        try:
            # ----------------------------------------------------------------
            # 3. Load credentials from Vault
            # ----------------------------------------------------------------
            vault_path = connector_row.get("vault_path") or (
                f"aegis/connectors/{tenant_id}/{connector_id}"
            )
            credentials = await self._vault_loader.load_credentials(vault_path)

            # ----------------------------------------------------------------
            # 4. Instantiate connector
            # ----------------------------------------------------------------
            connector_config = connector_row.get("config") or {}
            if isinstance(connector_config, str):
                connector_config = json.loads(connector_config)

            connector_cls = get_connector_class(connector_type)
            connector = connector_cls(
                tenant_id=tenant_id,
                connector_config=connector_config,
                credentials=credentials,
            )

            # ----------------------------------------------------------------
            # 5. Load last cursor from ingestion_watermarks
            # ----------------------------------------------------------------
            async with pool.acquire() as conn:
                wm_row = await conn.fetchrow(
                    """
                    SELECT cursor_data, last_chain_hash, last_chain_sequence
                    FROM ingestion_watermarks
                    WHERE connector_id = $1
                    """,
                    UUID(connector_id),
                )

            from_cursor: dict | None = None
            prev_chain_hash: bytes = _GENESIS_PREV_HASH
            chain_sequence: int = 0

            if wm_row:
                raw_cursor = wm_row["cursor_data"]
                if isinstance(raw_cursor, str):
                    from_cursor = json.loads(raw_cursor)
                elif isinstance(raw_cursor, dict):
                    from_cursor = raw_cursor

                if wm_row["last_chain_hash"]:
                    prev_chain_hash = bytes(wm_row["last_chain_hash"])
                if wm_row["last_chain_sequence"] is not None:
                    chain_sequence = wm_row["last_chain_sequence"] + 1

            # ----------------------------------------------------------------
            # 6. fetch_incremental
            # ----------------------------------------------------------------
            fetch_result = await connector.fetch_incremental(
                from_cursor=from_cursor,
                to_time=to_time,
            )
            bytes_ingested = fetch_result.bytes_ingested

            # ----------------------------------------------------------------
            # 7. For each record: compute chain link, publish to Kafka
            # ----------------------------------------------------------------
            for record in fetch_result.records:
                link = build_chain_link(
                    canonical_payload=record.canonical_payload,
                    prev_chain_hash=prev_chain_hash,
                    chain_sequence=chain_sequence,
                )
                record.chain_hash = link.chain_hash
                record.chain_sequence = link.chain_sequence

                await self._kafka.publish_evidence(record)

                prev_chain_hash = link.chain_hash
                chain_sequence += 1
                records_published += 1

            # ----------------------------------------------------------------
            # 8. Update ingestion_watermarks
            # ----------------------------------------------------------------
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO ingestion_watermarks
                      (connector_id, tenant_id, cursor_data, watermark_to,
                       last_chain_hash, last_chain_sequence, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, now())
                    ON CONFLICT (connector_id) DO UPDATE SET
                      cursor_data = EXCLUDED.cursor_data,
                      watermark_to = EXCLUDED.watermark_to,
                      last_chain_hash = EXCLUDED.last_chain_hash,
                      last_chain_sequence = EXCLUDED.last_chain_sequence,
                      updated_at = now()
                    """,
                    UUID(connector_id),
                    UUID(tenant_id),
                    json.dumps(fetch_result.next_cursor),
                    fetch_result.watermark_to,
                    prev_chain_hash,
                    chain_sequence - 1 if records_published > 0 else (wm_row["last_chain_sequence"] if wm_row else None),
                )

            run_status = "success"

            # ----------------------------------------------------------------
            # 10. On success: reset circuit breaker failure count
            # ----------------------------------------------------------------
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO connector_circuit_breakers
                      (connector_id, state, failure_count, opened_at)
                    VALUES ($1, 'closed', 0, NULL)
                    ON CONFLICT (connector_id) DO UPDATE SET
                      state = 'closed',
                      failure_count = 0,
                      opened_at = NULL
                    WHERE connector_circuit_breakers.failure_count > 0
                      OR connector_circuit_breakers.state <> 'closed'
                    """,
                    UUID(connector_id),
                )

            logger.info(
                "poll_scheduler: poll succeeded",
                connector_id=connector_id,
                records_published=records_published,
                bytes_ingested=bytes_ingested,
            )

        except Exception as exc:
            error_message = str(exc)
            logger.error(
                "poll_scheduler: poll failed",
                connector_id=connector_id,
                error=error_message,
            )

            # ----------------------------------------------------------------
            # 11. On failure: increment circuit breaker; open if >= threshold
            # ----------------------------------------------------------------
            async with pool.acquire() as conn:
                new_failure_count: int = await conn.fetchval(
                    """
                    INSERT INTO connector_circuit_breakers
                      (connector_id, state, failure_count, opened_at)
                    VALUES ($1, 'closed', 1, NULL)
                    ON CONFLICT (connector_id) DO UPDATE SET
                      failure_count = connector_circuit_breakers.failure_count + 1
                    RETURNING failure_count
                    """,
                    UUID(connector_id),
                )

                if new_failure_count >= settings.circuit_breaker_failure_threshold:
                    await conn.execute(
                        """
                        UPDATE connector_circuit_breakers
                        SET state = 'open', opened_at = now()
                        WHERE connector_id = $1
                        """,
                        UUID(connector_id),
                    )
                    logger.warning(
                        "poll_scheduler: circuit opened",
                        connector_id=connector_id,
                        failure_count=new_failure_count,
                    )
                    await self._publish_health_event(
                        connector_id=connector_id,
                        tenant_id=tenant_id,
                        event="circuit_opened",
                        error=error_message,
                    )

        finally:
            # ----------------------------------------------------------------
            # 9. Update ingestion_runs with final status
            # ----------------------------------------------------------------
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE ingestion_runs
                    SET status = $2,
                        finished_at = now(),
                        records_published = $3,
                        bytes_ingested = $4,
                        error_message = $5
                    WHERE run_id = $1
                    """,
                    run_id,
                    run_status,
                    records_published,
                    bytes_ingested,
                    error_message,
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _publish_health_event(
        self,
        connector_id: str,
        tenant_id: str,
        event: str,
        error: str | None = None,
    ) -> None:
        """Publish a health/circuit-breaker event to the health topic."""
        try:
            msg = {
                "connector_id": connector_id,
                "tenant_id": tenant_id,
                "event": event,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "error": error,
            }
            await self._kafka._producer.send_and_wait(  # type: ignore[union-attr]
                _TOPIC_HEALTH,
                value=json.dumps(msg).encode(),
                key=tenant_id,
            )
        except Exception as exc:
            logger.warning(
                "poll_scheduler: failed to publish health event: %s", exc
            )
