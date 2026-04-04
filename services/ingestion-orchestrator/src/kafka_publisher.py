"""
Kafka publisher for ingested evidence records.

Publishes canonical evidence records to the aegis.evidence.ingested topic
and ZK proof job requests to aegis.zk.proof.requested.

Producer configuration:
  - acks='all': waits for all in-sync replicas before acknowledging
  - enable_idempotence=True: exactly-once producer semantics
  - compression_type='gzip': reduces network and storage overhead
  - linger_ms=5: small batching window for throughput without adding latency

Key = tenant_id so all records for a tenant land in the same partition set,
preserving per-tenant ordering and enabling efficient consumer fan-out.
"""

import json
import logging

import structlog
from aiokafka import AIOKafkaProducer

from .canonical_schema import CanonicalEvidenceRecord
from .config import settings

logger = structlog.get_logger()

TOPIC_EVIDENCE_INGESTED = "aegis.evidence.ingested"
TOPIC_ZK_PROOF_REQUESTED = "aegis.zk.proof.requested"


class KafkaPublisher:
    """
    Async Kafka producer wrapper.

    Lifecycle:
      - Call await start() once during application startup.
      - Call await stop() during graceful shutdown.
      - Use publish_evidence() and publish_zk_request() during normal operation.
    """

    def __init__(self):
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        """Initialise and start the underlying AIOKafkaProducer."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: (
                v if isinstance(v, bytes) else json.dumps(v).encode()
            ),
            key_serializer=lambda k: (
                k.encode() if isinstance(k, str) else k
            ),
            compression_type="gzip",
            acks="all",  # Wait for all in-sync replicas
            max_batch_size=16384,
            linger_ms=5,  # Small batching window
            enable_idempotence=True,  # Exactly-once producer semantics
        )
        await self._producer.start()
        logger.info("kafka_publisher: producer started", servers=settings.kafka_bootstrap_servers)

    async def stop(self) -> None:
        """Flush pending messages and close the producer connection."""
        if self._producer:
            await self._producer.stop()
            logger.info("kafka_publisher: producer stopped")

    async def publish_evidence(self, record: CanonicalEvidenceRecord) -> None:
        """
        Publish a canonical evidence record to the evidence ingested topic.

        Key is tenant_id (str) so all records for a tenant go to the same
        partition set, preserving intra-tenant ordering.
        """
        if not self._producer:
            raise RuntimeError(
                "KafkaPublisher not started — call await start() first"
            )
        await self._producer.send_and_wait(
            TOPIC_EVIDENCE_INGESTED,
            value=record.to_kafka_message(),
            key=str(record.tenant_id),
        )

    async def publish_zk_request(
        self,
        tenant_id: str,
        circuit_type: str,
        evidence_ids: list[str],
        public_inputs: dict,
    ) -> None:
        """
        Publish a ZK proof generation job request.

        Parameters
        ----------
        tenant_id:
            UUID string of the tenant requesting the proof.
        circuit_type:
            Identifies which ZK circuit to invoke (e.g. 'benford_sum').
        evidence_ids:
            List of evidence_record UUIDs that the circuit will consume.
        public_inputs:
            Public inputs passed to the circuit (no private data).
        """
        if not self._producer:
            raise RuntimeError(
                "KafkaPublisher not started — call await start() first"
            )
        msg = {
            "tenant_id": tenant_id,
            "circuit_type": circuit_type,
            "evidence_record_ids": evidence_ids,
            "public_inputs": public_inputs,
        }
        await self._producer.send_and_wait(
            TOPIC_ZK_PROOF_REQUESTED,
            value=json.dumps(msg).encode(),
            key=tenant_id,
        )
