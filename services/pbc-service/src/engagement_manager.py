from __future__ import annotations

import uuid
from datetime import datetime, timezone

import asyncpg

from .db import tenant_conn
from .models import EngagementCreate


class EngagementManager:

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(
        self, pool: asyncpg.Pool, tenant_id: str, data: EngagementCreate
    ) -> dict:
        engagement_id = str(uuid.uuid4())
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO audit_engagements (
                    id, tenant_id, engagement_name, engagement_type,
                    fiscal_year, period_start, period_end, lead_auditor,
                    description, status, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'planning',
                        NOW(), NOW())
                RETURNING *
                """,
                engagement_id,
                tenant_id,
                data.engagement_name,
                data.engagement_type,
                data.fiscal_year,
                data.period_start,
                data.period_end,
                data.lead_auditor,
                data.description,
            )
        return dict(row)

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    async def list(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        status: str | None = None,
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            if status:
                rows = await conn.fetch(
                    """
                    SELECT * FROM audit_engagements
                    WHERE tenant_id = $1 AND status = $2
                    ORDER BY created_at DESC
                    """,
                    tenant_id,
                    status,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM audit_engagements
                    WHERE tenant_id = $1
                    ORDER BY created_at DESC
                    """,
                    tenant_id,
                )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    async def get(
        self, pool: asyncpg.Pool, tenant_id: str, engagement_id: str
    ) -> dict | None:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM audit_engagements
                WHERE id = $1 AND tenant_id = $2
                """,
                engagement_id,
                tenant_id,
            )
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Update status
    # ------------------------------------------------------------------

    async def update_status(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        engagement_id: str,
        status: str,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                UPDATE audit_engagements
                SET status = $3, updated_at = NOW()
                WHERE id = $1 AND tenant_id = $2
                RETURNING *
                """,
                engagement_id,
                tenant_id,
                status,
            )
        if row is None:
            raise ValueError(f"Engagement {engagement_id} not found")
        return dict(row)

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    async def get_dashboard(
        self, pool: asyncpg.Pool, tenant_id: str, engagement_id: str
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            # Engagement itself
            engagement_row = await conn.fetchrow(
                "SELECT * FROM audit_engagements WHERE id = $1 AND tenant_id = $2",
                engagement_id,
                tenant_id,
            )
            if engagement_row is None:
                raise ValueError(f"Engagement {engagement_id} not found")

            # PBC summary – aggregate across all lists for this engagement
            pbc_row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*)::int                                          AS total,
                    COUNT(*) FILTER (WHERE r.status = 'open')::int        AS open,
                    COUNT(*) FILTER (WHERE r.status = 'fulfilled')::int   AS fulfilled,
                    COUNT(*) FILTER (
                        WHERE r.status IN ('fulfilled', 'not_applicable')
                    )::int                                                 AS completed
                FROM pbc_requests r
                JOIN pbc_request_lists l ON l.id = r.list_id
                WHERE l.engagement_id = $1 AND l.tenant_id = $2
                """,
                engagement_id,
                tenant_id,
            )
            pbc_total = pbc_row["total"] or 0
            pbc_completed = pbc_row["completed"] or 0
            pbc_summary = {
                "total": pbc_total,
                "open": pbc_row["open"] or 0,
                "fulfilled": pbc_row["fulfilled"] or 0,
                "completion_pct": round(pbc_completed / pbc_total * 100, 1)
                if pbc_total
                else 0.0,
            }

            # Issue summary
            issue_rows = await conn.fetch(
                """
                SELECT severity, status
                FROM audit_issues
                WHERE engagement_id = $1 AND tenant_id = $2
                """,
                engagement_id,
                tenant_id,
            )
            issue_total = len(issue_rows)
            by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            open_count = 0
            for ir in issue_rows:
                sev = ir["severity"].lower() if ir["severity"] else "low"
                if sev in by_severity:
                    by_severity[sev] += 1
                if ir["status"] not in ("resolved", "closed", "risk_accepted"):
                    open_count += 1
            issue_summary = {
                "total": issue_total,
                "by_severity": by_severity,
                "open_count": open_count,
            }

            # Workpaper summary
            wp_row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*)::int                                          AS total,
                    COUNT(*) FILTER (WHERE status = 'draft')::int         AS draft,
                    COUNT(*) FILTER (WHERE status = 'in_review')::int     AS in_review,
                    COUNT(*) FILTER (WHERE status = 'final')::int         AS final
                FROM workpapers
                WHERE engagement_id = $1 AND tenant_id = $2
                """,
                engagement_id,
                tenant_id,
            )
            wp_total = wp_row["total"] or 0
            wp_final = wp_row["final"] or 0
            workpaper_summary = {
                "total": wp_total,
                "draft": wp_row["draft"] or 0,
                "in_review": wp_row["in_review"] or 0,
                "final": wp_final,
                "completion_pct": round(wp_final / wp_total * 100, 1)
                if wp_total
                else 0.0,
            }

        return {
            "engagement": dict(engagement_row),
            "pbc_summary": pbc_summary,
            "issue_summary": issue_summary,
            "workpaper_summary": workpaper_summary,
        }
