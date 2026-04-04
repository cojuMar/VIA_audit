from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class EvidenceRecordCreate(BaseModel):
    """Received from Kafka or HTTP POST. Pre-chain-hash state."""

    evidence_id: UUID
    tenant_id: UUID
    source_system: str
    collected_at_utc: datetime
    payload_hash: str  # hex SHA-256 of raw payload
    canonical_payload: dict[str, Any]
    collector_version: str = "1.0.0"


class EvidenceRecordResponse(BaseModel):
    evidence_id: UUID
    tenant_id: UUID
    source_system: str
    collected_at_utc: datetime
    chain_sequence: int
    chain_hash: str  # hex-encoded for API responses
    freshness_status: str
    zk_proof_id: UUID | None
    created_at: datetime
    # canonical_payload is intentionally excluded from the response
    # to minimize data surface area — request it separately if needed


class ChainVerificationResult(BaseModel):
    tenant_id: UUID
    records_checked: int
    chain_intact: bool
    first_broken_sequence: int | None
    checked_at: datetime


class WORMPromotionResult(BaseModel):
    records_promoted: int
    bytes_written: int
    duration_ms: int
