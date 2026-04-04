from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from .config import settings
from .db import tenant_conn
from .models import IssueCreate, IssueResponseCreate


def _get_minio_client():
    from minio import Minio

    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=False,
    )


class IssueTracker:

    # ------------------------------------------------------------------
    # Create issue
    # ------------------------------------------------------------------

    async def create_issue(
        self, pool: asyncpg.Pool, tenant_id: str, data: IssueCreate
    ) -> dict:
        issue_id = str(uuid.uuid4())
        async with tenant_conn(pool, tenant_id) as conn:
            num_row = await conn.fetchrow(
                """
                SELECT COALESCE(MAX(issue_number), 0) + 1 AS next_num
                FROM audit_issues
                WHERE engagement_id = $1 AND tenant_id = $2
                """,
                data.engagement_id,
                tenant_id,
            )
            next_num = num_row["next_num"]
            row = await conn.fetchrow(
                """
                INSERT INTO audit_issues (
                    issue_id, tenant_id, engagement_id, issue_number,
                    title, description, finding_type, severity,
                    control_reference, framework_references, root_cause,
                    management_owner, target_remediation_date,
                    status, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb,
                        $11, $12, $13, 'open', NOW(), NOW())
                RETURNING *
                """,
                issue_id,
                tenant_id,
                data.engagement_id,
                next_num,
                data.title,
                data.description,
                data.finding_type,
                data.severity,
                data.control_reference,
                data.framework_references,
                data.root_cause,
                data.management_owner,
                data.target_remediation_date,
            )
        return dict(row)

    # ------------------------------------------------------------------
    # Add response (immutable)
    # ------------------------------------------------------------------

    async def add_response(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        data: IssueResponseCreate,
        file_bytes: bytes | None = None,
        file_name: str | None = None,
    ) -> dict:
        response_id = str(uuid.uuid4())
        file_key: str | None = None

        if file_bytes and file_name:
            try:
                import io

                client = _get_minio_client()
                object_key = f"issues/{tenant_id}/{data.issue_id}/{uuid.uuid4()}_{file_name}"
                client.put_object(
                    settings.minio_bucket_workpapers,
                    object_key,
                    io.BytesIO(file_bytes),
                    length=len(file_bytes),
                )
                file_key = object_key
            except Exception:
                file_key = None

        async with tenant_conn(pool, tenant_id) as conn:
            # INSERT response (immutable)
            resp_row = await conn.fetchrow(
                """
                INSERT INTO issue_responses (
                    response_id, tenant_id, issue_id, response_type,
                    response_text, submitted_by, new_status,
                    file_name, file_key, responded_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                RETURNING *
                """,
                response_id,
                tenant_id,
                data.issue_id,
                data.response_type,
                data.response_text,
                data.submitted_by,
                data.new_status,
                file_name,
                file_key,
            )

            # UPDATE issue status if requested
            if data.new_status:
                if data.new_status == "resolved":
                    issue_row = await conn.fetchrow(
                        """
                        UPDATE audit_issues
                        SET status = $3,
                            actual_remediation_date = CURRENT_DATE,
                            updated_at = NOW()
                        WHERE issue_id = $1 AND tenant_id = $2
                        RETURNING *
                        """,
                        data.issue_id,
                        tenant_id,
                        data.new_status,
                    )
                else:
                    issue_row = await conn.fetchrow(
                        """
                        UPDATE audit_issues
                        SET status = $3, updated_at = NOW()
                        WHERE issue_id = $1 AND tenant_id = $2
                        RETURNING *
                        """,
                        data.issue_id,
                        tenant_id,
                        data.new_status,
                    )
            else:
                issue_row = await conn.fetchrow(
                    "SELECT * FROM audit_issues WHERE issue_id = $1 AND tenant_id = $2",
                    data.issue_id,
                    tenant_id,
                )

        return {"response": dict(resp_row), "issue": dict(issue_row)}

    # ------------------------------------------------------------------
    # Get issue register
    # ------------------------------------------------------------------

    async def get_issue_register(
        self, pool: asyncpg.Pool, tenant_id: str, engagement_id: str
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            issue_rows = await conn.fetch(
                """
                SELECT * FROM audit_issues
                WHERE engagement_id = $1 AND tenant_id = $2
                ORDER BY issue_number ASC
                """,
                engagement_id,
                tenant_id,
            )

            # Latest response per issue
            resp_rows = await conn.fetch(
                """
                SELECT DISTINCT ON (issue_id)
                    issue_id, response_type, response_text, submitted_by,
                    new_status, responded_at
                FROM issue_responses
                WHERE tenant_id = $1
                  AND issue_id = ANY($2::uuid[])
                ORDER BY issue_id, responded_at DESC
                """,
                tenant_id,
                [str(r["issue_id"]) for r in issue_rows],
            )

        resp_map = {str(r["issue_id"]): dict(r) for r in resp_rows}
        result = []
        for issue in issue_rows:
            d = dict(issue)
            d["latest_response"] = resp_map.get(str(issue["issue_id"]))
            result.append(d)
        return result

    # ------------------------------------------------------------------
    # Get single issue with all responses
    # ------------------------------------------------------------------

    async def get_issue(
        self, pool: asyncpg.Pool, tenant_id: str, issue_id: str
    ) -> dict | None:
        async with tenant_conn(pool, tenant_id) as conn:
            issue_row = await conn.fetchrow(
                "SELECT * FROM audit_issues WHERE issue_id = $1 AND tenant_id = $2",
                issue_id,
                tenant_id,
            )
            if issue_row is None:
                return None
            resp_rows = await conn.fetch(
                """
                SELECT * FROM issue_responses
                WHERE issue_id = $1 AND tenant_id = $2
                ORDER BY responded_at ASC
                """,
                issue_id,
                tenant_id,
            )
        d = dict(issue_row)
        d["responses"] = [dict(r) for r in resp_rows]
        return d

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    async def get_issue_metrics(
        self, pool: asyncpg.Pool, tenant_id: str, engagement_id: str
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT
                    issue_id, severity, status, finding_type,
                    created_at, target_remediation_date
                FROM audit_issues
                WHERE engagement_id = $1 AND tenant_id = $2
                """,
                engagement_id,
                tenant_id,
            )

        total = len(rows)
        by_severity: dict[str, int] = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "informational": 0,
        }
        by_status: dict[str, int] = {
            "open": 0,
            "management_response_pending": 0,
            "in_remediation": 0,
            "resolved": 0,
            "closed": 0,
            "risk_accepted": 0,
        }
        by_finding_type: dict[str, int] = {}
        open_count = 0
        days_open_list: list[float] = []
        past_target_date = 0

        from datetime import datetime, timezone

        now = datetime.now(tz=timezone.utc)

        for r in rows:
            sev = (r["severity"] or "low").lower()
            if sev in by_severity:
                by_severity[sev] += 1

            st = (r["status"] or "open").lower()
            if st in by_status:
                by_status[st] += 1

            ft = r["finding_type"] or "other"
            by_finding_type[ft] = by_finding_type.get(ft, 0) + 1

            is_open = st not in ("resolved", "closed", "risk_accepted")
            if is_open:
                open_count += 1
                created = r["created_at"]
                if created:
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    days_open_list.append((now - created).total_seconds() / 86400)

                target = r["target_remediation_date"]
                if target:
                    target_dt = datetime(
                        target.year, target.month, target.day, tzinfo=timezone.utc
                    )
                    if target_dt < now:
                        past_target_date += 1

        avg_days_open = (
            round(sum(days_open_list) / len(days_open_list), 1)
            if days_open_list
            else 0.0
        )

        return {
            "total": total,
            "by_severity": by_severity,
            "by_status": by_status,
            "by_finding_type": by_finding_type,
            "open_count": open_count,
            "avg_days_open": avg_days_open,
            "past_target_date": past_target_date,
        }

    # ------------------------------------------------------------------
    # Get issues by status
    # ------------------------------------------------------------------

    async def get_issues_by_status(
        self, pool: asyncpg.Pool, tenant_id: str, status: str
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM audit_issues
                WHERE tenant_id = $1 AND status = $2
                ORDER BY created_at DESC
                """,
                tenant_id,
                status,
            )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # List issues (filtered)
    # ------------------------------------------------------------------

    async def list_issues(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        engagement_id: str | None = None,
        severity: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        filters = ["tenant_id = $1"]
        params: list[Any] = [tenant_id]
        idx = 2

        if engagement_id:
            filters.append(f"engagement_id = ${idx}")
            params.append(engagement_id)
            idx += 1
        if severity:
            filters.append(f"severity = ${idx}")
            params.append(severity)
            idx += 1
        if status:
            filters.append(f"status = ${idx}")
            params.append(status)
            idx += 1

        where_clause = " AND ".join(filters)
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                f"SELECT * FROM audit_issues WHERE {where_clause} ORDER BY created_at DESC",
                *params,
            )
        return [dict(r) for r in rows]
