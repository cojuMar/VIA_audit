from __future__ import annotations

import datetime
import uuid

import asyncpg

from .db import tenant_conn
from .models import EngagementCreate

# ---------------------------------------------------------------------------
# Status transition graph
# ---------------------------------------------------------------------------
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "planning": {"fieldwork", "cancelled"},
    "fieldwork": {"reporting", "planning", "cancelled"},
    "reporting": {"review", "fieldwork"},
    "review": {"closed", "reporting"},
    "closed": set(),
    "cancelled": {"planning"},
}


class EngagementManager:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ------------------------------------------------------------------
    async def create_engagement(
        self, tenant_id: str, data: EngagementCreate
    ) -> dict:
        eng_id = str(uuid.uuid4())
        code = data.engagement_code

        if not code:
            year = datetime.date.today().year
            # Count existing engagements for this tenant this year to derive seq
            async with tenant_conn(self.pool, tenant_id) as conn:
                count_row = await conn.fetchrow(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM audit_engagements
                    WHERE tenant_id = $1
                      AND EXTRACT(YEAR FROM created_at) = $2
                    """,
                    tenant_id,
                    year,
                )
            seq = (count_row["cnt"] or 0) + 1
            code = f"AUD-{year}-{seq:03d}"

        sql = """
            INSERT INTO audit_engagements (
                id, tenant_id, plan_item_id, title, engagement_code,
                audit_type, scope, objectives,
                planned_start_date, planned_end_date,
                budget_hours, lead_auditor, team_members,
                engagement_manager, status,
                created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8,
                $9::date, $10::date,
                $11, $12, $13,
                $14, 'planning',
                NOW(), NOW()
            )
            RETURNING *
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                sql,
                eng_id,
                tenant_id,
                data.plan_item_id,
                data.title,
                code,
                data.audit_type,
                data.scope,
                data.objectives,
                data.planned_start_date,
                data.planned_end_date,
                data.budget_hours,
                data.lead_auditor,
                data.team_members,
                data.engagement_manager,
            )
        return dict(row)

    # ------------------------------------------------------------------
    async def update_engagement(
        self, tenant_id: str, eng_id: str, updates: dict
    ) -> dict:
        allowed = {
            "title", "scope", "objectives", "planned_start_date",
            "planned_end_date", "budget_hours", "lead_auditor",
            "team_members", "engagement_manager", "plan_item_id",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            async with tenant_conn(self.pool, tenant_id) as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM audit_engagements WHERE id = $1", eng_id
                )
            return dict(row)

        set_clauses = ", ".join(
            f"{col} = ${i + 1}" for i, col in enumerate(filtered.keys())
        )
        values = list(filtered.values())
        idx = len(values) + 1
        sql = f"""
            UPDATE audit_engagements
            SET {set_clauses}, updated_at = NOW()
            WHERE id = ${idx}
            RETURNING *
        """
        values.append(eng_id)

        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(sql, *values)
        return dict(row)

    # ------------------------------------------------------------------
    async def get_engagement(self, tenant_id: str, eng_id: str) -> dict:
        sql = """
            SELECT ae.*,
                   COALESCE((
                       SELECT SUM(te.hours)
                       FROM time_entries te
                       WHERE te.engagement_id = ae.id
                   ), 0) AS actual_hours
            FROM audit_engagements ae
            WHERE ae.id = $1
        """
        milestone_sql = """
            SELECT * FROM audit_milestones
            WHERE engagement_id = $1
            ORDER BY due_date
        """
        resource_sql = """
            SELECT ra.*,
                   COALESCE((
                       SELECT SUM(te.hours)
                       FROM time_entries te
                       WHERE te.engagement_id = ra.engagement_id
                         AND te.auditor_email = ra.auditor_email
                   ), 0) AS actual_hours
            FROM resource_assignments ra
            WHERE ra.engagement_id = $1
        """
        hours_by_activity_sql = """
            SELECT activity_type, SUM(hours) AS hours
            FROM time_entries
            WHERE engagement_id = $1
            GROUP BY activity_type
        """

        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(sql, eng_id)
            milestones = await conn.fetch(milestone_sql, eng_id)
            resources = await conn.fetch(resource_sql, eng_id)
            activity_rows = await conn.fetch(hours_by_activity_sql, eng_id)

        if not row:
            return {}

        result = dict(row)
        result["milestones"] = [dict(m) for m in milestones]
        result["resource_assignments"] = [dict(r) for r in resources]
        result["hours_by_activity"] = {
            r["activity_type"]: float(r["hours"]) for r in activity_rows
        }
        return result

    # ------------------------------------------------------------------
    async def list_engagements(
        self,
        tenant_id: str,
        status: str | None = None,
        lead_auditor: str | None = None,
    ) -> list[dict]:
        conditions: list[str] = []
        params: list = []
        idx = 1

        if status is not None:
            conditions.append(f"ae.status = ${idx}")
            params.append(status)
            idx += 1

        if lead_auditor is not None:
            conditions.append(f"ae.lead_auditor = ${idx}")
            params.append(lead_auditor)
            idx += 1

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        sql = f"""
            SELECT ae.*,
                   COALESCE((
                       SELECT SUM(te.hours)
                       FROM time_entries te
                       WHERE te.engagement_id = ae.id
                   ), 0) AS total_logged_hours
            FROM audit_engagements ae
            {where}
            ORDER BY ae.planned_start_date ASC NULLS LAST, ae.created_at DESC
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    async def transition_status(
        self,
        tenant_id: str,
        eng_id: str,
        new_status: str,
        notes: str | None = None,
    ) -> dict:
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                "SELECT * FROM audit_engagements WHERE id = $1", eng_id
            )
            if not row:
                raise ValueError(f"Engagement {eng_id} not found")

            current_status = row["status"]
            allowed = _ALLOWED_TRANSITIONS.get(current_status, set())
            if new_status not in allowed:
                raise ValueError(
                    f"Transition from '{current_status}' to '{new_status}' is not allowed"
                )

            extra_sets: list[str] = []
            extra_values: list = []
            idx = 3  # $1=notes, $2=new_status consumed below; shift idx

            # Set actual_start_date when entering fieldwork
            if new_status == "fieldwork" and not row["actual_start_date"]:
                extra_sets.append(f"actual_start_date = CURRENT_DATE")

            # Set actual_end_date when closing
            if new_status == "closed":
                extra_sets.append(f"actual_end_date = CURRENT_DATE")

            extra_clause = (", " + ", ".join(extra_sets)) if extra_sets else ""

            update_sql = f"""
                UPDATE audit_engagements
                SET status = $1,
                    status_notes = $2,
                    updated_at = NOW()
                    {extra_clause}
                WHERE id = $3
                RETURNING *
            """
            updated = await conn.fetchrow(
                update_sql, new_status, notes, eng_id
            )
        return dict(updated)

    # ------------------------------------------------------------------
    async def get_gantt_data(
        self, tenant_id: str, plan_id: str | None = None
    ) -> list[dict]:
        params: list = []
        where_clause = ""
        if plan_id:
            where_clause = """
                WHERE ae.plan_item_id IN (
                    SELECT id FROM audit_plan_items WHERE plan_id = $1
                )
            """
            params.append(plan_id)

        sql = f"""
            SELECT ae.id, ae.title, ae.engagement_code AS code,
                   ae.planned_start_date AS start,
                   ae.planned_end_date AS end,
                   ae.status
            FROM audit_engagements ae
            {where_clause}
            ORDER BY ae.planned_start_date ASC NULLS LAST
        """
        milestone_sql = """
            SELECT engagement_id, title, due_date AS due,
                   (status = 'completed') AS done
            FROM audit_milestones
            ORDER BY due_date
        """

        async with tenant_conn(self.pool, tenant_id) as conn:
            eng_rows = await conn.fetch(sql, *params)
            ms_rows = await conn.fetch(milestone_sql)

        # Group milestones by engagement_id
        ms_by_eng: dict[str, list] = {}
        for ms in ms_rows:
            eid = str(ms["engagement_id"])
            ms_by_eng.setdefault(eid, []).append(
                {
                    "title": ms["title"],
                    "due": ms["due"].isoformat() if ms["due"] else None,
                    "done": ms["done"],
                }
            )

        result = []
        for row in eng_rows:
            eid = str(row["id"])
            item = {
                "id": eid,
                "title": row["title"],
                "code": row["code"],
                "start": row["start"].isoformat() if row["start"] else None,
                "end": row["end"].isoformat() if row["end"] else None,
                "status": row["status"],
                "milestones": ms_by_eng.get(eid, []),
            }
            result.append(item)

        return result
