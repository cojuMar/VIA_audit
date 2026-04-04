from __future__ import annotations

import uuid

import asyncpg

from .db import tenant_conn
from .models import EntityCreate


class UniverseManager:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def create_entity(self, tenant_id: str, data: EntityCreate) -> dict:
        entity_id = str(uuid.uuid4())
        sql = """
            INSERT INTO audit_entities (
                id, tenant_id, name, description, entity_type_id,
                owner_name, owner_email, department,
                risk_score, audit_frequency_months, tags, metadata,
                in_universe, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8,
                $9, $10, $11, $12,
                true, NOW(), NOW()
            )
            RETURNING *
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                sql,
                entity_id,
                tenant_id,
                data.name,
                data.description,
                data.entity_type_id,
                data.owner_name,
                data.owner_email,
                data.department,
                data.risk_score,
                data.audit_frequency_months,
                data.tags,
                data.metadata,
            )
        return dict(row)

    async def update_entity(
        self, tenant_id: str, entity_id: str, updates: dict
    ) -> dict:
        allowed = {
            "name", "description", "entity_type_id", "owner_name", "owner_email",
            "department", "risk_score", "audit_frequency_months", "tags",
            "metadata", "in_universe",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            async with tenant_conn(self.pool, tenant_id) as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM audit_entities WHERE id = $1", entity_id
                )
            return dict(row)

        set_clauses = ", ".join(
            f"{col} = ${i + 1}" for i, col in enumerate(filtered.keys())
        )
        values = list(filtered.values())
        idx = len(values) + 1
        sql = f"""
            UPDATE audit_entities
            SET {set_clauses}, updated_at = NOW()
            WHERE id = ${idx}
            RETURNING *
        """
        values.append(entity_id)

        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(sql, *values)
        return dict(row)

    async def list_entities(
        self,
        tenant_id: str,
        entity_type_id: str | None = None,
        min_risk_score: float | None = None,
        in_universe_only: bool = True,
    ) -> list[dict]:
        conditions = []
        params: list = []
        idx = 1

        if in_universe_only:
            conditions.append(f"ae.in_universe = true")

        if entity_type_id is not None:
            conditions.append(f"ae.entity_type_id = ${idx}")
            params.append(entity_type_id)
            idx += 1

        if min_risk_score is not None:
            conditions.append(f"ae.risk_score >= ${idx}")
            params.append(min_risk_score)
            idx += 1

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        sql = f"""
            SELECT ae.*, aet.display_name AS entity_type_name
            FROM audit_entities ae
            LEFT JOIN audit_entity_types aet ON ae.entity_type_id = aet.id
            {where}
            ORDER BY ae.risk_score DESC
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    async def get_entity(self, tenant_id: str, entity_id: str) -> dict | None:
        sql = """
            SELECT ae.*, aet.display_name AS entity_type_name
            FROM audit_entities ae
            LEFT JOIN audit_entity_types aet ON ae.entity_type_id = aet.id
            WHERE ae.id = $1
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(sql, entity_id)
        return dict(row) if row else None

    async def get_entity_types(self) -> list[dict]:
        # Platform table — no tenant RLS needed
        sql = "SELECT * FROM audit_entity_types ORDER BY display_name"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql)
        return [dict(r) for r in rows]

    async def calculate_universe_coverage(
        self, tenant_id: str, plan_year: int
    ) -> dict:
        sql = """
            WITH universe AS (
                SELECT id, risk_score
                FROM audit_entities
                WHERE in_universe = true
            ),
            planned AS (
                SELECT DISTINCT api.audit_entity_id
                FROM audit_plan_items api
                JOIN audit_plans ap ON api.plan_id = ap.id
                WHERE ap.plan_year = $1
                  AND api.audit_entity_id IS NOT NULL
            ),
            high_risk_unaudited AS (
                SELECT ae.id, ae.name, ae.risk_score, ae.department,
                       ae.owner_name, ae.owner_email
                FROM audit_entities ae
                WHERE ae.in_universe = true
                  AND ae.risk_score >= 7.0
                  AND ae.id NOT IN (SELECT audit_entity_id FROM planned)
                ORDER BY ae.risk_score DESC
            )
            SELECT
                (SELECT COUNT(*) FROM universe)::int AS total_entities,
                (SELECT COUNT(*) FROM planned)::int AS entities_with_audits,
                (
                    SELECT json_agg(row_to_json(hru))
                    FROM high_risk_unaudited hru
                ) AS high_risk_unaudited_json
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(sql, plan_year)

        total = row["total_entities"]
        audited = row["entities_with_audits"]
        coverage_pct = round((audited / total * 100), 2) if total else 0.0

        import json
        high_risk_raw = row["high_risk_unaudited_json"]
        if isinstance(high_risk_raw, str):
            high_risk = json.loads(high_risk_raw)
        else:
            high_risk = high_risk_raw or []

        return {
            "total_entities": total,
            "entities_with_audits": audited,
            "coverage_pct": coverage_pct,
            "high_risk_unaudited": high_risk,
        }
