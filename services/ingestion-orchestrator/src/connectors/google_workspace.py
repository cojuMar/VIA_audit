"""
Google Workspace Admin SDK connector.

Fetches audit activity events from the Admin Reports API using a service account
with domain-wide delegation.  Supports all applicationName values (login, admin,
drive, calendar, etc.) via the `application_name` connector config field.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator
from uuid import UUID

from googleapiclient.discovery import build
from google.oauth2 import service_account

from ..canonical_schema import CanonicalEvidenceRecord
from ..connector_base import ConnectorBase, FetchResult

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/admin.reports.audit.readonly"]
_MAX_RESULTS = 1000


class GoogleWorkspaceAdminConnector(ConnectorBase):
    """
    Polls the Google Workspace Admin Reports API for audit activity logs.

    Config fields:
      - customer_id (str, default 'my_customer'): Google Workspace customer ID
      - application_name (str): e.g. 'login', 'admin', 'drive', 'calendar'

    Credentials (from Vault):
      - extra['service_account_json']: JSON string of service account key file
      - extra['delegated_admin_email']: email of the admin to impersonate
    """

    connector_type = "google_workspace_admin"
    version = "1.0.0"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_service(self):
        extra = self.credentials.extra or {}
        sa_json_str = extra.get("service_account_json", "{}")
        sa_info = json.loads(sa_json_str)
        delegated_email = extra.get("delegated_admin_email", "")

        creds = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=_SCOPES,
        )
        creds = creds.with_subject(delegated_email)
        return build("admin", "reports_v1", credentials=creds, cache_discovery=False)

    @staticmethod
    def _dt_to_rfc3339(dt: datetime) -> str:
        """Format datetime as RFC 3339 for Admin SDK startTime/endTime."""
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ------------------------------------------------------------------
    # ConnectorBase implementation
    # ------------------------------------------------------------------

    async def fetch_incremental(
        self,
        from_cursor: dict | None,
        to_time: datetime,
    ) -> FetchResult:
        customer_id = self.config.get("customer_id", "my_customer")
        app_name = self.config.get("application_name", "login")

        if from_cursor and "last_event_time" in from_cursor:
            from_time = datetime.fromisoformat(from_cursor["last_event_time"])
        else:
            from_time = to_time - timedelta(hours=1)

        collected_at = datetime.now(timezone.utc)
        records: list[CanonicalEvidenceRecord] = []
        bytes_ingested = 0

        try:
            service = self._build_service()
        except Exception as exc:
            logger.warning(
                "google_workspace: failed to build service: %s", exc
            )
            return FetchResult(
                records=[],
                next_cursor=from_cursor,
                records_fetched=0,
                bytes_ingested=0,
                watermark_to=to_time,
            )

        page_token: str | None = None
        try:
            while True:
                request = service.activities().list(
                    userKey="all",
                    applicationName=app_name,
                    customerId=customer_id,
                    startTime=self._dt_to_rfc3339(from_time),
                    endTime=self._dt_to_rfc3339(to_time),
                    maxResults=_MAX_RESULTS,
                    pageToken=page_token,
                )
                response = request.execute()
                activities = response.get("items", [])

                for activity in activities:
                    raw_bytes = json.dumps(activity, default=str).encode("utf-8")
                    bytes_ingested += len(raw_bytes)
                    record = self.normalize_to_canonical(activity, collected_at)
                    record.raw_payload_hash = record.compute_raw_hash(raw_bytes)
                    errors = self.validate_canonical(record)
                    if errors:
                        logger.warning(
                            "google_workspace: canonical validation errors: %s", errors
                        )
                        continue
                    records.append(record)

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

        except Exception as exc:
            logger.warning(
                "google_workspace: unexpected error during fetch: %s", exc
            )

        new_cursor = {"last_event_time": to_time.isoformat()}
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
        """
        Yields monthly batches.
        Admin SDK max lookback is 180 days.
        """
        max_lookback = datetime.now(timezone.utc) - timedelta(days=180)
        effective_from = max(from_time, max_lookback)

        current = effective_from
        while current < to_time:
            month_end = min(
                datetime(
                    current.year + (current.month // 12),
                    (current.month % 12) + 1,
                    1,
                    tzinfo=timezone.utc,
                ),
                to_time,
            )
            result = await self.fetch_incremental(
                from_cursor={"last_event_time": current.isoformat()},
                to_time=month_end,
            )
            yield result
            current = month_end

    def normalize_to_canonical(
        self,
        raw_record: dict,
        collected_at: datetime,
    ) -> CanonicalEvidenceRecord:
        """
        Maps a single Admin SDK activity dict to the canonical schema.
        """
        activity_id = raw_record.get("id", {})
        events = raw_record.get("events", [])

        # Build a composite event type from kind + first event name
        kind = raw_record.get("kind", "admin#reports#activity")
        kind_suffix = kind.split("#")[-1].lower()
        first_event_name = events[0]["name"] if events else "unknown"
        event_type = f"gsuite.{kind_suffix}.{first_event_name}"

        entity_id = str(activity_id.get("uniqueQualifier", ""))
        actor_id = (raw_record.get("actor") or {}).get("email")
        timestamp_utc = activity_id.get("time", "")
        resource = activity_id.get("applicationName")

        canonical_payload = {
            "event_type": event_type,
            "entity_id": entity_id,
            "entity_type": "gsuite_activity",
            "actor_id": actor_id,
            "timestamp_utc": timestamp_utc,
            "outcome": "success",  # Admin SDK only surfaces completed events
            "resource": resource,
            "metadata": {
                "ip_address": raw_record.get("ipAddress"),
                "events": [e["name"] for e in events],
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
        Calls activities.list with maxResults=1 to verify auth and connectivity.
        """
        customer_id = self.config.get("customer_id", "my_customer")
        app_name = self.config.get("application_name", "login")
        try:
            service = self._build_service()
            service.activities().list(
                userKey="all",
                applicationName=app_name,
                customerId=customer_id,
                maxResults=1,
            ).execute()
            return True
        except Exception as exc:
            logger.warning(
                "google_workspace: test_connection failed: %s", exc
            )
            return False
