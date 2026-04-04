import logging
from uuid import uuid4

import asyncpg

from .db import tenant_conn
from .models import NDAAcceptance

logger = logging.getLogger(__name__)


class NDAManager:
    """Manage NDA acceptance records for the trust portal."""

    async def has_valid_nda(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        email: str,
        nda_version: str,
    ) -> bool:
        """Return True if a signed NDA for this email+version already exists."""
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT id FROM portal_ndas
                WHERE tenant_id = $1
                  AND signatory_email = $2
                  AND nda_version = $3
                LIMIT 1
                """,
                tenant_id,
                email.lower().strip(),
                nda_version,
            )
        return row is not None

    async def record_acceptance(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        acceptance: NDAAcceptance,
        ip: str,
        user_agent: str,
    ) -> dict:
        """Immutable INSERT — returns the created record."""
        record_id = str(uuid4())
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO portal_ndas (
                    id, tenant_id, signatory_name, signatory_email,
                    signatory_company, nda_version, ip_address,
                    user_agent, accepted_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                RETURNING *
                """,
                record_id,
                tenant_id,
                acceptance.signatory_name,
                acceptance.signatory_email.lower().strip(),
                acceptance.signatory_company,
                acceptance.nda_version,
                ip,
                user_agent,
            )
        return dict(row)

    async def list_acceptances(
        self, pool: asyncpg.Pool, tenant_id: str, limit: int = 200
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT id, signatory_name, signatory_email, signatory_company,
                       nda_version, ip_address, accepted_at
                FROM portal_ndas
                WHERE tenant_id = $1
                ORDER BY accepted_at DESC
                LIMIT $2
                """,
                tenant_id,
                limit,
            )
        return [dict(r) for r in rows]

    async def get_nda_stats(
        self, pool: asyncpg.Pool, tenant_id: str
    ) -> dict:
        """Return {total, last_7_days, unique_companies}."""
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*)                                          AS total,
                    COUNT(*) FILTER (
                        WHERE accepted_at >= NOW() - INTERVAL '7 days'
                    )                                                 AS last_7_days,
                    COUNT(DISTINCT signatory_company)
                        FILTER (WHERE signatory_company IS NOT NULL)  AS unique_companies
                FROM portal_ndas
                WHERE tenant_id = $1
                """,
                tenant_id,
            )
        return {
            "total": row["total"],
            "last_7_days": row["last_7_days"],
            "unique_companies": row["unique_companies"],
        }
