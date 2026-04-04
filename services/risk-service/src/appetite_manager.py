import logging
import uuid
from datetime import datetime

import asyncpg

from .db import tenant_conn

logger = logging.getLogger(__name__)


def _row_to_dict(row: asyncpg.Record) -> dict:
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


class AppetiteManager:
    # ------------------------------------------------------------------
    # upsert
    # ------------------------------------------------------------------
    async def upsert(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        category_key: str,
        appetite_level: str,
        max_acceptable_score: float,
        description: str | None,
        approved_by: str | None,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            cat_row = await conn.fetchrow(
                "SELECT id, name FROM risk_categories WHERE category_key = $1",
                category_key,
            )
            if not cat_row:
                raise ValueError(f"Unknown category_key: {category_key}")
            category_id = cat_row["id"]

            row = await conn.fetchrow(
                """
                INSERT INTO risk_appetite (
                    id, tenant_id, category_id,
                    appetite_level, max_acceptable_score,
                    description, approved_by, created_at, updated_at
                ) VALUES (
                    $1,$2,$3,
                    $4,$5,
                    $6,$7,NOW(),NOW()
                )
                ON CONFLICT (tenant_id, category_id) DO UPDATE SET
                    appetite_level        = EXCLUDED.appetite_level,
                    max_acceptable_score  = EXCLUDED.max_acceptable_score,
                    description           = EXCLUDED.description,
                    approved_by           = EXCLUDED.approved_by,
                    updated_at            = NOW()
                RETURNING *
                """,
                str(uuid.uuid4()),
                tenant_id,
                category_id,
                appetite_level,
                max_acceptable_score,
                description,
                approved_by,
            )
            result = _row_to_dict(row)
            result["category_name"] = cat_row["name"]
            result["category_key"] = category_key
            return result

    # ------------------------------------------------------------------
    # get_all
    # ------------------------------------------------------------------
    async def get_all(self, pool: asyncpg.Pool, tenant_id: str) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT ra.*, rc.display_name AS category_name, rc.category_key
                FROM risk_appetite ra
                JOIN risk_categories rc ON rc.id = ra.category_id
                WHERE ra.tenant_id = $1
                ORDER BY rc.display_name
                """,
                tenant_id,
            )
        return [_row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # check_risk_vs_appetite
    # ------------------------------------------------------------------
    async def check_risk_vs_appetite(
        self, pool: asyncpg.Pool, tenant_id: str, risk_uuid: str
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    r.risk_id, r.title,
                    COALESCE(r.residual_score, r.inherent_score) AS residual_score,
                    ra.max_acceptable_score AS appetite_max,
                    ra.appetite_level
                FROM risks r
                LEFT JOIN risk_appetite ra
                    ON ra.tenant_id = r.tenant_id AND ra.category_id = r.category_id
                WHERE r.id = $1 AND r.tenant_id = $2
                """,
                risk_uuid,
                tenant_id,
            )
        if not row:
            raise LookupError(f"Risk not found: {risk_uuid}")

        residual_score = float(row["residual_score"] or 0)
        appetite_max = float(row["appetite_max"]) if row["appetite_max"] is not None else None
        exceeds = bool(appetite_max is not None and residual_score > appetite_max)
        gap = round(residual_score - appetite_max, 2) if appetite_max is not None else None

        return {
            "risk_id": row["risk_id"],
            "title": row["title"],
            "residual_score": residual_score,
            "appetite_max": appetite_max,
            "exceeds_appetite": exceeds,
            "appetite_level": row["appetite_level"],
            "gap": gap,
        }

    # ------------------------------------------------------------------
    # get_summary
    # ------------------------------------------------------------------
    async def get_summary(self, pool: asyncpg.Pool, tenant_id: str) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            total_row = await conn.fetchrow(
                "SELECT COUNT(*) AS total FROM risk_appetite WHERE tenant_id = $1",
                tenant_id,
            )

            above_row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS cnt
                FROM risks r
                JOIN risk_appetite ra
                  ON ra.tenant_id = r.tenant_id AND ra.category_id = r.category_id
                WHERE r.tenant_id = $1
                  AND r.status != 'closed'
                  AND COALESCE(r.residual_score, r.inherent_score) > ra.max_acceptable_score
                """,
                tenant_id,
            )

            category_rows = await conn.fetch(
                """
                SELECT
                    rc.display_name AS category,
                    ra.appetite_level,
                    COUNT(r.id) FILTER (
                        WHERE r.status != 'closed'
                        AND COALESCE(r.residual_score, r.inherent_score) > ra.max_acceptable_score
                    ) AS risks_above
                FROM risk_appetite ra
                JOIN risk_categories rc ON rc.id = ra.category_id
                LEFT JOIN risks r
                    ON r.category_id = ra.category_id AND r.tenant_id = ra.tenant_id
                WHERE ra.tenant_id = $1
                GROUP BY rc.display_name, ra.appetite_level
                ORDER BY rc.display_name
                """,
                tenant_id,
            )

        return {
            "total_configured": total_row["total"] if total_row else 0,
            "risks_above_appetite": above_row["cnt"] if above_row else 0,
            "by_category": [
                {
                    "category": r["category"],
                    "appetite_level": r["appetite_level"],
                    "risks_above": r["risks_above"],
                }
                for r in category_rows
            ],
        }
