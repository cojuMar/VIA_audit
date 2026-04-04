from __future__ import annotations

import datetime
import uuid

import asyncpg

from .db import tenant_conn
from .models import MilestoneCreate


class MilestoneManager:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def create_milestone(
        self, tenant_id: str, data: MilestoneCreate
    ) -> dict:
        milestone_id = str(uuid.uuid4())
        today = datetime.date.today()
        # Auto-set status: overdue if due_date < today
        try:
            due = datetime.date.fromisoformat(data.due_date)
            status = "overdue" if due < today else "pending"
        except (ValueError, TypeError):
            status = "pending"

        sql = """
            INSERT INTO audit_milestones (
                id, tenant_id, engagement_id, title, milestone_type,
                due_date, owner, notes, status,
                created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6::date, $7, $8, $9,
                NOW(), NOW()
            )
            RETURNING *
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                sql,
                milestone_id,
                tenant_id,
                data.engagement_id,
                data.title,
                data.milestone_type,
                data.due_date,
                data.owner,
                data.notes,
                status,
            )
        return dict(row)

    async def complete_milestone(
        self,
        tenant_id: str,
        milestone_id: str,
        completed_date: str | None = None,
    ) -> dict:
        if completed_date:
            sql = """
                UPDATE audit_milestones
                SET status = 'completed',
                    completed_date = $1::date,
                    updated_at = NOW()
                WHERE id = $2
                RETURNING *
            """
            params: list = [completed_date, milestone_id]
        else:
            sql = """
                UPDATE audit_milestones
                SET status = 'completed',
                    completed_date = CURRENT_DATE,
                    updated_at = NOW()
                WHERE id = $1
                RETURNING *
            """
            params = [milestone_id]

        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(sql, *params)
        return dict(row)

    async def get_engagement_milestones(
        self, tenant_id: str, eng_id: str
    ) -> list[dict]:
        sql = """
            SELECT *
            FROM audit_milestones
            WHERE engagement_id = $1
            ORDER BY due_date
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(sql, eng_id)

        today = datetime.date.today()
        result = []
        for r in rows:
            item = dict(r)
            due = r["due_date"]
            if due:
                delta = (due - today).days
                if delta >= 0:
                    item["days_until_due"] = delta
                    item["days_overdue"] = 0
                else:
                    item["days_until_due"] = 0
                    item["days_overdue"] = abs(delta)
            else:
                item["days_until_due"] = None
                item["days_overdue"] = None
            result.append(item)

        return result

    async def check_overdue_milestones(self, tenant_id: str) -> list[dict]:
        sql = """
            UPDATE audit_milestones
            SET status = 'overdue', updated_at = NOW()
            WHERE status NOT IN ('completed', 'waived')
              AND due_date < CURRENT_DATE
            RETURNING *
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(sql)
        return [dict(r) for r in rows]

    async def seed_default_milestones(
        self,
        tenant_id: str,
        engagement_id: str,
        planned_start: str,
        planned_end: str,
    ) -> list[dict]:
        start = datetime.date.fromisoformat(planned_start)
        end = datetime.date.fromisoformat(planned_end)

        templates = [
            ("Kickoff Meeting", "kickoff", start),
            ("Planning Complete", "milestone", start + datetime.timedelta(days=5)),
            ("Fieldwork Start", "milestone", start + datetime.timedelta(days=7)),
            ("Fieldwork Complete", "milestone", end - datetime.timedelta(days=14)),
            ("Draft Report", "deliverable", end - datetime.timedelta(days=7)),
            ("Management Response", "deliverable", end - datetime.timedelta(days=3)),
            ("Final Report", "deliverable", end),
            ("Closeout", "milestone", end + datetime.timedelta(days=3)),
        ]

        created: list[dict] = []
        for title, ms_type, due in templates:
            data = MilestoneCreate(
                engagement_id=engagement_id,
                title=title,
                milestone_type=ms_type,
                due_date=due.isoformat(),
            )
            ms = await self.create_milestone(tenant_id, data)
            created.append(ms)

        return created
