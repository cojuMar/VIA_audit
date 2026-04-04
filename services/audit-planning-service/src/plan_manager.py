from __future__ import annotations

import uuid

import asyncpg

from .db import tenant_conn
from .models import PlanCreate, PlanItemCreate


def _priority_from_risk(risk_score: float) -> str:
    if risk_score >= 9.0:
        return "critical"
    if risk_score >= 7.0:
        return "high"
    if risk_score >= 5.0:
        return "medium"
    return "low"


class PlanManager:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def create_plan(self, tenant_id: str, data: PlanCreate) -> dict:
        plan_id = str(uuid.uuid4())
        sql = """
            INSERT INTO audit_plans (
                id, tenant_id, plan_year, title, description,
                total_budget_hours, status, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, 'draft', NOW(), NOW()
            )
            RETURNING *
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                sql,
                plan_id,
                tenant_id,
                data.plan_year,
                data.title,
                data.description,
                data.total_budget_hours,
            )
        return dict(row)

    async def get_plan(self, tenant_id: str, plan_id: str) -> dict:
        sql = """
            SELECT ap.*,
                   (SELECT COUNT(*) FROM audit_plan_items api
                    WHERE api.plan_id = ap.id)::int AS item_count,
                   (SELECT COALESCE(SUM(te.hours), 0)
                    FROM time_entries te
                    JOIN audit_engagements ae ON te.engagement_id = ae.id
                    JOIN audit_plan_items api ON ae.plan_item_id = api.id
                    WHERE api.plan_id = ap.id) AS total_actual_hours
            FROM audit_plans ap
            WHERE ap.id = $1
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(sql, plan_id)
        return dict(row) if row else {}

    async def list_plans(self, tenant_id: str) -> list[dict]:
        sql = """
            SELECT ap.*,
                   (SELECT COUNT(*) FROM audit_plan_items api
                    WHERE api.plan_id = ap.id)::int AS item_count
            FROM audit_plans ap
            ORDER BY ap.plan_year DESC, ap.created_at DESC
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(sql)
        return [dict(r) for r in rows]

    async def approve_plan(
        self, tenant_id: str, plan_id: str, approved_by: str
    ) -> dict:
        sql = """
            UPDATE audit_plans
            SET status = 'approved',
                approved_by = $1,
                approved_at = NOW(),
                updated_at = NOW()
            WHERE id = $2
            RETURNING *
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(sql, approved_by, plan_id)
        return dict(row)

    async def add_item(self, tenant_id: str, data: PlanItemCreate) -> dict:
        item_id = str(uuid.uuid4())
        sql = """
            INSERT INTO audit_plan_items (
                id, tenant_id, plan_id, audit_entity_id,
                title, audit_type, priority,
                planned_start_date, planned_end_date,
                budget_hours, assigned_lead, rationale,
                status, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4,
                $5, $6, $7,
                $8::date, $9::date,
                $10, $11, $12,
                'planned', NOW(), NOW()
            )
            RETURNING *
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                sql,
                item_id,
                tenant_id,
                data.plan_id,
                data.audit_entity_id,
                data.title,
                data.audit_type,
                data.priority,
                data.planned_start_date,
                data.planned_end_date,
                data.budget_hours,
                data.assigned_lead,
                data.rationale,
            )
        return dict(row)

    async def update_item(
        self, tenant_id: str, item_id: str, updates: dict
    ) -> dict:
        allowed = {
            "title", "audit_type", "priority", "planned_start_date",
            "planned_end_date", "budget_hours", "assigned_lead",
            "rationale", "status", "audit_entity_id",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            async with tenant_conn(self.pool, tenant_id) as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM audit_plan_items WHERE id = $1", item_id
                )
            return dict(row)

        set_clauses = ", ".join(
            f"{col} = ${i + 1}" for i, col in enumerate(filtered.keys())
        )
        values = list(filtered.values())
        idx = len(values) + 1
        sql = f"""
            UPDATE audit_plan_items
            SET {set_clauses}, updated_at = NOW()
            WHERE id = ${idx}
            RETURNING *
        """
        values.append(item_id)

        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(sql, *values)
        return dict(row)

    async def get_plan_summary(self, tenant_id: str, plan_id: str) -> dict:
        plan = await self.get_plan(tenant_id, plan_id)

        sql = """
            SELECT
                api.*,
                ae.name AS entity_name,
                ae.risk_score AS entity_risk_score
            FROM audit_plan_items api
            LEFT JOIN audit_entities ae ON api.audit_entity_id = ae.id
            WHERE api.plan_id = $1
            ORDER BY api.priority, api.planned_start_date
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            items = [dict(r) for r in await conn.fetch(sql, plan_id)]

        items_by_priority: dict[str, list] = {
            "critical": [], "high": [], "medium": [], "low": []
        }
        items_by_status: dict[str, list] = {}
        items_by_type: dict[str, list] = {}
        budget_total = 0.0
        coverage = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for item in items:
            pri = item.get("priority", "medium")
            items_by_priority.setdefault(pri, []).append(item)

            st = item.get("status", "planned")
            items_by_status.setdefault(st, []).append(item)

            at = item.get("audit_type", "internal")
            items_by_type.setdefault(at, []).append(item)

            budget_total += float(item.get("budget_hours") or 0)

            risk = float(item.get("entity_risk_score") or 0)
            if risk >= 9.0:
                coverage["critical"] += 1
            elif risk >= 7.0:
                coverage["high"] += 1
            elif risk >= 5.0:
                coverage["medium"] += 1
            else:
                coverage["low"] += 1

        return {
            "plan": plan,
            "items_by_priority": items_by_priority,
            "items_by_status": items_by_status,
            "budget_total": budget_total,
            "items_by_type": items_by_type,
            "coverage": coverage,
        }

    async def auto_populate_from_universe(
        self,
        tenant_id: str,
        plan_id: str,
        risk_threshold: float = 7.0,
    ) -> list[dict]:
        # Find entities already in this plan
        existing_sql = """
            SELECT audit_entity_id
            FROM audit_plan_items
            WHERE plan_id = $1 AND audit_entity_id IS NOT NULL
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            existing_rows = await conn.fetch(existing_sql, plan_id)

        existing_ids = {r["audit_entity_id"] for r in existing_rows}

        # Fetch eligible entities
        entity_sql = """
            SELECT id, name, risk_score, department, owner_name
            FROM audit_entities
            WHERE in_universe = true
              AND risk_score >= $1
            ORDER BY risk_score DESC
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            entities = await conn.fetch(entity_sql, risk_threshold)

        created: list[dict] = []
        for entity in entities:
            eid = str(entity["id"])
            if eid in existing_ids:
                continue

            priority = _priority_from_risk(float(entity["risk_score"]))
            item_data = PlanItemCreate(
                plan_id=plan_id,
                audit_entity_id=eid,
                title=f"Audit of {entity['name']}",
                audit_type="internal",
                priority=priority,
                rationale=(
                    f"Risk score {entity['risk_score']:.1f} meets threshold "
                    f"{risk_threshold:.1f}. Auto-added from audit universe."
                ),
            )
            item = await self.add_item(tenant_id, item_data)
            created.append(item)

        return created
