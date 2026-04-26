"""
Plaid Transactions connector.

Uses the plaid-python SDK with the /transactions/sync endpoint for
cursor-based incremental polling.  The connector handles added, modified,
and removed transaction events, normalizing each to the canonical schema.

IMPORTANT: Transaction amounts are placed in canonical_payload.metadata only.
They are private inputs for ZK proofs and must NOT appear in the top-level
canonical_payload or be logged.
"""

import json
import logging
from datetime import datetime, timezone
from typing import AsyncIterator
from uuid import UUID

import plaid
from plaid.api import plaid_api
from plaid.model.transactions_sync_request import TransactionsSyncRequest

from ..canonical_schema import CanonicalEvidenceRecord
from ..connector_base import ConnectorBase, FetchResult

logger = logging.getLogger(__name__)


class PlaidTransactionsConnector(ConnectorBase):
    """
    Polls Plaid /transactions/sync for added/modified/removed transactions.

    Config fields:
      - environment (str, default 'production'): 'sandbox', 'development', or 'production'
      - account_ids (list[str], optional): filter to specific account IDs

    Credentials (from Vault):
      - client_id: Plaid client ID
      - client_secret: Plaid secret
      - oauth_access_token: Plaid access token for the linked item
    """

    connector_type = "plaid_transactions"
    version = "1.0.0"

    _ENV_MAP = {
        "sandbox": plaid.Environment.Sandbox,
        "development": plaid.Environment.Development,
        "production": plaid.Environment.Production,
    }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_client(self) -> plaid_api.PlaidApi:
        env_str = self.config.get("environment", "production").lower()
        host = self._ENV_MAP.get(env_str, plaid.Environment.Production)
        configuration = plaid.Configuration(
            host=host,
            api_key={
                "clientId": self.credentials.client_id or "",
                "secret": self.credentials.client_secret or "",
            },
        )
        api_client = plaid.ApiClient(configuration)
        return plaid_api.PlaidApi(api_client)

    def _normalize_transaction(
        self,
        txn: dict,
        event_type: str,
        collected_at: datetime,
    ) -> CanonicalEvidenceRecord:
        canonical_payload = {
            "event_type": event_type,
            "entity_id": txn.get("transaction_id", ""),
            "entity_type": "financial_transaction",
            "actor_id": None,
            "timestamp_utc": txn.get("date", "") + "T00:00:00Z",
            "outcome": "success",
            "resource": txn.get("account_id", ""),
            "metadata": {
                # Amount is private input for ZK proofs — metadata only, never top-level
                "amount": txn.get("amount"),
                "currency": txn.get("iso_currency_code"),
                "merchant_name": txn.get("merchant_name"),
                "category": txn.get("category", []),
                "pending": txn.get("pending", False),
            },
        }
        return CanonicalEvidenceRecord(
            tenant_id=UUID(str(self.tenant_id)),
            source_system=self.connector_type,
            collected_at_utc=collected_at,
            raw_payload_hash="",  # caller fills in
            canonical_payload=canonical_payload,
        )

    # ------------------------------------------------------------------
    # ConnectorBase implementation
    # ------------------------------------------------------------------

    async def fetch_incremental(
        self,
        from_cursor: dict | None,
        to_time: datetime,
    ) -> FetchResult:
        """
        Uses /transactions/sync (cursor-based).  Loops until has_more=False.
        Processes added, modified, and removed transaction lists.
        """
        access_token = self.credentials.oauth_access_token or ""
        cursor: str = (from_cursor or {}).get("cursor", "")

        collected_at = datetime.now(timezone.utc)
        records: list[CanonicalEvidenceRecord] = []
        bytes_ingested = 0
        next_cursor = cursor

        try:
            client = self._build_client()
        except Exception as exc:
            logger.warning("plaid: failed to build client: %s", exc)
            return FetchResult(
                records=[],
                next_cursor=from_cursor,
                records_fetched=0,
                bytes_ingested=0,
                watermark_to=to_time,
            )

        account_ids = self.config.get("account_ids") or None

        try:
            has_more = True
            while has_more:
                request_kwargs: dict = {
                    "access_token": access_token,
                    "cursor": next_cursor,
                    "count": 500,
                }
                if account_ids:
                    request_kwargs["options"] = {"account_ids": account_ids}

                request = TransactionsSyncRequest(**request_kwargs)
                response = client.transactions_sync(request)

                # added transactions
                for txn in response.added:
                    txn_dict = txn.to_dict() if hasattr(txn, "to_dict") else dict(txn)
                    raw_bytes = json.dumps(txn_dict, default=str).encode("utf-8")
                    bytes_ingested += len(raw_bytes)
                    record = self._normalize_transaction(
                        txn_dict, "transaction.created", collected_at
                    )
                    record.raw_payload_hash = record.compute_raw_hash(raw_bytes)
                    errors = self.validate_canonical(record)
                    if not errors:
                        records.append(record)
                    else:
                        logger.warning("plaid: validation errors: %s", errors)

                # modified transactions
                for txn in response.modified:
                    txn_dict = txn.to_dict() if hasattr(txn, "to_dict") else dict(txn)
                    raw_bytes = json.dumps(txn_dict, default=str).encode("utf-8")
                    bytes_ingested += len(raw_bytes)
                    record = self._normalize_transaction(
                        txn_dict, "transaction.modified", collected_at
                    )
                    record.raw_payload_hash = record.compute_raw_hash(raw_bytes)
                    errors = self.validate_canonical(record)
                    if not errors:
                        records.append(record)
                    else:
                        logger.warning("plaid: validation errors: %s", errors)

                # removed transactions (tombstone records)
                for removed_txn in response.removed:
                    removed_dict = (
                        removed_txn.to_dict()
                        if hasattr(removed_txn, "to_dict")
                        else dict(removed_txn)
                    )
                    raw_bytes = json.dumps(removed_dict, default=str).encode("utf-8")
                    bytes_ingested += len(raw_bytes)
                    txn_id = removed_dict.get("transaction_id", "")
                    canonical_payload = {
                        "event_type": "transaction.removed",
                        "entity_id": txn_id,
                        "entity_type": "financial_transaction",
                        "actor_id": None,
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "outcome": "success",
                        "resource": removed_dict.get("account_id", ""),
                        "metadata": {},
                    }
                    record = CanonicalEvidenceRecord(
                        tenant_id=UUID(str(self.tenant_id)),
                        source_system=self.connector_type,
                        collected_at_utc=collected_at,
                        raw_payload_hash=CanonicalEvidenceRecord(
                            tenant_id=UUID(str(self.tenant_id)),
                            source_system=self.connector_type,
                            collected_at_utc=collected_at,
                            raw_payload_hash="",
                            canonical_payload=canonical_payload,
                        ).compute_raw_hash(raw_bytes),
                        canonical_payload=canonical_payload,
                    )
                    records.append(record)

                next_cursor = response.next_cursor
                has_more = response.has_more

        except Exception as exc:
            logger.warning("plaid: unexpected error during fetch: %s", exc)

        return FetchResult(
            records=records,
            next_cursor={"cursor": next_cursor},
            records_fetched=len(records),
            bytes_ingested=bytes_ingested,
            watermark_to=to_time,
        )

    async def fetch_full(
        self, from_time: datetime, to_time: datetime
    ) -> AsyncIterator[FetchResult]:
        """
        Plaid sync is inherently cursor-based; a full fetch starts from cursor=''.
        Yields a single FetchResult with all available history.
        """
        result = await self.fetch_incremental(from_cursor=None, to_time=to_time)
        yield result

    def normalize_to_canonical(
        self,
        raw_record: dict,
        collected_at: datetime,
    ) -> CanonicalEvidenceRecord:
        """Delegates to _normalize_transaction with 'transaction.created'."""
        return self._normalize_transaction(raw_record, "transaction.created", collected_at)

    async def test_connection(self) -> bool:
        """
        Calls transactions_sync with cursor='' and count=1 to verify connectivity.
        """
        access_token = self.credentials.oauth_access_token or ""
        try:
            client = self._build_client()
            request = TransactionsSyncRequest(
                access_token=access_token,
                cursor="",
                count=1,
            )
            client.transactions_sync(request)
            return True
        except Exception as exc:
            logger.warning("plaid: test_connection failed: %s", exc)
            return False
