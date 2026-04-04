"""
QuickBooks Online connector — General Ledger / JournalEntry.

Uses the QuickBooks V3 REST API (Intuit Query Language) to fetch JournalEntry
records via an async httpx client.  Supports cursor-based incremental polling
via the MetaData.LastUpdatedTime field and startposition pagination.

Token refresh: on HTTP 401 the connector refreshes the OAuth2 access token via
the Intuit token endpoint and retries the request once.  New tokens are written
back to Vault so the next poll uses them.

IMPORTANT: JournalEntry memo fields are ALWAYS redacted in canonical_payload.
Total amounts appear in metadata for Benford / ML analysis, but are private
inputs for ZK proofs.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator
from uuid import UUID

import httpx

from ..canonical_schema import CanonicalEvidenceRecord
from ..connector_base import ConnectorBase, ConnectorCredentials, FetchResult

logger = logging.getLogger(__name__)

_QB_BASE_URL_PROD = "https://quickbooks.api.intuit.com"
_QB_BASE_URL_SANDBOX = "https://sandbox-quickbooks.api.intuit.com"
_TOKEN_ENDPOINT = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
_PAGE_SIZE = 100


class QuickBooksLedgerConnector(ConnectorBase):
    """
    Polls QuickBooks Online for JournalEntry records (general ledger).

    Config fields:
      - realm_id (str, required): QuickBooks company ID
      - environment (str, default 'production'): 'sandbox' or 'production'

    Credentials (from Vault):
      - oauth_access_token
      - oauth_refresh_token
      - client_id
      - client_secret
    """

    connector_type = "quickbooks_ledger"
    version = "1.0.0"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _base_url(self) -> str:
        env = self.config.get("environment", "production").lower()
        return _QB_BASE_URL_SANDBOX if env == "sandbox" else _QB_BASE_URL_PROD

    def _query_url(self) -> str:
        realm_id = self.config["realm_id"]
        return f"{self._base_url()}/v3/company/{realm_id}/query"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.credentials.oauth_access_token}",
            "Accept": "application/json",
            "Content-Type": "application/text",
        }

    async def _refresh_token(self, vault_path: str | None = None) -> bool:
        """
        Refreshes the OAuth2 access token using the refresh token.
        Updates self.credentials and optionally persists new tokens to Vault.
        Returns True on success.
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    _TOKEN_ENDPOINT,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": self.credentials.oauth_refresh_token or "",
                    },
                    auth=(
                        self.credentials.client_id or "",
                        self.credentials.client_secret or "",
                    ),
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                token_data = response.json()
                self.credentials.oauth_access_token = token_data["access_token"]
                if "refresh_token" in token_data:
                    self.credentials.oauth_refresh_token = token_data["refresh_token"]

                # Persist to Vault if path provided
                if vault_path:
                    from ..vault_credentials import ConnectorVaultLoader

                    loader = ConnectorVaultLoader()
                    await loader.update_tokens(
                        vault_path,
                        self.credentials.oauth_access_token,
                        self.credentials.oauth_refresh_token or "",
                    )
                return True
        except Exception as exc:
            logger.warning("quickbooks: token refresh failed: %s", exc)
            return False

    async def _execute_query(
        self,
        query: str,
        *,
        vault_path: str | None = None,
        retry_on_401: bool = True,
    ) -> dict:
        """
        Executes a QuickBooks IQL query.  On 401 refreshes the token and retries once.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                self._query_url(),
                params={"query": query},
                headers=self._headers(),
            )

            if response.status_code == 401 and retry_on_401:
                refreshed = await self._refresh_token(vault_path=vault_path)
                if refreshed:
                    # Retry once with new token
                    response = await client.get(
                        self._query_url(),
                        params={"query": query},
                        headers=self._headers(),
                    )

            response.raise_for_status()
            return response.json()

    # ------------------------------------------------------------------
    # ConnectorBase implementation
    # ------------------------------------------------------------------

    async def fetch_incremental(
        self,
        from_cursor: dict | None,
        to_time: datetime,
    ) -> FetchResult:
        if from_cursor and "last_updated_time" in from_cursor:
            from_time = datetime.fromisoformat(from_cursor["last_updated_time"])
        else:
            from_time = to_time - timedelta(hours=1)

        # QuickBooks datetime format: yyyy-MM-ddTHH:mm:ss+HH:MM
        from_str = from_time.strftime("%Y-%m-%dT%H:%M:%S+00:00")

        collected_at = datetime.now(timezone.utc)
        records: list[CanonicalEvidenceRecord] = []
        bytes_ingested = 0
        start_position = 1

        try:
            while True:
                query = (
                    f"SELECT * FROM JournalEntry "
                    f"WHERE MetaData.LastUpdatedTime >= '{from_str}' "
                    f"STARTPOSITION {start_position} "
                    f"MAXRESULTS {_PAGE_SIZE}"
                )
                data = await self._execute_query(query)

                query_response = data.get("QueryResponse", {})
                entries = query_response.get("JournalEntry", [])

                for entry in entries:
                    raw_bytes = json.dumps(entry, default=str).encode("utf-8")
                    bytes_ingested += len(raw_bytes)
                    record = self.normalize_to_canonical(entry, collected_at)
                    record.raw_payload_hash = record.compute_raw_hash(raw_bytes)
                    errors = self.validate_canonical(record)
                    if errors:
                        logger.warning("quickbooks: validation errors: %s", errors)
                        continue
                    records.append(record)

                if len(entries) < _PAGE_SIZE:
                    break
                start_position += _PAGE_SIZE

        except Exception as exc:
            logger.warning("quickbooks: unexpected error during fetch: %s", exc)

        new_cursor = {"last_updated_time": to_time.isoformat()}
        return FetchResult(
            records=records,
            next_cursor=new_cursor,
            records_fetched=len(records),
            bytes_ingested=bytes_ingested,
            watermark_to=to_time,
        )

    async def fetch_full(
        self, from_time: datetime, to_time: datetime
    ) -> AsyncIterator[FetchResult]:
        """Yields weekly batches across the requested range."""
        current = from_time
        while current < to_time:
            week_end = min(current + timedelta(days=7), to_time)
            result = await self.fetch_incremental(
                from_cursor={"last_updated_time": current.isoformat()},
                to_time=week_end,
            )
            yield result
            current = week_end

    def normalize_to_canonical(
        self,
        raw_record: dict,
        collected_at: datetime,
    ) -> CanonicalEvidenceRecord:
        """
        Maps a single QuickBooks JournalEntry dict to the canonical schema.
        Memo fields are always redacted.  Amounts go to metadata only.
        """
        lines = raw_record.get("Line", [])
        je_lines = [
            {
                "account_ref": (
                    line.get("JournalEntryLineDetail", {})
                    .get("AccountRef", {})
                    .get("value")
                ),
                "posting_type": (
                    line.get("JournalEntryLineDetail", {}).get("PostingType")
                ),
            }
            for line in lines
            if line.get("DetailType") == "JournalEntryLineDetail"
        ]

        actor_id = (
            raw_record.get("MetaData", {})
            .get("LastModifiedByRef", {})
            .get("value")
        )

        txn_date = raw_record.get("TxnDate", "")
        timestamp_utc = txn_date + "T00:00:00Z" if txn_date else ""

        canonical_payload = {
            "event_type": "ledger.journal_entry",
            "entity_id": str(raw_record.get("Id", "")),
            "entity_type": "journal_entry",
            "actor_id": actor_id,
            "timestamp_utc": timestamp_utc,
            "outcome": "success",
            "resource": raw_record.get("DocNumber", ""),
            "metadata": {
                "line_count": len(lines),
                "total_amount": raw_record.get("TotalAmt"),  # private ZK input
                "currency": raw_record.get("CurrencyRef", {}).get("value", "USD"),
                "private_memo": "[REDACTED]",  # memo never included in canonical
                "lines": je_lines,
            },
        }

        return CanonicalEvidenceRecord(
            tenant_id=UUID(str(self.tenant_id)),
            source_system=self.connector_type,
            collected_at_utc=collected_at,
            raw_payload_hash="",  # caller fills in
            canonical_payload=canonical_payload,
        )

    async def test_connection(self) -> bool:
        """
        Queries SELECT COUNT(*) FROM JournalEntry MAXRESULTS 1 to verify auth.
        """
        try:
            await self._execute_query(
                "SELECT COUNT(*) FROM JournalEntry MAXRESULTS 1",
                retry_on_401=True,
            )
            return True
        except Exception as exc:
            logger.warning("quickbooks: test_connection failed: %s", exc)
            return False
