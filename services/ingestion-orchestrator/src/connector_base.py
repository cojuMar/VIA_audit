import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator

from .canonical_schema import CanonicalEvidenceRecord


@dataclass
class ConnectorCredentials:
    """
    Loaded at runtime from HashiCorp Vault.
    Never stored in the connector config.
    """

    api_key: str | None = None
    oauth_access_token: str | None = None
    oauth_refresh_token: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    extra: dict = field(default_factory=dict)  # connector-specific fields


@dataclass
class FetchResult:
    records: list[CanonicalEvidenceRecord]
    next_cursor: dict | None  # persisted to ingestion_watermarks
    records_fetched: int
    bytes_ingested: int
    watermark_to: datetime


class ConnectorBase(abc.ABC):
    """
    Base class for all 400+ integrations.

    Each connector implementation must:
    1. Implement fetch_incremental() — the hot path called every hour
    2. Implement fetch_full() — for initial backfill or recovery
    3. Implement test_connection() — called during connector registration
    4. Implement normalize_to_canonical() — maps raw API response to canonical schema

    Connectors MUST NOT:
    - Store credentials locally (always fetch from Vault via the credentials param)
    - Log raw API responses (may contain PII)
    - Raise unhandled exceptions (catch and return FetchResult with error context)
    """

    connector_type: str  # class-level constant, e.g. 'aws_cloudtrail'
    version: str = "1.0.0"

    def __init__(
        self,
        tenant_id: str,
        connector_config: dict,
        credentials: ConnectorCredentials,
    ):
        self.tenant_id = tenant_id
        self.config = connector_config
        self.credentials = credentials

    @abc.abstractmethod
    async def fetch_incremental(
        self,
        from_cursor: dict | None,
        to_time: datetime,
    ) -> FetchResult:
        """Fetch only new records since last_cursor."""
        ...

    @abc.abstractmethod
    async def fetch_full(
        self, from_time: datetime, to_time: datetime
    ) -> AsyncIterator[FetchResult]:
        """Full backfill, yielding batches."""
        ...

    @abc.abstractmethod
    def normalize_to_canonical(
        self,
        raw_record: dict,
        collected_at: datetime,
    ) -> CanonicalEvidenceRecord:
        """Map a single raw API record to the canonical schema."""
        ...

    @abc.abstractmethod
    async def test_connection(self) -> bool:
        """Verify credentials and connectivity. Called at connector registration."""
        ...

    def validate_canonical(self, record: CanonicalEvidenceRecord) -> list[str]:
        """Returns list of validation errors. Empty list = valid."""
        errors = []
        required_payload_fields = [
            "event_type",
            "entity_id",
            "entity_type",
            "timestamp_utc",
            "outcome",
        ]
        for f in required_payload_fields:
            if f not in record.canonical_payload:
                errors.append(f"canonical_payload missing required field: {f}")
        if not record.tenant_id:
            errors.append("tenant_id is required")
        if not record.source_system:
            errors.append("source_system is required")
        return errors
