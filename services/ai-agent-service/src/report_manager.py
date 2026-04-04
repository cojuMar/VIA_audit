from uuid import UUID

from .db import tenant_conn


class ReportManager:
    async def list(self, pool, tenant_id: str, report_type: str | None = None) -> list[dict]:
        """List all reports for a tenant, optionally filtered by report_type."""
        async with tenant_conn(pool, tenant_id) as conn:
            if report_type:
                rows = await conn.fetch(
                    """SELECT id, tenant_id, conversation_id, report_type, title,
                              model_used, generation_time_ms, metadata, created_at
                       FROM agent_reports
                       WHERE tenant_id = $1 AND report_type = $2
                       ORDER BY created_at DESC""",
                    UUID(tenant_id), report_type,
                )
            else:
                rows = await conn.fetch(
                    """SELECT id, tenant_id, conversation_id, report_type, title,
                              model_used, generation_time_ms, metadata, created_at
                       FROM agent_reports
                       WHERE tenant_id = $1
                       ORDER BY created_at DESC""",
                    UUID(tenant_id),
                )
        return [dict(r) for r in rows]

    async def get(self, pool, tenant_id: str, report_id: str) -> dict | None:
        """Get a single report including full content."""
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """SELECT id, tenant_id, conversation_id, report_type, title, content,
                          model_used, generation_time_ms, metadata, created_at
                   FROM agent_reports
                   WHERE id = $1 AND tenant_id = $2""",
                UUID(report_id), UUID(tenant_id),
            )
        return dict(row) if row else None

    async def delete_soft(self, pool, tenant_id: str, report_id: str) -> None:
        """
        agent_reports is an IMMUTABLE append-only table.
        Deletion is not supported to preserve the audit trail.
        """
        raise NotImplementedError(
            "Reports are immutable audit records and cannot be deleted. "
            "Archive the parent conversation instead if you need to suppress visibility."
        )
