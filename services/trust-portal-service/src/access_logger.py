import json
import logging
from uuid import uuid4

import asyncpg

from .db import tenant_conn

logger = logging.getLogger(__name__)


class AccessLogger:
    """Immutable access log writer and reader for the trust portal."""

    async def log(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        event_type: str,
        ip: str,
        user_agent: str,
        visitor_email: str | None = None,
        visitor_company: str | None = None,
        document_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """INSERT an access log entry (immutable — no UPDATE/DELETE)."""
        try:
            async with tenant_conn(pool, tenant_id) as conn:
                await conn.execute(
                    """
                    INSERT INTO trust_portal_access_logs (
                        id, tenant_id, event_type, visitor_email,
                        visitor_company, document_id, ip_address,
                        user_agent, metadata, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                    """,
                    str(uuid4()),
                    tenant_id,
                    event_type,
                    visitor_email,
                    visitor_company,
                    document_id,
                    ip,
                    user_agent,
                    json.dumps(metadata) if metadata else None,
                )
        except Exception as exc:
            # Access logging must never crash the main request
            logger.error("Failed to write access log: %s", exc)

    async def get_recent_events(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        limit: int = 100,
        event_type: str | None = None,
    ) -> list[dict]:
        """Fetch recent access log entries, optionally filtered by event_type."""
        async with tenant_conn(pool, tenant_id) as conn:
            if event_type:
                rows = await conn.fetch(
                    """
                    SELECT id, event_type, visitor_email, visitor_company,
                           document_id, ip_address, user_agent, metadata, created_at
                    FROM trust_portal_access_logs
                    WHERE tenant_id = $1 AND event_type = $2
                    ORDER BY created_at DESC
                    LIMIT $3
                    """,
                    tenant_id,
                    event_type,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, event_type, visitor_email, visitor_company,
                           document_id, ip_address, user_agent, metadata, created_at
                    FROM trust_portal_access_logs
                    WHERE tenant_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    tenant_id,
                    limit,
                )
        return [dict(r) for r in rows]

    async def get_stats(
        self, pool: asyncpg.Pool, tenant_id: str
    ) -> dict:
        """Aggregate portal activity stats."""
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*)                                                       AS total_views,
                    COUNT(DISTINCT visitor_email)
                        FILTER (WHERE visitor_email IS NOT NULL)                  AS unique_visitors,
                    COUNT(*) FILTER (WHERE event_type = 'document_download')      AS document_downloads,
                    COUNT(*) FILTER (WHERE event_type = 'chatbot_message')        AS chatbot_messages,
                    COUNT(*) FILTER (WHERE event_type = 'nda_signed')             AS ndas_signed,
                    COUNT(*) FILTER (
                        WHERE created_at >= NOW() - INTERVAL '30 days'
                    )                                                              AS last_30_days
                FROM trust_portal_access_logs
                WHERE tenant_id = $1
                """,
                tenant_id,
            )
        return {
            "total_views": row["total_views"],
            "unique_visitors": row["unique_visitors"],
            "document_downloads": row["document_downloads"],
            "chatbot_messages": row["chatbot_messages"],
            "ndas_signed": row["ndas_signed"],
            "last_30_days": row["last_30_days"],
        }
