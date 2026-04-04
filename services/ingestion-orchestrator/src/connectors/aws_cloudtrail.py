"""
AWS CloudTrail connector.

Fetches CloudTrail management and data events via the boto3 lookup_events API.
For high-volume deployments, S3-based delivery can be configured via the
`s3_bucket` config field (S3 delivery is handled separately; this connector
covers the lookup API path for up to 1 000 events per incremental poll).
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import boto3
import botocore.exceptions

from ..canonical_schema import CanonicalEvidenceRecord
from ..connector_base import ConnectorBase, ConnectorCredentials, FetchResult

logger = logging.getLogger(__name__)

_MAX_EVENTS_PER_POLL = 1_000
_BATCH_SIZE = 50  # CloudTrail MaxResults ceiling per call


class AWSCloudTrailConnector(ConnectorBase):
    """
    Polls AWS CloudTrail lookup_events for management/data events.

    Config fields:
      - region (str, required): AWS region, e.g. 'us-east-1'
      - trail_arn (str, optional): restrict to a specific trail
      - s3_bucket (str, optional): S3 bucket for high-volume delivery (future)

    Credentials (from Vault extra dict):
      - aws_access_key_id
      - aws_secret_access_key
    """

    connector_type = "aws_cloudtrail"
    version = "1.0.0"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_client(self):
        extra = self.credentials.extra or {}
        return boto3.client(
            "cloudtrail",
            region_name=self.config.get("region", "us-east-1"),
            aws_access_key_id=extra.get("aws_access_key_id"),
            aws_secret_access_key=extra.get("aws_secret_access_key"),
        )

    def _lookup_kwargs(self, start: datetime, end: datetime) -> dict:
        kwargs: dict = {
            "StartTime": start,
            "EndTime": end,
            "MaxResults": _BATCH_SIZE,
        }
        trail_arn = self.config.get("trail_arn")
        if trail_arn:
            kwargs["LookupAttributes"] = [
                {"AttributeKey": "EventSource", "AttributeValue": trail_arn}
            ]
        return kwargs

    # ------------------------------------------------------------------
    # ConnectorBase implementation
    # ------------------------------------------------------------------

    async def fetch_incremental(
        self,
        from_cursor: dict | None,
        to_time: datetime,
    ) -> FetchResult:
        """
        Fetches up to _MAX_EVENTS_PER_POLL CloudTrail events between the
        cursor watermark and to_time.  Handles NextToken pagination internally.
        """
        try:
            client = self._make_client()
        except Exception as exc:
            logger.warning("aws_cloudtrail: failed to create boto3 client: %s", exc)
            return FetchResult(
                records=[],
                next_cursor=from_cursor,
                records_fetched=0,
                bytes_ingested=0,
                watermark_to=to_time,
            )

        from_time: datetime
        if from_cursor and "last_event_time" in from_cursor:
            from_time = datetime.fromisoformat(from_cursor["last_event_time"])
        else:
            # Default: last hour
            from_time = to_time - timedelta(hours=1)

        collected_at = datetime.now(timezone.utc)
        records: list[CanonicalEvidenceRecord] = []
        bytes_ingested = 0
        next_token: str | None = None
        total_fetched = 0

        kwargs = self._lookup_kwargs(from_time, to_time)

        try:
            while total_fetched < _MAX_EVENTS_PER_POLL:
                if next_token:
                    kwargs["NextToken"] = next_token
                elif "NextToken" in kwargs:
                    del kwargs["NextToken"]

                try:
                    response = client.lookup_events(**kwargs)
                except botocore.exceptions.ClientError as exc:
                    logger.warning(
                        "aws_cloudtrail: lookup_events error: %s",
                        exc.response["Error"]["Code"],
                    )
                    break

                events = response.get("Events", [])
                for raw_event in events:
                    raw_bytes = json.dumps(raw_event, default=str).encode("utf-8")
                    bytes_ingested += len(raw_bytes)
                    record = self.normalize_to_canonical(raw_event, collected_at)
                    record.raw_payload_hash = record.compute_raw_hash(raw_bytes)
                    errors = self.validate_canonical(record)
                    if errors:
                        logger.warning(
                            "aws_cloudtrail: canonical validation errors for event %s: %s",
                            raw_event.get("EventId"),
                            errors,
                        )
                        continue
                    records.append(record)

                total_fetched += len(events)
                next_token = response.get("NextToken")
                if not next_token:
                    break

        except Exception as exc:
            logger.warning("aws_cloudtrail: unexpected error during fetch: %s", exc)

        new_cursor = {"last_event_time": to_time.isoformat()}
        if next_token:
            new_cursor["next_token"] = next_token

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
        Yields daily batches across the requested range.
        CloudTrail lookup_events has a 90-day maximum lookback.
        """
        ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
        effective_from = max(from_time, ninety_days_ago)

        current = effective_from
        while current < to_time:
            day_end = min(current + timedelta(days=1), to_time)
            result = await self.fetch_incremental(
                from_cursor={"last_event_time": current.isoformat()},
                to_time=day_end,
            )
            yield result
            current = day_end

    def normalize_to_canonical(
        self,
        raw_record: dict,
        collected_at: datetime,
    ) -> CanonicalEvidenceRecord:
        """
        Maps a single CloudTrail event dict to the canonical schema.
        """
        from uuid import UUID

        resources = raw_record.get("Resources", [])
        first_resource_arn: str | None = None
        if resources:
            first_resource_arn = resources[0].get("ResourceARN") or resources[0].get(
                "ResourceName"
            )

        actor_id = raw_record.get("Username") or (
            raw_record.get("UserIdentity") or {}
        ).get("arn")

        outcome = (
            "failure" if "ErrorCode" in raw_record else "success"
        )

        event_name = raw_record.get("EventName", "unknown")
        canonical_payload = {
            "event_type": "aws." + event_name.lower(),
            "entity_id": raw_record.get("EventId", ""),
            "entity_type": "aws_resource",
            "actor_id": actor_id,
            "timestamp_utc": (
                raw_record["EventTime"].isoformat()
                if isinstance(raw_record.get("EventTime"), datetime)
                else str(raw_record.get("EventTime", ""))
            ),
            "outcome": outcome,
            "resource": first_resource_arn,
            "metadata": {
                "event_source": raw_record.get("EventSource"),
                "aws_region": raw_record.get("AwsRegion"),
                "error_code": raw_record.get("ErrorCode"),
                "error_message": raw_record.get("ErrorMessage"),
            },
        }

        return CanonicalEvidenceRecord(
            tenant_id=UUID(str(self.tenant_id)),
            source_system=self.connector_type,
            collected_at_utc=collected_at,
            raw_payload_hash="",  # caller fills in after serialization
            canonical_payload=canonical_payload,
        )

    async def test_connection(self) -> bool:
        """
        Calls describe_trails to verify credentials and connectivity.
        Returns True on success, False on any error.
        """
        try:
            client = self._make_client()
            client.describe_trails()
            return True
        except botocore.exceptions.ClientError as exc:
            logger.warning(
                "aws_cloudtrail: test_connection failed: %s",
                exc.response["Error"]["Code"],
            )
            return False
        except Exception as exc:
            logger.warning("aws_cloudtrail: test_connection unexpected error: %s", exc)
            return False
