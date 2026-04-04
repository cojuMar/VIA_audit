from __future__ import annotations

import asyncpg

from .db import tenant_conn
from .models import ResourceAssignmentCreate


class ResourceManager:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def assign(
        self, tenant_id: str, data: ResourceAssignmentCreate
    ) -> dict:
        sql = """
            INSERT INTO resource_assignments (
                tenant_id, engagement_id, auditor_name, auditor_email,
                role, allocated_hours, start_date, end_date,
                created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4,
                $5, $6, $7::date, $8::date,
                NOW(), NOW()
            )
            ON CONFLICT (engagement_id, auditor_email)
            DO UPDATE SET
                auditor_name   = EXCLUDED.auditor_name,
                role           = EXCLUDED.role,
                allocated_hours= EXCLUDED.allocated_hours,
                start_date     = EXCLUDED.start_date,
                end_date       = EXCLUDED.end_date,
                updated_at     = NOW()
            RETURNING *
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                sql,
                tenant_id,
                data.engagement_id,
                data.auditor_name,
                data.auditor_email,
                data.role,
                data.allocated_hours,
                data.start_date,
                data.end_date,
            )
        return dict(row)

    async def list_for_engagement(
        self, tenant_id: str, eng_id: str
    ) -> list[dict]:
        sql = """
            SELECT ra.*,
                   COALESCE((
                       SELECT SUM(te.hours)
                       FROM time_entries te
                       WHERE te.engagement_id = ra.engagement_id
                         AND te.auditor_email = ra.auditor_email
                   ), 0) AS actual_hours
            FROM resource_assignments ra
            WHERE ra.engagement_id = $1
            ORDER BY ra.role, ra.auditor_name
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(sql, eng_id)
        return [dict(r) for r in rows]

    async def get_auditor_schedule(
        self,
        tenant_id: str,
        auditor_email: str,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        sql = """
            SELECT ra.*,
                   ae.title AS engagement_title,
                   ae.engagement_code,
                   ae.status AS engagement_status,
                   ae.planned_start_date,
                   ae.planned_end_date,
                   (
                       SELECT COUNT(*)
                       FROM audit_milestones am
                       WHERE am.engagement_id = ra.engagement_id
                   )::int AS milestone_count
            FROM resource_assignments ra
            JOIN audit_engagements ae ON ra.engagement_id = ae.id
            WHERE ra.auditor_email = $1
              AND (
                  ra.start_date IS NULL
                  OR ra.start_date <= $3::date
              )
              AND (
                  ra.end_date IS NULL
                  OR ra.end_date >= $2::date
              )
            ORDER BY ae.planned_start_date ASC NULLS LAST
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(sql, auditor_email, start_date, end_date)
        return [dict(r) for r in rows]

    async def get_team_availability(
        self,
        tenant_id: str,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        sql = """
            SELECT DISTINCT ra.auditor_name, ra.auditor_email,
                   SUM(ra.allocated_hours) OVER (
                       PARTITION BY ra.auditor_email
                   ) AS total_allocated_hours
            FROM resource_assignments ra
            WHERE (
                ra.start_date IS NULL
                OR ra.start_date <= $2::date
            )
            AND (
                ra.end_date IS NULL
                OR ra.end_date >= $1::date
            )
            ORDER BY ra.auditor_name
        """
        assignments_sql = """
            SELECT ra.auditor_email,
                   ra.engagement_id,
                   ae.title AS engagement_title,
                   ra.role,
                   ra.allocated_hours,
                   ra.start_date,
                   ra.end_date
            FROM resource_assignments ra
            JOIN audit_engagements ae ON ra.engagement_id = ae.id
            WHERE (
                ra.start_date IS NULL
                OR ra.start_date <= $2::date
            )
            AND (
                ra.end_date IS NULL
                OR ra.end_date >= $1::date
            )
            ORDER BY ra.auditor_email, ae.planned_start_date
        """

        async with tenant_conn(self.pool, tenant_id) as conn:
            auditor_rows = await conn.fetch(sql, start_date, end_date)
            assignment_rows = await conn.fetch(
                assignments_sql, start_date, end_date
            )

        # Group assignments by auditor_email
        by_auditor: dict[str, list] = {}
        for r in assignment_rows:
            email = r["auditor_email"]
            by_auditor.setdefault(email, []).append(
                {
                    "engagement_id": str(r["engagement_id"]),
                    "title": r["engagement_title"],
                    "role": r["role"],
                    "allocated_hours": float(r["allocated_hours"]),
                    "start_date": (
                        r["start_date"].isoformat() if r["start_date"] else None
                    ),
                    "end_date": (
                        r["end_date"].isoformat() if r["end_date"] else None
                    ),
                }
            )

        return [
            {
                "auditor_name": r["auditor_name"],
                "auditor_email": r["auditor_email"],
                "total_allocated_hours": float(r["total_allocated_hours"]),
                "assignments": by_auditor.get(r["auditor_email"], []),
            }
            for r in auditor_rows
        ]
