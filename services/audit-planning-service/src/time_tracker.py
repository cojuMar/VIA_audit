from __future__ import annotations

import uuid

import asyncpg

from .db import tenant_conn
from .models import TimeEntryCreate


class TimeTracker:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ------------------------------------------------------------------
    # Immutable INSERT — no UPDATE or DELETE ever
    # ------------------------------------------------------------------
    async def log_hours(self, tenant_id: str, data: TimeEntryCreate) -> dict:
        entry_id = str(uuid.uuid4())
        # entry_date defaults to CURRENT_DATE when None
        if data.entry_date:
            sql = """
                INSERT INTO time_entries (
                    id, tenant_id, engagement_id,
                    auditor_name, auditor_email,
                    entry_date, hours, activity_type,
                    description, is_billable,
                    created_at
                ) VALUES (
                    $1, $2, $3,
                    $4, $5,
                    $6::date, $7, $8,
                    $9, $10,
                    NOW()
                )
                RETURNING *
            """
            params = [
                entry_id, tenant_id, data.engagement_id,
                data.auditor_name, data.auditor_email,
                data.entry_date, data.hours, data.activity_type,
                data.description, data.is_billable,
            ]
        else:
            sql = """
                INSERT INTO time_entries (
                    id, tenant_id, engagement_id,
                    auditor_name, auditor_email,
                    entry_date, hours, activity_type,
                    description, is_billable,
                    created_at
                ) VALUES (
                    $1, $2, $3,
                    $4, $5,
                    CURRENT_DATE, $6, $7,
                    $8, $9,
                    NOW()
                )
                RETURNING *
            """
            params = [
                entry_id, tenant_id, data.engagement_id,
                data.auditor_name, data.auditor_email,
                data.hours, data.activity_type,
                data.description, data.is_billable,
            ]

        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(sql, *params)
        return dict(row)

    # ------------------------------------------------------------------
    async def get_engagement_hours(self, tenant_id: str, eng_id: str) -> dict:
        eng_sql = "SELECT budget_hours FROM audit_engagements WHERE id = $1"
        total_sql = """
            SELECT COALESCE(SUM(hours), 0) AS total_hours
            FROM time_entries
            WHERE engagement_id = $1
        """
        by_activity_sql = """
            SELECT activity_type, COALESCE(SUM(hours), 0) AS hours
            FROM time_entries
            WHERE engagement_id = $1
            GROUP BY activity_type
        """
        by_auditor_sql = """
            SELECT auditor_name AS name, auditor_email AS email,
                   SUM(hours) AS hours
            FROM time_entries
            WHERE engagement_id = $1
            GROUP BY auditor_name, auditor_email
            ORDER BY hours DESC
        """
        daily_sql = """
            SELECT entry_date AS date, SUM(hours) AS hours
            FROM time_entries
            WHERE engagement_id = $1
              AND entry_date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY entry_date
            ORDER BY entry_date
        """

        async with tenant_conn(self.pool, tenant_id) as conn:
            eng_row = await conn.fetchrow(eng_sql, eng_id)
            total_row = await conn.fetchrow(total_sql, eng_id)
            activity_rows = await conn.fetch(by_activity_sql, eng_id)
            auditor_rows = await conn.fetch(by_auditor_sql, eng_id)
            daily_rows = await conn.fetch(daily_sql, eng_id)

        budget = float(eng_row["budget_hours"]) if eng_row else 0.0
        total = float(total_row["total_hours"])
        variance = budget - total
        variance_pct = round((variance / budget * 100), 2) if budget else 0.0

        return {
            "total_hours": total,
            "budget_hours": budget,
            "variance": variance,
            "variance_pct": variance_pct,
            "by_activity": {
                r["activity_type"]: float(r["hours"]) for r in activity_rows
            },
            "by_auditor": [
                {
                    "name": r["name"],
                    "email": r["email"],
                    "hours": float(r["hours"]),
                }
                for r in auditor_rows
            ],
            "daily_trend": [
                {
                    "date": r["date"].isoformat(),
                    "hours": float(r["hours"]),
                }
                for r in daily_rows
            ],
        }

    # ------------------------------------------------------------------
    async def get_auditor_utilization(
        self, tenant_id: str, start_date: str, end_date: str
    ) -> list[dict]:
        sql = """
            SELECT
                te.auditor_email,
                te.auditor_name,
                SUM(te.hours) AS total_hours,
                SUM(CASE WHEN te.is_billable THEN te.hours ELSE 0 END) AS billable_hours
            FROM time_entries te
            WHERE te.entry_date BETWEEN $1::date AND $2::date
            GROUP BY te.auditor_email, te.auditor_name
            ORDER BY total_hours DESC
        """
        by_eng_sql = """
            SELECT te.auditor_email, te.engagement_id,
                   ae.title,
                   SUM(te.hours) AS hours
            FROM time_entries te
            JOIN audit_engagements ae ON te.engagement_id = ae.id
            WHERE te.entry_date BETWEEN $1::date AND $2::date
            GROUP BY te.auditor_email, te.engagement_id, ae.title
        """

        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(sql, start_date, end_date)
            eng_rows = await conn.fetch(by_eng_sql, start_date, end_date)

        # Build per-auditor engagement breakdown
        eng_by_auditor: dict[str, list] = {}
        for r in eng_rows:
            email = r["auditor_email"]
            eng_by_auditor.setdefault(email, []).append(
                {
                    "engagement_id": str(r["engagement_id"]),
                    "title": r["title"],
                    "hours": float(r["hours"]),
                }
            )

        return [
            {
                "auditor_name": r["auditor_name"],
                "auditor_email": r["auditor_email"],
                "total_hours": float(r["total_hours"]),
                "billable_hours": float(r["billable_hours"]),
                "by_engagement": eng_by_auditor.get(r["auditor_email"], []),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    async def get_time_report(
        self,
        tenant_id: str,
        engagement_id: str | None = None,
        auditor_email: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        conditions: list[str] = []
        params: list = []
        idx = 1

        if engagement_id:
            conditions.append(f"te.engagement_id = ${idx}")
            params.append(engagement_id)
            idx += 1

        if auditor_email:
            conditions.append(f"te.auditor_email = ${idx}")
            params.append(auditor_email)
            idx += 1

        if start_date:
            conditions.append(f"te.entry_date >= ${idx}::date")
            params.append(start_date)
            idx += 1

        if end_date:
            conditions.append(f"te.entry_date <= ${idx}::date")
            params.append(end_date)
            idx += 1

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        sql = f"""
            SELECT te.*, ae.title AS engagement_title,
                   ae.engagement_code
            FROM time_entries te
            JOIN audit_engagements ae ON te.engagement_id = ae.id
            {where}
            ORDER BY te.entry_date DESC, te.created_at DESC
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    async def get_budget_status(self, tenant_id: str, plan_id: str) -> dict:
        sql = """
            SELECT
                ae.id AS engagement_id,
                ae.title,
                ae.engagement_code,
                ae.budget_hours,
                COALESCE(SUM(te.hours), 0) AS logged_hours
            FROM audit_engagements ae
            LEFT JOIN time_entries te ON te.engagement_id = ae.id
            WHERE ae.plan_item_id IN (
                SELECT id FROM audit_plan_items WHERE plan_id = $1
            )
            GROUP BY ae.id, ae.title, ae.engagement_code, ae.budget_hours
            ORDER BY ae.title
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(sql, plan_id)

        total_budget = 0.0
        total_logged = 0.0
        over_budget: list[dict] = []
        by_engagement: list[dict] = []

        for r in rows:
            budget = float(r["budget_hours"])
            logged = float(r["logged_hours"])
            total_budget += budget
            total_logged += logged

            item = {
                "engagement_id": str(r["engagement_id"]),
                "title": r["title"],
                "engagement_code": r["engagement_code"],
                "budget_hours": budget,
                "logged_hours": logged,
                "variance": budget - logged,
            }
            by_engagement.append(item)

            if logged > budget:
                over_budget.append(item)

        return {
            "total_budget": total_budget,
            "total_logged": total_logged,
            "variance": total_budget - total_logged,
            "over_budget_engagements": over_budget,
            "by_engagement": by_engagement,
        }
