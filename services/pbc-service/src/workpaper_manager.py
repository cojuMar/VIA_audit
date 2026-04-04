from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from .db import tenant_conn
from .models import SectionUpdate, WorkpaperCreate


class WorkpaperManager:

    # ------------------------------------------------------------------
    # Templates (platform-level, no tenant filter)
    # ------------------------------------------------------------------

    async def list_templates(self, pool: asyncpg.Pool) -> list[dict]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM workpaper_templates
                WHERE is_active = TRUE
                ORDER BY template_name ASC
                """
            )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Create from template
    # ------------------------------------------------------------------

    async def create_from_template(
        self, pool: asyncpg.Pool, tenant_id: str, data: WorkpaperCreate
    ) -> dict:
        workpaper_id = str(uuid.uuid4())

        async with tenant_conn(pool, tenant_id) as conn:
            # Fetch template sections if template_id provided
            template_sections: list[dict] = []
            if data.template_id:
                section_rows = await conn.fetch(
                    """
                    SELECT section_key, title, sort_order
                    FROM workpaper_template_sections
                    WHERE template_id = $1
                    ORDER BY sort_order ASC
                    """,
                    data.template_id,
                )
                template_sections = [dict(r) for r in section_rows]

            # INSERT workpaper
            wp_row = await conn.fetchrow(
                """
                INSERT INTO workpapers (
                    workpaper_id, tenant_id, engagement_id, template_id,
                    title, wp_reference, workpaper_type, preparer,
                    status, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'draft', NOW(), NOW())
                RETURNING *
                """,
                workpaper_id,
                tenant_id,
                data.engagement_id,
                data.template_id,
                data.title,
                data.wp_reference,
                data.workpaper_type,
                data.preparer,
            )

            # INSERT sections from template
            for section in template_sections:
                section_id = str(uuid.uuid4())
                await conn.execute(
                    """
                    INSERT INTO workpaper_sections (
                        section_id, tenant_id, workpaper_id,
                        section_key, title, content, sort_order,
                        is_complete, created_at, updated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, '{}'::jsonb, $6,
                            FALSE, NOW(), NOW())
                    """,
                    section_id,
                    tenant_id,
                    workpaper_id,
                    section["section_key"],
                    section["title"],
                    section["sort_order"],
                )

        return dict(wp_row)

    # ------------------------------------------------------------------
    # Create blank
    # ------------------------------------------------------------------

    async def create_blank(
        self, pool: asyncpg.Pool, tenant_id: str, data: WorkpaperCreate
    ) -> dict:
        workpaper_id = str(uuid.uuid4())
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO workpapers (
                    workpaper_id, tenant_id, engagement_id, template_id,
                    title, wp_reference, workpaper_type, preparer,
                    status, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'draft', NOW(), NOW())
                RETURNING *
                """,
                workpaper_id,
                tenant_id,
                data.engagement_id,
                data.template_id,
                data.title,
                data.wp_reference,
                data.workpaper_type,
                data.preparer,
            )
        return dict(row)

    # ------------------------------------------------------------------
    # Get workpaper with sections
    # ------------------------------------------------------------------

    async def get_workpaper(
        self, pool: asyncpg.Pool, tenant_id: str, workpaper_id: str
    ) -> dict | None:
        async with tenant_conn(pool, tenant_id) as conn:
            wp_row = await conn.fetchrow(
                "SELECT * FROM workpapers WHERE workpaper_id = $1 AND tenant_id = $2",
                workpaper_id,
                tenant_id,
            )
            if wp_row is None:
                return None
            section_rows = await conn.fetch(
                """
                SELECT * FROM workpaper_sections
                WHERE workpaper_id = $1 AND tenant_id = $2
                ORDER BY sort_order ASC
                """,
                workpaper_id,
                tenant_id,
            )
        d = dict(wp_row)
        d["sections"] = [dict(r) for r in section_rows]
        return d

    # ------------------------------------------------------------------
    # Update section
    # ------------------------------------------------------------------

    async def update_section(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        section_id: str,
        data: SectionUpdate,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                UPDATE workpaper_sections
                SET content = $3::jsonb,
                    is_complete = $4,
                    updated_at = NOW()
                WHERE section_id = $1 AND tenant_id = $2
                RETURNING *
                """,
                section_id,
                tenant_id,
                data.content,
                data.is_complete,
            )
        if row is None:
            raise ValueError(f"Section {section_id} not found")
        return dict(row)

    # ------------------------------------------------------------------
    # Add section
    # ------------------------------------------------------------------

    async def add_section(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        workpaper_id: str,
        section_key: str,
        title: str,
        sort_order: int,
    ) -> dict:
        section_id = str(uuid.uuid4())
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO workpaper_sections (
                    section_id, tenant_id, workpaper_id,
                    section_key, title, content, sort_order,
                    is_complete, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, '{}'::jsonb, $6,
                        FALSE, NOW(), NOW())
                RETURNING *
                """,
                section_id,
                tenant_id,
                workpaper_id,
                section_key,
                title,
                sort_order,
            )
        return dict(row)

    # ------------------------------------------------------------------
    # Completion status
    # ------------------------------------------------------------------

    async def get_completion_status(
        self, pool: asyncpg.Pool, tenant_id: str, workpaper_id: str
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT title, is_complete
                FROM workpaper_sections
                WHERE workpaper_id = $1 AND tenant_id = $2
                ORDER BY sort_order ASC
                """,
                workpaper_id,
                tenant_id,
            )
        total = len(rows)
        complete = sum(1 for r in rows if r["is_complete"])
        incomplete = [r["title"] for r in rows if not r["is_complete"]]
        return {
            "total_sections": total,
            "complete_sections": complete,
            "completion_pct": round(complete / total * 100, 1) if total else 0.0,
            "incomplete_sections": incomplete,
        }

    # ------------------------------------------------------------------
    # Finalize
    # ------------------------------------------------------------------

    async def finalize(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        workpaper_id: str,
        reviewer: str,
        review_notes: str | None,
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            # Check all sections complete
            incomplete_count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM workpaper_sections
                WHERE workpaper_id = $1 AND tenant_id = $2 AND is_complete = FALSE
                """,
                workpaper_id,
                tenant_id,
            )
            if incomplete_count and incomplete_count > 0:
                raise ValueError(
                    f"Cannot finalize: {incomplete_count} section(s) still incomplete"
                )
            row = await conn.fetchrow(
                """
                UPDATE workpapers
                SET status = 'final',
                    reviewer = $3,
                    review_notes = $4,
                    finalized_at = NOW(),
                    updated_at = NOW()
                WHERE workpaper_id = $1 AND tenant_id = $2
                RETURNING *
                """,
                workpaper_id,
                tenant_id,
                reviewer,
                review_notes,
            )
        if row is None:
            raise ValueError(f"Workpaper {workpaper_id} not found")
        return dict(row)

    # ------------------------------------------------------------------
    # List workpapers
    # ------------------------------------------------------------------

    async def list_workpapers(
        self, pool: asyncpg.Pool, tenant_id: str, engagement_id: str
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            wp_rows = await conn.fetch(
                """
                SELECT * FROM workpapers
                WHERE tenant_id = $1 AND engagement_id = $2
                ORDER BY created_at DESC
                """,
                tenant_id,
                engagement_id,
            )
            if not wp_rows:
                return []
            wp_ids = [str(r["workpaper_id"]) for r in wp_rows]

            # Section completion counts per workpaper
            count_rows = await conn.fetch(
                """
                SELECT
                    workpaper_id::text,
                    COUNT(*)::int               AS total_sections,
                    COUNT(*) FILTER (WHERE is_complete = TRUE)::int AS complete_sections
                FROM workpaper_sections
                WHERE tenant_id = $1 AND workpaper_id::text = ANY($2)
                GROUP BY workpaper_id
                """,
                tenant_id,
                wp_ids,
            )
        count_map = {r["workpaper_id"]: dict(r) for r in count_rows}
        result = []
        for wp in wp_rows:
            d = dict(wp)
            wp_id_str = str(wp["workpaper_id"])
            counts = count_map.get(wp_id_str, {"total_sections": 0, "complete_sections": 0})
            d["total_sections"] = counts["total_sections"]
            d["complete_sections"] = counts["complete_sections"]
            result.append(d)
        return result

    # ------------------------------------------------------------------
    # Submit for review
    # ------------------------------------------------------------------

    async def submit_for_review(
        self, pool: asyncpg.Pool, tenant_id: str, workpaper_id: str
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                UPDATE workpapers
                SET status = 'in_review', updated_at = NOW()
                WHERE workpaper_id = $1 AND tenant_id = $2
                RETURNING *
                """,
                workpaper_id,
                tenant_id,
            )
        if row is None:
            raise ValueError(f"Workpaper {workpaper_id} not found")
        return dict(row)
