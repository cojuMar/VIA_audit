import hashlib
import json
from datetime import datetime
from typing import Any, TypedDict
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CanonicalEvidenceRecord(BaseModel):
    """
    Canonical evidence record — the normalized form produced by every connector.
    All connector-specific data is mapped to this schema before storage.

    Fields mirror the evidence_records DB table columns.
    """

    evidence_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    source_system: str  # e.g. 'aws_cloudtrail', 'quickbooks'
    collected_at_utc: datetime
    raw_payload_hash: str  # hex-encoded SHA-256 of the original raw API response
    canonical_payload: dict[str, Any]
    collector_version: str = "1.0.0"
    # Set by evidence-store after chain hashing:
    chain_hash: bytes | None = None
    chain_sequence: int | None = None

    def compute_raw_hash(self, raw_payload: bytes | str) -> str:
        if isinstance(raw_payload, str):
            raw_payload = raw_payload.encode("utf-8")
        return hashlib.sha256(raw_payload).hexdigest()

    def to_kafka_message(self) -> bytes:
        """Serialize to JSON bytes for Kafka publishing."""
        d = self.model_dump(mode="json")
        return json.dumps(d, default=str).encode("utf-8")


class CanonicalPayloadFields(TypedDict):
    """
    Documents the required fields every canonical_payload dict MUST include.
    All connectors must populate these keys in their normalize_to_canonical output.
    """

    event_type: str
    """Normalized event category (e.g. 'access.login', 'transaction.created')."""

    entity_id: str
    """The primary entity (user ID, transaction ID, resource ARN, etc.)."""

    entity_type: str
    """Type of entity ('user', 'transaction', 'resource', 'policy')."""

    actor_id: str | None
    """Who performed the action (user, service account). None for system events."""

    timestamp_utc: str
    """ISO 8601 event timestamp from the source system."""

    outcome: str
    """'success', 'failure', or 'unknown'."""

    resource: str | None
    """Affected resource identifier."""

    metadata: dict
    """Connector-specific additional fields (safe to include non-PII only)."""
