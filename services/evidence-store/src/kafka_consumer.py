from __future__ import annotations

import json

import asyncpg
import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from .config import settings
from .db import get_chain_state, insert_evidence_record
from .hasher import compute_chain_hash, compute_payload_hash
from .models import EvidenceRecordCreate
from .worm_client import WORMStorageClient

logger = structlog.get_logger(__name__)

INGESTED_TOPIC = "aegis.evidence.ingested"
NORMALIZED_TOPIC = "aegis.evidence.normalized"


class EvidenceKafkaConsumer:
    """
    Consumes canonical evidence records from ``aegis.evidence.ingested``,
    applies hash-chaining, persists to PostgreSQL, and re-publishes the
    enriched records to ``aegis.evidence.normalized``.
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        worm_client: WORMStorageClient,
        publisher: AIOKafkaProducer,
    ) -> None:
        self._pool = pool
        self._worm_client = worm_client
        self._publisher = publisher
        self._consumer: AIOKafkaConsumer | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Creates and starts the AIOKafkaConsumer."""
        self._consumer = AIOKafkaConsumer(
            INGESTED_TOPIC,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_consumer_group,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
        )
        await self._consumer.start()
        logger.info(
            "kafka_consumer_started",
            topic=INGESTED_TOPIC,
            group=settings.kafka_consumer_group,
        )

    async def stop(self) -> None:
        if self._consumer is not None:
            await self._consumer.stop()
            logger.info("kafka_consumer_stopped")

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def process_message(self, msg) -> bool:
        """
        Processes a single Kafka message:
        1. Deserializes the value into an EvidenceRecordCreate.
        2. Fetches the current chain state for the tenant.
        3. Computes payload_hash and chain_hash.
        4. Inserts into the DB (idempotent via ON CONFLICT DO NOTHING).
        5. Publishes the enriched record to aegis.evidence.normalized.

        Returns True on success, raises on unrecoverable error.
        """
        raw: dict = msg.value
        log = logger.bind(
            partition=msg.partition,
            offset=msg.offset,
            topic=msg.topic,
        )

        try:
            record = EvidenceRecordCreate(**raw)
        except Exception as exc:
            log.error("message_deserialization_failed", error=str(exc))
            # Deserialization failures are not retriable — treat as poison pill
            # and commit so we don't block the partition forever.
            return True  # caller will still commit

        tenant_id = str(record.tenant_id)
        log = log.bind(
            evidence_id=str(record.evidence_id),
            tenant_id=tenant_id,
        )

        # --- Chain state ------------------------------------------------
        chain_state = await get_chain_state(self._pool, tenant_id)

        # --- Hash computation -------------------------------------------
        # Re-derive payload_hash from canonical_payload to verify fidelity;
        # the incoming payload_hash field is used as a cross-check only.
        computed_payload_hash = compute_payload_hash(record.canonical_payload)
        if computed_payload_hash.hex() != record.payload_hash:
            log.warning(
                "payload_hash_mismatch",
                provided=record.payload_hash,
                computed=computed_payload_hash.hex(),
            )
            # Use the computed hash for chain integrity
        chain_hash = compute_chain_hash(chain_state.last_hash, computed_payload_hash)
        chain_sequence = chain_state.next_seq

        # --- DB insert --------------------------------------------------
        await insert_evidence_record(
            self._pool,
            record,
            chain_hash=chain_hash,
            chain_sequence=chain_sequence,
            tenant_id=tenant_id,
        )

        # --- Publish normalized event -----------------------------------
        normalized_payload = {
            **raw,
            "chain_sequence": chain_sequence,
            "chain_hash": chain_hash.hex(),
            "payload_hash": computed_payload_hash.hex(),
        }
        await self._publisher.send_and_wait(
            NORMALIZED_TOPIC,
            key=str(record.evidence_id).encode("utf-8"),
            value=json.dumps(normalized_payload, default=str).encode("utf-8"),
        )

        log.info(
            "evidence_processed",
            chain_sequence=chain_sequence,
            chain_hash=chain_hash.hex()[:16] + "...",
        )
        return True

    # ------------------------------------------------------------------
    # Consume loop
    # ------------------------------------------------------------------

    async def consume_loop(self) -> None:
        """
        Infinite loop.  Commits offsets only after a successful DB write.
        On failure the offset is NOT committed so Kafka redelivers the message.
        """
        if self._consumer is None:
            raise RuntimeError("Consumer not started — call start() first")

        logger.info("consume_loop_started")
        async for msg in self._consumer:
            try:
                await self.process_message(msg)
                await self._consumer.commit()
            except Exception as exc:
                logger.error(
                    "message_processing_failed",
                    topic=msg.topic,
                    partition=msg.partition,
                    offset=msg.offset,
                    error=str(exc),
                    exc_info=True,
                )
                # Do NOT commit — let Kafka redeliver the message
