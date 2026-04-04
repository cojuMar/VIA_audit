from __future__ import annotations

import asyncpg

from .db import tenant_conn
from .models import AssignmentCreate


class TemplateManager:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ------------------------------------------------------------------
    # Platform-level template type data (no tenant context)
    # ------------------------------------------------------------------

    async def get_template_types(self) -> list[dict]:
        """Return all field audit template types ordered by display_name."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM field_audit_template_types ORDER BY display_name"
            )
        return [dict(r) for r in rows]

    async def get_templates(
        self,
        type_id: str | None = None,
        active_only: bool = True,
    ) -> list[dict]:
        """Return templates with their type joined, with optional filters."""
        conditions: list[str] = []
        params: list = []

        if active_only:
            params.append(True)
            conditions.append(f"t.is_active = ${len(params)}")

        if type_id is not None:
            params.append(type_id)
            conditions.append(f"t.template_type_id = ${len(params)}")

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        query = f"""
            SELECT
                t.*,
                tt.display_name AS template_type_name,
                tt.type_key     AS template_type_category
            FROM field_audit_templates t
            LEFT JOIN field_audit_template_types tt
                   ON tt.id = t.template_type_id
            {where_clause}
            ORDER BY t.display_name
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]

    async def get_template_with_questions(
        self, template_id: str
    ) -> dict | None:
        """Return template metadata with questions grouped by section."""
        async with self.pool.acquire() as conn:
            template_row = await conn.fetchrow(
                """
                SELECT t.*, tt.display_name AS template_type_name
                FROM field_audit_templates t
                LEFT JOIN field_audit_template_types tt
                       ON tt.id = t.template_type_id
                WHERE t.id = $1
                """,
                template_id,
            )
            if template_row is None:
                return None

            question_rows = await conn.fetch(
                """
                SELECT *
                FROM field_audit_template_questions
                WHERE template_id = $1
                ORDER BY section_name NULLS LAST, sequence_number
                """,
                template_id,
            )

        # Group questions by section
        sections: dict[str, dict] = {}
        section_order: list[str] = []
        for q in question_rows:
            section_name = q["section_name"] or "General"
            if section_name not in sections:
                sections[section_name] = {
                    "id": section_name.lower().replace(" ", "_"),
                    "name": section_name,
                    "questions": [],
                }
                section_order.append(section_name)
            sections[section_name]["questions"].append(dict(q))

        result = dict(template_row)
        result["sections"] = [sections[s] for s in section_order]
        return result

    # ------------------------------------------------------------------
    # Tenant-scoped assignment data
    # ------------------------------------------------------------------

    async def get_assignments(
        self,
        tenant_id: str,
        email: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """Return field audit assignments, optionally filtered by email/status."""
        conditions: list[str] = []
        params: list = []

        if email is not None:
            params.append(email)
            conditions.append(f"a.assigned_to_email = ${len(params)}")

        if status is not None:
            params.append(status)
            conditions.append(f"a.status = ${len(params)}")

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        query = f"""
            SELECT
                a.*,
                t.display_name AS template_name
            FROM field_audit_assignments a
            LEFT JOIN field_audit_templates t ON t.id = a.template_id
            {where_clause}
            ORDER BY a.scheduled_date, a.created_at DESC
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]

    async def create_assignment(
        self, tenant_id: str, data: AssignmentCreate
    ) -> dict:
        """Insert a new field audit assignment."""
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO field_audit_assignments (
                    template_id,
                    assigned_to_email,
                    assigned_to_name,
                    location_name,
                    location_address,
                    scheduled_date,
                    due_date,
                    priority,
                    notes,
                    engagement_id,
                    status,
                    created_at,
                    updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    'pending', NOW(), NOW()
                )
                RETURNING *
                """,
                data.template_id,
                data.assigned_to_email,
                data.assigned_to_name,
                data.location_name,
                data.location_address,
                data.scheduled_date,
                data.due_date,
                data.priority,
                data.notes,
                data.engagement_id,
            )
        return dict(row)

    async def update_assignment_status(
        self, tenant_id: str, assignment_id: str, status: str
    ) -> dict:
        """Update the status of a field audit assignment."""
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                UPDATE field_audit_assignments
                SET status = $1, updated_at = NOW()
                WHERE id = $2
                RETURNING *
                """,
                status,
                assignment_id,
            )
        if row is None:
            raise ValueError(f"Assignment {assignment_id} not found")
        return dict(row)
